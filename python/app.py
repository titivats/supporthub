# server_app.py

from typing import Dict, List, Optional, Set
import json
import os
import re
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
from python.database import (
    AppSetting,
    MasterAuditLog,
    MasterLine,
    MasterLineMonitoringMap,
    MasterMachine,
    MasterMachineId,
    MasterMachineType,
    MasterProblem,
    ProblemClass,
    ProblemMatch,
    MasterSupportArea,
    MasterSupportAreaMap,
    SessionLocal,
    Ticket,
    TicketTakeoverLog,
    User,
    get_db,
    init_db,
)
from python.notify import line_notify
from python.OEE.oee_metrics import build_monitoring_line_metrics, build_monitoring_metrics, parse_th_date_range
from python.time_utils import TH_OFFSET, fmt_hms as _fmt_hms, fmt_th

from python.IoT.iot_monitor_service import iot_monitor

app = FastAPI(title="SupportHub")
from fastapi.templating import Jinja2Templates
templates = Jinja2Templates(directory="html")


@app.on_event("startup")
def on_startup() -> None:
    iot_monitor.start()


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

# ---------- Master data ----------
LINE_OPS = ["BT01","BT02","BT03","BT04","BT05","BT06","BT07","BT08","BT09"]

EQUIPMENTS = [
    "Wave Soldering","AOI Wave","AOI Coating","X-ray","RTV","Coating",
    "Robot Packing","Conveyor","Auto Insertion","Router",
    "KED Cleaning Pallet","KED Cleaning PCB","DCT Cleaning PCB","Etc..",
]

PROBLEM_MAP = {
    "Wave Soldering": ["Covert Program", "Clean Nozzle", "Flux Empty", "Fill Solder", "Machine Down", "Board Drop", "Fine-tune Program"],
    "AOI Wave": ["Covert Program", "Machine Down", "Full Storage Data", "Board Drop", "Fine-tune Program"],
    "AOI Coating": ["Covert Program", "Machine Down", "Full Storage Data", "Board Drop", "Fine-tune Program"],
    "X-ray": ["Covert Program", "Machine Down", "Full Storage Data", "Board Drop", "Fine-tune Program"],
    "RTV": ["Covert Program", "Nozzle Broken", "Nozzle Clog", "Fill Glue", "Fill Coating Liquid", "Machine Down", "Board Drop", "Fine-tune Program"],
    "Coating": ["Covert Program", "Nozzle Broken", "Nozzle Clog", "Fill Glue", "Fill Coating Liquid", "Machine Down", "Board Drop", "Fine-tune Program"],
    "Robot Packing": ["Covert Program", "Machine Down", "Sensors Error", "Vacuum Error", "Camera Error", "Board Drop", "Robot not movement", "Robot Error"],
    "Conveyor": ["Machine Down", "Board Can't Transfer", "Board Drop"],
    "Auto Insertion": ["Covert Program", "Machine Down", "Can't Placement Part", "Fine-tune Program"],
    "Router": ["Covert Program", "Machine Down", "Change Router Bit", "Router Bit Broken", "Dust Cabinet Not Working", "Fine-tune Program"],
    "KED Cleaning Pallet": ["Covert Program", "Machine Down", "Fill Chemical", "Fine-tune Program", "System Chemical Leak", "Chemical Over Flow"],
    "KED Cleaning PCB": ["Covert Program", "Machine Down", "Fill Chemical", "Fine-tune Program", "System Chemical Leak", "Chemical Over Flow"],
    "DCT Cleaning PCB": ["Covert Program", "Machine Down", "Fill Chemical", "Fine-tune Program", "System Chemical Leak", "Chemical Over Flow"],
}

EXTRA_LINE_OPS = ["PACKING", "REWORK", "CLEANING"]

