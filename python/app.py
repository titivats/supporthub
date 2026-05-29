import python.load_env  # noqa: F401

from typing import Dict, List, Optional, Set
import json
import threading
from pathlib import Path

from fastapi import FastAPI

from sqlalchemy.orm import Session

from python.auth import (
    BadSignature,
    SECURE_COOKIES,
    SESSION_AGE,
    make_session_token,
    read_session_token,
    sha256,
    verify_password,
)
from python.db import (
    AppSetting,
    MasterAuditLog,
    MasterLine,
    MasterMachine,
    MasterMachineId,
    MasterMachineType,
    MasterProblem,
    MasterSupportArea,
    MasterSupportAreaMap,
    Ticket,
    TicketTakeoverLog,
    User,
    get_db,
    init_db,
    refresh_postgres_line_to_monitoring_page_table,
)
from python.notify import line_notify
from python.OEE.oee_metrics import build_monitoring_line_metrics, build_monitoring_metrics, parse_th_date_range
from python.time_utils import TH_OFFSET, fmt_hms as _fmt_hms, fmt_th

from python.IoT.iot_monitor_service import iot_monitor
from python.master_data import EQUIPMENTS, MASTER_STATUS_TEXT
from python.settings import LINE_MACHINE_MAP_FILE

app = FastAPI(title="SupportHub")
from fastapi.templating import Jinja2Templates
class _TemplatesCompat:
    """Wrap Jinja2Templates for Starlette 0.36+ (request is first arg)."""

    def __init__(self, directory: str) -> None:
        self._inner = Jinja2Templates(directory=directory)

    def TemplateResponse(
        self,
        request_or_name,
        name_or_context=None,
        context=None,
        status_code: int = 200,
        **kwargs,
    ):
        if isinstance(request_or_name, str):
            name = request_or_name
            ctx = dict(name_or_context or {})
            request = ctx.pop("request")
            if request is None:
                raise ValueError("Template context must include 'request'")
        else:
            request = request_or_name
            name = name_or_context
            ctx = dict(context or {})
            ctx.pop("request", None)

        return self._inner.TemplateResponse(
            request, name, ctx, status_code=status_code, **kwargs
        )


templates = _TemplatesCompat("html")


@app.on_event("startup")
def on_startup() -> None:
    try:
        iot_monitor.start()
    except Exception as exc:
        print(f"[IOT] startup error (app continues): {exc}")


@app.on_event("shutdown")
def on_shutdown() -> None:
    iot_monitor.stop()

# ---------- Database ----------
init_db()

# ---------- Realtime version (smart-reload) ----------
ACTIVE_VERSION = 0
_ACTIVE_LOCK = threading.Lock()

def bump_active_version():
    global ACTIVE_VERSION
    with _ACTIVE_LOCK:
        ACTIVE_VERSION += 1

def current_active_version():
    with _ACTIVE_LOCK:
        return ACTIVE_VERSION

@app.get("/api/active/version")
def api_active_version():
    # Used by index.html polling script for lightweight active-ticket refresh.
    return {"version": current_active_version()}

LINE_MACHINE_MAP_SETTING_KEY = "line_machine_map_v1"
DEFAULT_LINE_MACHINE_MAP_FILE = "database/monitoring_line_map.json"
LINE_MACHINE_ITEM_SEPARATOR = "|||"

def _clean_text(v: Optional[str]) -> str:
    return (v or "").strip()

def _unique_clean(values: List[str]) -> List[str]:
    out: List[str] = []
    seen = set()
    for raw in values:
        val = _clean_text(raw)
        if not val:
            continue
        key = val.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(val)
    return out


def _append_unique_casefold(values: List[str], value: str) -> None:
    if not value:
        return
    lowered = value.lower()
    if lowered not in {item.lower() for item in values}:
        values.append(value)

def _is_admin_user(user: User) -> bool:
    return (user.role or "").lower() == "admin" or (user.username or "").upper() == "ADMIN"

def _normalize_line_machine_map(raw: object) -> Dict[str, List[str]]:
    out: Dict[str, List[str]] = {}
    if not isinstance(raw, dict):
        return out

    for raw_line, raw_items in raw.items():
        line_no = _clean_text(str(raw_line)).upper()
        if not line_no:
            continue

        items: List[str] = []
        seen = set()
        source = raw_items if isinstance(raw_items, list) else [raw_items]
        for entry in source:
            item = _clean_text(str(entry))
            if not item:
                continue
            key = item.lower()
            if key in seen:
                continue
            seen.add(key)
            items.append(item)
        if items:
            out[line_no] = sorted(items, key=lambda s: s.lower())
    return out