MACHINE_TYPE_MAP_DEFAULT = {
    "Wave Soldering": ["ECO1 SELECT", "ERSA VERSAFLOW"],
    "AOI Wave": ["Jet", "Nordson", "Axxon", "Yamaha"],
    "AOI Coating": ["Jet", "Nordson", "Axxon", "Yamaha"],
    "X-ray": ["Vitrox", "Omron"],
    "RTV": ["Mycronic", "Nordson"],
    "Coating": ["Mycronic", "Nordson"],
    "UV Curing": ["Nutek", "Nordson"],
    "Robotic": ["Robot KUKA"],
    "Auto Insertion": ["FACC"],
    "Router": ["Aurotek Router", "Cencorp Router"],
    "Cleaning Machine": ["DCT Twin", "KED D1000", "KED AT5000"],
    "Rework Machine": ["SRT Machine", "Minipot", "Oven"],
    "Etc..": ["Other M/C or Tools"],
}

DEFAULT_SUPPORT_AREAS = ["Backline", "Inspection", "Coating & Robotic", "Rework", "Etc.."]
DEFAULT_SUPPORT_AREA_MAP = {
    "Backline": ["Wave Soldering", "Auto Insertion", "Router", "Cleaning Machine"],
    "Inspection": ["AOI Wave", "AOI Coating", "X-ray"],
    "Coating & Robotic": ["RTV", "Coating", "UV Curing", "Robotic"],
    "Rework": ["Rework Machine"],
    "Etc..": ["Etc.."],
}
LINE_MACHINE_MAP_SETTING_KEY = "line_machine_map_v1"
LEGACY_LINE_MACHINE_MAP_FILE = "database/monitoring_line_map.json"
LINE_MACHINE_MAP_FILE_ENV = "SUPPORTHUB_LINE_MACHINE_MAP_FILE"
LINE_MACHINE_ITEM_SEPARATOR = "|||"

MASTER_STATUS_TEXT = {
    "line_added": "Added new Line No. successfully",
    "line_exists": "Line No. already exists",
    "line_deleted": "Deleted Line No. successfully",
    "line_not_found": "Line No. not found",
    "machine_added": "Added new Machine successfully",
    "machine_exists": "Machine already exists",
    "machine_deleted": "Deleted Machine successfully",
    "machine_not_found": "Machine not found",
    "machine_type_added": "Added new Machine Type successfully",
    "machine_type_exists": "Machine Type already exists for this Machine",
    "machine_type_deleted": "Deleted Machine Type successfully",
    "machine_type_not_found": "Machine Type not found",
    "machine_id_added": "Added new Machine ID successfully",
    "machine_id_exists": "Machine ID already exists for this Machine Type",
    "machine_id_deleted": "Deleted Machine ID successfully",
    "machine_id_not_found": "Machine ID not found",
    "support_area_added": "Added new Support Area successfully",
    "support_area_exists": "Support Area already exists",
    "support_area_deleted": "Deleted Support Area successfully",
    "support_area_not_found": "Support Area not found",
    "support_area_map_added": "Mapped Support Area to Machine successfully",
    "support_area_map_exists": "This Support Area and Machine mapping already exists",
    "support_area_map_deleted": "Deleted Support Area and Machine mapping successfully",
    "support_area_map_not_found": "Support Area and Machine mapping not found",
    "problem_added": "Added new Problem successfully",
    "problem_exists": "Problem already exists",
    "problem_deleted": "Deleted Problem successfully",
    "problem_not_found": "Problem not found",
    "line_machine_map_added": "Mapped Line No. to Monitoring item successfully",
    "line_machine_map_exists": "This Line No. and Monitoring item mapping already exists",
    "line_machine_map_deleted": "Deleted Line No. and Monitoring item mapping successfully",
    "line_machine_map_not_found": "Line No. and Monitoring item mapping not found",
    "invalid_input": "Please provide all required fields",
}

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

MASTER_SEED_KEY = "master_seed_v1"

def _ensure_master_seeded():
    try:
        db = SessionLocal()
        seed_row = db.query(AppSetting).filter(AppSetting.key == MASTER_SEED_KEY).first()
        if seed_row and (seed_row.value or "").strip() == "1":
            return

        line_seen = {
            _clean_text(r.line_no).upper()
            for r in db.query(MasterLine).all()
            if _clean_text(r.line_no)
        }
        machine_seen = {
            _clean_text(r.machine).lower()
            for r in db.query(MasterMachine).all()
            if _clean_text(r.machine)
        }
        machine_type_seen = {
            (_clean_text(r.machine).lower(), _clean_text(r.machine_type).lower())
            for r in db.query(MasterMachineType).all()
            if _clean_text(r.machine) and _clean_text(r.machine_type)
        }
        support_area_seen = {
            _clean_text(r.support_area).lower()
            for r in db.query(MasterSupportArea).all()
            if _clean_text(r.support_area)
        }
        support_map_seen = {
            (_clean_text(r.support_area).lower(), _clean_text(r.machine).lower())
            for r in db.query(MasterSupportAreaMap).all()
            if _clean_text(r.support_area) and _clean_text(r.machine)
        }
        problem_seen = {
            (_clean_text(r.machine).lower(), _clean_text(r.machine_type).lower(), _clean_text(r.problem).lower())
            for r in db.query(MasterProblem).all()
            if _clean_text(r.machine) and _clean_text(r.problem)
        }

        def add_machine_if_missing(machine_val: str):
            key = machine_val.lower()
            if key in machine_seen:
                return
            machine_seen.add(key)
            db.add(MasterMachine(machine=machine_val))

        # Seed line numbers.
        for line in _unique_clean(LINE_OPS + EXTRA_LINE_OPS):
            line_val = _clean_text(line).upper()
            if not line_val:
                continue
            if line_val not in line_seen:
                line_seen.add(line_val)
                db.add(MasterLine(line_no=line_val))

        # Seed machine + machine type defaults.
        for machine, machine_types in MACHINE_TYPE_MAP_DEFAULT.items():
            machine_val = _clean_text(machine)
            if not machine_val:
                continue
            add_machine_if_missing(machine_val)
            for machine_type in _unique_clean(machine_types):
                mt_val = _clean_text(machine_type)
                if not mt_val:
                    continue
                mt_key = (machine_val.lower(), mt_val.lower())
                if mt_key not in machine_type_seen:
                    machine_type_seen.add(mt_key)
                    db.add(MasterMachineType(machine=machine_val, machine_type=mt_val))

        # Seed support areas + support area mappings.
        for area in _unique_clean(DEFAULT_SUPPORT_AREAS):
            area_val = _clean_text(area)
            if not area_val:
                continue
            area_key = area_val.lower()
            if area_key not in support_area_seen:
                support_area_seen.add(area_key)
                db.add(MasterSupportArea(support_area=area_val))

        for area, machines in DEFAULT_SUPPORT_AREA_MAP.items():
            area_val = _clean_text(area)
            if not area_val:
                continue
            area_key = area_val.lower()
            if area_key not in support_area_seen:
                support_area_seen.add(area_key)
                db.add(MasterSupportArea(support_area=area_val))
            for machine in _unique_clean(machines):
                machine_val = _clean_text(machine)
                if not machine_val:
                    continue
                add_machine_if_missing(machine_val)
                map_key = (area_key, machine_val.lower())
                if map_key not in support_map_seen:
                    support_map_seen.add(map_key)
                    db.add(MasterSupportAreaMap(support_area=area_val, machine=machine_val))

        # Seed machine-level default problems.
        for machine, problems in PROBLEM_MAP.items():
            machine_val = _clean_text(machine)
            if not machine_val:
                continue
            add_machine_if_missing(machine_val)
            for problem in _unique_clean(problems):
                problem_val = _clean_text(problem)
                if not problem_val:
                    continue
                problem_key = (machine_val.lower(), "", problem_val.lower())
                if problem_key not in problem_seen:
                    problem_seen.add(problem_key)
                    db.add(MasterProblem(machine=machine_val, machine_type=None, problem=problem_val))

        if not seed_row:
            seed_row = AppSetting(key=MASTER_SEED_KEY, value="1")
            db.add(seed_row)
        else:
            seed_row.value = "1"
            db.add(seed_row)
        db.commit()
    except Exception as e:
        print("[INIT] _ensure_master_seeded error:", e)
    finally:
        try:
            db.close()
        except Exception:
            pass