def _split_line_machine_item(raw_item: Optional[str]) -> tuple[str, str]:
    item = _clean_text(raw_item)
    if not item:
        return "", ""
    if LINE_MACHINE_ITEM_SEPARATOR in item:
        left, right = item.split(LINE_MACHINE_ITEM_SEPARATOR, 1)
        return _clean_text(left), _clean_text(right)
    return item, ""


def _build_line_machine_lookup(
    db: Session,
) -> tuple[Set[str], Dict[str, str], Dict[str, Dict[str, str]]]:
    allowed_lines: Set[str] = set()
    machine_type_lookup: Dict[str, str] = {}
    machine_id_lookup: Dict[str, Dict[str, str]] = {}

    for (line_no,) in db.query(MasterLine.line_no).all():
        line_val = _clean_text(line_no).upper()
        if line_val:
            allowed_lines.add(line_val)

    for (machine_type,) in db.query(MasterMachineType.machine_type).all():
        mt_val = _clean_text(machine_type)
        if not mt_val:
            continue
        machine_type_lookup.setdefault(mt_val.lower(), mt_val)

    for machine_type, machine_id in db.query(MasterMachineId.machine_type, MasterMachineId.machine_id).all():
        mt_val = _clean_text(machine_type)
        mid_val = _clean_text(machine_id)
        if not mt_val or not mid_val:
            continue
        mt_key = mt_val.lower()
        canonical_type = machine_type_lookup.get(mt_key, mt_val)
        machine_type_lookup.setdefault(mt_key, canonical_type)
        machine_id_lookup.setdefault(mt_key, {})
        machine_id_lookup[mt_key].setdefault(mid_val.lower(), mid_val)

    return allowed_lines, machine_type_lookup, machine_id_lookup


def _sanitize_line_machine_map(
    line_machine_map: Dict[str, List[str]],
    allowed_lines: Set[str],
    machine_type_lookup: Dict[str, str],
    machine_id_lookup: Dict[str, Dict[str, str]],
) -> Dict[str, List[str]]:
    normalized = _normalize_line_machine_map(line_machine_map)
    out: Dict[str, List[str]] = {}

    for line_no, raw_items in normalized.items():
        if line_no not in allowed_lines:
            continue

        kept: List[str] = []
        seen = set()
        for raw_item in raw_items:
            item_type, machine_id = _split_line_machine_item(raw_item)
            if not item_type:
                continue

            type_key = item_type.lower()
            canonical_type = machine_type_lookup.get(type_key)
            if not canonical_type:
                continue

            normalized_item = canonical_type
            if machine_id:
                canonical_id = (machine_id_lookup.get(type_key) or {}).get(machine_id.lower())
                if not canonical_id:
                    continue
                normalized_item = f"{canonical_type}{LINE_MACHINE_ITEM_SEPARATOR}{canonical_id}"

            item_key = normalized_item.lower()
            if item_key in seen:
                continue
            seen.add(item_key)
            kept.append(normalized_item)

        if kept:
            out[line_no] = sorted(kept, key=lambda s: s.lower())
    return out

def _line_machine_map_path() -> Path:
    if LINE_MACHINE_MAP_FILE:
        return Path(LINE_MACHINE_MAP_FILE).expanduser()
    return Path(__file__).resolve().parents[1] / DEFAULT_LINE_MACHINE_MAP_FILE

def _read_line_machine_map_file(path: Path) -> Dict[str, List[str]]:
    if not path.exists():
        return {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8") or "{}")
    except Exception as e:
        print(f"[WARN] Failed to read monitoring map file: {path} ({e})")
        return {}
    return _normalize_line_machine_map(raw)

def _write_line_machine_map_file(path: Path, line_machine_map: Dict[str, List[str]]) -> None:
    normalized = _normalize_line_machine_map(line_machine_map)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(normalized, ensure_ascii=False, indent=2), encoding="utf-8")

def _get_line_machine_map(db: Session) -> Dict[str, List[str]]:
    # Monitoring mapping is file-based to keep it outside PostgreSQL.
    map_file = _line_machine_map_path()
    file_map = _read_line_machine_map_file(map_file)
    if not map_file.exists():
        # One-time fallback: migrate legacy mapping from app_settings if present.
        row = db.query(AppSetting).filter(AppSetting.key == LINE_MACHINE_MAP_SETTING_KEY).first()
        if row and _clean_text(row.value):
            try:
                raw = json.loads(row.value)
            except Exception:
                raw = {}
            normalized = _normalize_line_machine_map(raw)
            if normalized:
                _write_line_machine_map_file(map_file, normalized)
                file_map = normalized

    allowed_lines, machine_type_lookup, machine_id_lookup = _build_line_machine_lookup(db)
    sanitized = _sanitize_line_machine_map(
        file_map,
        allowed_lines,
        machine_type_lookup,
        machine_id_lookup,
    )

    if sanitized != file_map:
        _write_line_machine_map_file(map_file, sanitized)
    return sanitized

def _save_line_machine_map(db: Session, line_machine_map: Dict[str, List[str]]) -> None:
    map_file = _line_machine_map_path()
    _write_line_machine_map_file(map_file, line_machine_map)

    # Remove old app_settings row so Monitoring no longer stores this in DB.
    row = db.query(AppSetting).filter(AppSetting.key == LINE_MACHINE_MAP_SETTING_KEY).first()
    if row:
        db.delete(row)

    try:
        refresh_postgres_line_to_monitoring_page_table()
    except Exception as exc:
        print("[WARN] refresh_postgres_line_to_monitoring_page_table error:", exc)

def _build_monitoring_item_options(
    machine_list: List[str],
    machine_type_map: Dict[str, List[str]],
    machine_id_map: Dict[str, List[str]],
    line_machine_map: Dict[str, List[str]],
) -> List[str]:
    raw_values: List[str] = []
    raw_values.extend(machine_list or [])
    for values in (machine_type_map or {}).values():
        raw_values.extend(values or [])
    for values in (machine_id_map or {}).values():
        raw_values.extend(values or [])
    for values in (line_machine_map or {}).values():
        raw_values.extend(values or [])
    return _unique_clean(raw_values)

def _build_master_data(db: Session) -> Dict[str, object]:
    line_ops = _unique_clean([r.line_no for r in db.query(MasterLine).order_by(MasterLine.line_no.asc()).all()])

    machine_type_map: Dict[str, List[str]] = {}
    problem_map: Dict[str, List[str]] = {}
    problem_combo_map: Dict[str, List[str]] = {}
    machine_id_map: Dict[str, List[str]] = {}
    support_area_map: Dict[str, List[str]] = {}
    support_areas: List[str] = []
    support_area_lookup: Dict[str, str] = {}
    machine_names = set()

    for row in db.query(MasterMachine).order_by(MasterMachine.machine.asc()).all():
        machine = _clean_text(row.machine)
        if not machine:
            continue
        machine_names.add(machine)
        machine_type_map.setdefault(machine, [])
        problem_map.setdefault(machine, [])

    for row in db.query(MasterMachineType).order_by(MasterMachineType.machine.asc(), MasterMachineType.machine_type.asc()).all():
        machine = _clean_text(row.machine)
        machine_type = _clean_text(row.machine_type)
        if not machine:
            continue
        machine_names.add(machine)
        machine_type_map.setdefault(machine, [])
        problem_map.setdefault(machine, [])
        if machine_type:
            _append_unique_casefold(machine_type_map[machine], machine_type)

    for row in db.query(MasterProblem).order_by(MasterProblem.machine.asc(), MasterProblem.machine_type.asc(), MasterProblem.problem.asc()).all():
        machine = _clean_text(row.machine)
        machine_type = _clean_text(row.machine_type)
        problem = _clean_text(row.problem)
        if not machine or not problem:
            continue

        machine_names.add(machine)
        machine_type_map.setdefault(machine, [])
        problem_map.setdefault(machine, [])

        if machine_type:
            _append_unique_casefold(machine_type_map[machine], machine_type)
            key = f"{machine}||{machine_type}"
            problem_combo_map.setdefault(key, [])
            _append_unique_casefold(problem_combo_map[key], problem)
        else:
            _append_unique_casefold(problem_map[machine], problem)

    for row in db.query(MasterMachineId).order_by(MasterMachineId.machine.asc(), MasterMachineId.machine_type.asc(), MasterMachineId.machine_id.asc()).all():
        machine = _clean_text(row.machine)
        machine_type = _clean_text(row.machine_type)
        machine_id = _clean_text(row.machine_id)
        if not machine or not machine_type or not machine_id:
            continue

        machine_names.add(machine)
        machine_type_map.setdefault(machine, [])
        problem_map.setdefault(machine, [])
        _append_unique_casefold(machine_type_map[machine], machine_type)

        key = f"{machine}||{machine_type}"
        machine_id_map.setdefault(key, [])
        _append_unique_casefold(machine_id_map[key], machine_id)

    for row in db.query(MasterSupportArea).order_by(MasterSupportArea.created_at.asc(), MasterSupportArea.id.asc()).all():
        area = _clean_text(row.support_area)
        if not area:
            continue
        if area.lower() not in support_area_lookup:
            support_area_lookup[area.lower()] = area
            support_areas.append(area)
        support_area_map.setdefault(support_area_lookup[area.lower()], [])

    for row in db.query(MasterSupportAreaMap).order_by(MasterSupportAreaMap.created_at.asc(), MasterSupportAreaMap.id.asc()).all():
        area = _clean_text(row.support_area)
        machine = _clean_text(row.machine)
        if not area or not machine:
            continue
        canonical_area = support_area_lookup.get(area.lower())
        if not canonical_area:
            canonical_area = area
            support_area_lookup[area.lower()] = canonical_area
            support_areas.append(canonical_area)
        support_area_map.setdefault(canonical_area, [])
        _append_unique_casefold(support_area_map[canonical_area], machine)

    machine_list = sorted(machine_names, key=lambda x: x.lower())
    for machine in machine_list:
        machine_type_map[machine] = _unique_clean(machine_type_map.get(machine, []))
        problem_map[machine] = _unique_clean(problem_map.get(machine, []))

    for key in list(problem_combo_map.keys()):
        problem_combo_map[key] = _unique_clean(problem_combo_map.get(key, []))
    for key in list(machine_id_map.keys()):
        machine_id_map[key] = _unique_clean(machine_id_map.get(key, []))
    for area in support_areas:
        support_area_map[area] = _unique_clean(support_area_map.get(area, []))
    line_machine_map = _get_line_machine_map(db)
    monitoring_item_options = _build_monitoring_item_options(
        machine_list,
        machine_type_map,
        machine_id_map,
        line_machine_map,
    )

    return {
        "line_ops": line_ops,
        "machine_type_map": machine_type_map,
        "machine_id_map": machine_id_map,
        "support_areas": support_areas,
        "support_area_map": support_area_map,
        "problem_map": problem_map,
        "problem_combo_map": problem_combo_map,
        "machine_list": machine_list,
        "line_machine_map": line_machine_map,
        "monitoring_item_options": monitoring_item_options,
    }