def _is_admin_user(user: User) -> bool:
    return (user.role or "").lower() == "admin" or (user.username or "").upper() == "ADMIN"

_ensure_master_seeded()

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

def _legacy_line_machine_map_path() -> Path:
    custom_path = _clean_text(os.getenv(LINE_MACHINE_MAP_FILE_ENV))
    if custom_path:
        return Path(custom_path).expanduser()
    return Path(__file__).resolve().parents[1] / LEGACY_LINE_MACHINE_MAP_FILE

def _read_legacy_line_machine_map_file(path: Path) -> Dict[str, List[str]]:
    if not path.exists():
        return {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8") or "{}")
    except Exception as e:
        print(f"[WARN] Failed to read monitoring map file: {path} ({e})")
        return {}
    return _normalize_line_machine_map(raw)


_LINE_MACHINE_AUDIT_ITEM_PATTERN = re.compile(
    r"^\s*(?P<line>.+?)\s*->\s*(?P<type>.+?)\s*(?:\((?P<id>[^()]*)\))?\s*$"
)


def _parse_line_machine_map_audit_item(raw_item: Optional[str]) -> tuple[str, str]:
    text = _clean_text(raw_item)
    if not text:
        return "", ""

    matched = _LINE_MACHINE_AUDIT_ITEM_PATTERN.match(text)
    if not matched:
        return "", ""

    line_val = _clean_text(matched.group("line")).upper()
    machine_type = _clean_text(matched.group("type"))
    machine_id = _clean_text(matched.group("id"))
    if not line_val or not machine_type:
        return "", ""

    normalized_item = machine_type
    if machine_id and machine_id != "-":
        normalized_item = f"{machine_type}{LINE_MACHINE_ITEM_SEPARATOR}{machine_id}"
    return line_val, normalized_item


def _load_line_machine_map_from_audit(db: Session) -> Dict[str, List[str]]:
    rows = (
        db.query(MasterAuditLog)
        .filter(MasterAuditLog.data_type == "LINE_MACHINE_MAP")
        .order_by(MasterAuditLog.created_at.asc(), MasterAuditLog.id.asc())
        .all()
    )
    if not rows:
        return {}

    line_machine_map: Dict[str, List[str]] = {}
    for row in rows:
        line_val, item_val = _parse_line_machine_map_audit_item(getattr(row, "item", ""))
        if not line_val or not item_val:
            continue

        action = _clean_text(getattr(row, "action", "")).upper()
        existing = list(line_machine_map.get(line_val, []))
        if action == "DELETE":
            kept = [val for val in existing if _clean_text(val).lower() != item_val.lower()]
            if kept:
                line_machine_map[line_val] = kept
            else:
                line_machine_map.pop(line_val, None)
            continue

        if not any(_clean_text(val).lower() == item_val.lower() for val in existing):
            existing.append(item_val)
            line_machine_map[line_val] = existing

    return _normalize_line_machine_map(line_machine_map)


def _load_line_machine_map_from_db(db: Session) -> Dict[str, List[str]]:
    out: Dict[str, List[str]] = {}
    rows = (
        db.query(MasterLineMonitoringMap)
        .order_by(
            MasterLineMonitoringMap.line_no.asc(),
            MasterLineMonitoringMap.machine_type.asc(),
            MasterLineMonitoringMap.machine_id.asc(),
            MasterLineMonitoringMap.id.asc(),
        )
        .all()
    )
    for row in rows:
        line_no = _clean_text(row.line_no).upper()
        machine_type = _clean_text(row.machine_type)
        machine_id = _clean_text(row.machine_id)
        if not line_no or not machine_type:
            continue
        normalized_item = machine_type
        if machine_id and machine_id != "-":
            normalized_item = f"{machine_type}{LINE_MACHINE_ITEM_SEPARATOR}{machine_id}"
        _append_unique_casefold(out.setdefault(line_no, []), normalized_item)
    return _normalize_line_machine_map(out)


def _replace_line_machine_map_in_db(db: Session, line_machine_map: Dict[str, List[str]]) -> None:
    normalized = _normalize_line_machine_map(line_machine_map)
    db.query(MasterLineMonitoringMap).delete(synchronize_session=False)
    for line_no, items in normalized.items():
        for raw_item in items:
            machine_type, machine_id = _split_line_machine_item(raw_item)
            if not machine_type:
                continue
            db.add(
                MasterLineMonitoringMap(
                    line_no=line_no,
                    machine_type=machine_type,
                    machine_id=machine_id or "-",
                )
            )
    db.flush()


def _bootstrap_line_machine_map_from_legacy_sources(db: Session) -> None:
    if db.query(MasterLineMonitoringMap.id).first():
        return

    legacy_map = _read_legacy_line_machine_map_file(_legacy_line_machine_map_path())

    if not legacy_map:
        row = db.query(AppSetting).filter(AppSetting.key == LINE_MACHINE_MAP_SETTING_KEY).first()
        if row and _clean_text(row.value):
            try:
                raw = json.loads(row.value)
            except Exception:
                raw = {}
            legacy_map = _normalize_line_machine_map(raw)

    if not legacy_map:
        legacy_map = _load_line_machine_map_from_audit(db)

    if not legacy_map:
        return

    allowed_lines, machine_type_lookup, machine_id_lookup = _build_line_machine_lookup(db)
    sanitized = _sanitize_line_machine_map(
        legacy_map,
        allowed_lines,
        machine_type_lookup,
        machine_id_lookup,
    )
    if not sanitized:
        return

    _replace_line_machine_map_in_db(db, sanitized)
    row = db.query(AppSetting).filter(AppSetting.key == LINE_MACHINE_MAP_SETTING_KEY).first()
    if row:
        db.delete(row)
    db.commit()


def _get_line_machine_map(db: Session) -> Dict[str, List[str]]:
    try:
        _bootstrap_line_machine_map_from_legacy_sources(db)
    except Exception as exc:
        db.rollback()
        print("[WARN] bootstrap line-monitoring map from legacy sources failed:", exc)

    db_map = _load_line_machine_map_from_db(db)

    allowed_lines, machine_type_lookup, machine_id_lookup = _build_line_machine_lookup(db)
    sanitized = _sanitize_line_machine_map(
        db_map,
        allowed_lines,
        machine_type_lookup,
        machine_id_lookup,
    )
    return sanitized

def _save_line_machine_map(db: Session, line_machine_map: Dict[str, List[str]]) -> None:
    allowed_lines, machine_type_lookup, machine_id_lookup = _build_line_machine_lookup(db)
    sanitized = _sanitize_line_machine_map(
        line_machine_map,
        allowed_lines,
        machine_type_lookup,
        machine_id_lookup,
    )
    _replace_line_machine_map_in_db(db, sanitized)

    # Keep old key cleaned up after moving to PostgreSQL table storage.
    row = db.query(AppSetting).filter(AppSetting.key == LINE_MACHINE_MAP_SETTING_KEY).first()
    if row:
        db.delete(row)

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
        "ProblemClass": ProblemClass,
        "ProblemMatch": ProblemMatch,
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