def _master_status_text(status_key: str) -> str:
    return MASTER_STATUS_TEXT.get(status_key or "", "")

def _add_master_audit(db: Session,
                      actor: str,
                      action: str,
                      data_type: str,
                      item: str,
                      details: Optional[str] = None):
    db.add(MasterAuditLog(
        action=_clean_text(action).upper(),
        data_type=_clean_text(data_type).upper(),
        item=_clean_text(item),
        actor=_clean_text(actor) or "-",
        details=_clean_text(details) or None,
    ))

def _get_master_rows_sorted(db: Session, sort_time: str) -> Dict[str, list]:
    newest = sort_time != "asc"

    def _rows(model):
        if newest:
            return db.query(model).order_by(model.created_at.desc(), model.id.desc()).all()
        return db.query(model).order_by(model.created_at.asc(), model.id.asc()).all()

    return {
        "line_rows": _rows(MasterLine),
        "machine_rows": _rows(MasterMachine),
        "machine_type_rows": _rows(MasterMachineType),
        "machine_id_rows": _rows(MasterMachineId),
        "support_area_rows": _rows(MasterSupportArea),
        "support_area_map_rows": _rows(MasterSupportAreaMap),
        "problem_rows": _rows(MasterProblem),
        "audit_rows": _rows(MasterAuditLog),
    }

from python.routes.web_routes import register_web_routes

register_web_routes(
    app,
    templates,
    {
        "get_db": get_db,
        "User": User,
        "Ticket": Ticket,
        "TicketTakeoverLog": TicketTakeoverLog,
        "MasterLine": MasterLine,
        "MasterMachine": MasterMachine,
        "MasterMachineType": MasterMachineType,
        "MasterMachineId": MasterMachineId,
        "MasterProblem": MasterProblem,
        "MasterSupportArea": MasterSupportArea,
        "MasterSupportAreaMap": MasterSupportAreaMap,
        "BadSignature": BadSignature,
        "SECURE_COOKIES": SECURE_COOKIES,
        "SESSION_AGE": SESSION_AGE,
        "make_session_token": make_session_token,
        "read_session_token": read_session_token,
        "sha256": sha256,
        "verify_password": verify_password,
        "line_notify": line_notify,
        "parse_th_date_range": parse_th_date_range,
        "build_monitoring_metrics": build_monitoring_metrics,
        "build_monitoring_line_metrics": build_monitoring_line_metrics,
        "TH_OFFSET": TH_OFFSET,
        "_fmt_hms": _fmt_hms,
        "fmt_th": fmt_th,
        "_clean_text": _clean_text,
        "_is_admin_user": _is_admin_user,
        "_build_master_data": _build_master_data,
        "get_line_machine_map": _get_line_machine_map,
        "save_line_machine_map": _save_line_machine_map,
        "_master_status_text": _master_status_text,
        "_add_master_audit": _add_master_audit,
        "_get_master_rows_sorted": _get_master_rows_sorted,
        "bump_active_version": bump_active_version,
        "EQUIPMENTS": EQUIPMENTS,
        "iot_monitor": iot_monitor,
    },
)
