from __future__ import annotations

import json
import os
import re
import threading
from pathlib import Path
from typing import Dict, List, Optional, Set

from sqlalchemy.orm import Session

from python.config_defaults import (
    DEFAULT_SUPPORT_AREAS,
    DEFAULT_SUPPORT_AREA_MAP,
    EXTRA_LINE_OPS,
    LEGACY_LINE_MACHINE_MAP_FILE,
    LINE_MACHINE_ITEM_SEPARATOR,
    LINE_MACHINE_MAP_FILE_ENV,
    LINE_MACHINE_MAP_SETTING_KEY,
    LINE_OPS,
    MACHINE_TYPE_MAP_DEFAULT,
    MASTER_SEED_KEY,
    MASTER_STATUS_TEXT,
    PROBLEM_MAP,
)
from python.database.base import SessionLocal
from python.database.models import (
    AppSetting,
    MasterAuditLog,
    MasterLine,
    MasterLineMonitoringMap,
    MasterMachine,
    MasterMachineId,
    MasterMachineType,
    MasterProblem,
    MasterSupportArea,
    MasterSupportAreaMap,
    User,
)
from python.logging_utils import get_supporthub_logger


APP_LOGGER = get_supporthub_logger("app")

ACTIVE_VERSION = 0
MASTER_DATA_VERSION = 0
_ACTIVE_LOCK = threading.Lock()
_MASTER_DATA_LOCK = threading.Lock()
_MASTER_DATA_CACHE: Dict[str, object] = {"version": None, "data": None}

_LINE_MACHINE_AUDIT_ITEM_PATTERN = re.compile(
    r"^\s*(?P<line>.+?)\s*->\s*(?P<type>.+?)\s*(?:\((?P<id>[^()]*)\))?\s*$"
)


def bump_active_version() -> None:
    global ACTIVE_VERSION
    with _ACTIVE_LOCK:
        ACTIVE_VERSION += 1


def current_active_version() -> int:
    with _ACTIVE_LOCK:
        return ACTIVE_VERSION


def bump_master_data_version() -> None:
    global MASTER_DATA_VERSION
    with _MASTER_DATA_LOCK:
        MASTER_DATA_VERSION += 1
        _MASTER_DATA_CACHE["version"] = None
        _MASTER_DATA_CACHE["data"] = None


def clean_text(value: Optional[str]) -> str:
    return (value or "").strip()


def unique_clean(values: List[str]) -> List[str]:
    out: List[str] = []
    seen = set()
    for raw in values:
        val = clean_text(raw)
        if not val:
            continue
        lowered = val.lower()
        if lowered in seen:
            continue
        seen.add(lowered)
        out.append(val)
    return out


def append_unique_casefold(values: List[str], value: str) -> None:
    if not value:
        return
    lowered = value.lower()
    if lowered not in {item.lower() for item in values}:
        values.append(value)


def is_admin_user(user: User) -> bool:
    return (user.role or "").lower() == "admin" or (user.username or "").upper() == "ADMIN"


def ensure_master_seeded() -> None:
    db = None
    try:
        db = SessionLocal()
        seed_row = db.query(AppSetting).filter(AppSetting.key == MASTER_SEED_KEY).first()
        if seed_row and (seed_row.value or "").strip() == "1":
            return

        line_seen = {
            clean_text(row.line_no).upper()
            for row in db.query(MasterLine).all()
            if clean_text(row.line_no)
        }
        machine_seen = {
            clean_text(row.machine).lower()
            for row in db.query(MasterMachine).all()
            if clean_text(row.machine)
        }
        machine_type_seen = {
            (clean_text(row.machine).lower(), clean_text(row.machine_type).lower())
            for row in db.query(MasterMachineType).all()
            if clean_text(row.machine) and clean_text(row.machine_type)
        }
        support_area_seen = {
            clean_text(row.support_area).lower()
            for row in db.query(MasterSupportArea).all()
            if clean_text(row.support_area)
        }
        support_map_seen = {
            (clean_text(row.support_area).lower(), clean_text(row.machine).lower())
            for row in db.query(MasterSupportAreaMap).all()
            if clean_text(row.support_area) and clean_text(row.machine)
        }
        problem_seen = {
            (
                clean_text(row.machine).lower(),
                clean_text(row.machine_type).lower(),
                clean_text(row.problem).lower(),
            )
            for row in db.query(MasterProblem).all()
            if clean_text(row.machine) and clean_text(row.problem)
        }

        def add_machine_if_missing(machine_val: str) -> None:
            key = machine_val.lower()
            if key in machine_seen:
                return
            machine_seen.add(key)
            db.add(MasterMachine(machine=machine_val))

        for line in unique_clean(LINE_OPS + EXTRA_LINE_OPS):
            line_val = clean_text(line).upper()
            if line_val and line_val not in line_seen:
                line_seen.add(line_val)
                db.add(MasterLine(line_no=line_val))

        for machine, machine_types in MACHINE_TYPE_MAP_DEFAULT.items():
            machine_val = clean_text(machine)
            if not machine_val:
                continue
            add_machine_if_missing(machine_val)
            for machine_type in unique_clean(machine_types):
                machine_type_val = clean_text(machine_type)
                if not machine_type_val:
                    continue
                machine_type_key = (machine_val.lower(), machine_type_val.lower())
                if machine_type_key not in machine_type_seen:
                    machine_type_seen.add(machine_type_key)
                    db.add(MasterMachineType(machine=machine_val, machine_type=machine_type_val))

        for support_area in unique_clean(DEFAULT_SUPPORT_AREAS):
            support_area_val = clean_text(support_area)
            if not support_area_val:
                continue
            support_area_key = support_area_val.lower()
            if support_area_key not in support_area_seen:
                support_area_seen.add(support_area_key)
                db.add(MasterSupportArea(support_area=support_area_val))

        for support_area, machines in DEFAULT_SUPPORT_AREA_MAP.items():
            support_area_val = clean_text(support_area)
            if not support_area_val:
                continue
            support_area_key = support_area_val.lower()
            if support_area_key not in support_area_seen:
                support_area_seen.add(support_area_key)
                db.add(MasterSupportArea(support_area=support_area_val))
            for machine in unique_clean(machines):
                machine_val = clean_text(machine)
                if not machine_val:
                    continue
                add_machine_if_missing(machine_val)
                map_key = (support_area_key, machine_val.lower())
                if map_key not in support_map_seen:
                    support_map_seen.add(map_key)
                    db.add(MasterSupportAreaMap(support_area=support_area_val, machine=machine_val))

        for machine, problems in PROBLEM_MAP.items():
            machine_val = clean_text(machine)
            if not machine_val:
                continue
            add_machine_if_missing(machine_val)
            for problem in unique_clean(problems):
                problem_val = clean_text(problem)
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
    except Exception:
        APP_LOGGER.exception("[INIT] ensure_master_seeded error")
    finally:
        if db is not None:
            try:
                db.close()
            except Exception:
                pass


def normalize_line_machine_map(raw: object) -> Dict[str, List[str]]:
    out: Dict[str, List[str]] = {}
    if not isinstance(raw, dict):
        return out

    for raw_line, raw_items in raw.items():
        line_no = clean_text(str(raw_line)).upper()
        if not line_no:
            continue

        items: List[str] = []
        seen = set()
        source = raw_items if isinstance(raw_items, list) else [raw_items]
        for entry in source:
            item = clean_text(str(entry))
            if not item:
                continue
            lowered = item.lower()
            if lowered in seen:
                continue
            seen.add(lowered)
            items.append(item)
        if items:
            out[line_no] = sorted(items, key=lambda value: value.lower())
    return out


def split_line_machine_item(raw_item: Optional[str]) -> tuple[str, str]:
    item = clean_text(raw_item)
    if not item:
        return "", ""
    if LINE_MACHINE_ITEM_SEPARATOR in item:
        left, right = item.split(LINE_MACHINE_ITEM_SEPARATOR, 1)
        return clean_text(left), clean_text(right)
    return item, ""


def _build_line_machine_lookup(
    db: Session,
) -> tuple[Set[str], Dict[str, str], Dict[str, Dict[str, str]]]:
    allowed_lines: Set[str] = set()
    machine_type_lookup: Dict[str, str] = {}
    machine_id_lookup: Dict[str, Dict[str, str]] = {}

    for (line_no,) in db.query(MasterLine.line_no).all():
        line_val = clean_text(line_no).upper()
        if line_val:
            allowed_lines.add(line_val)

    for (machine_type,) in db.query(MasterMachineType.machine_type).all():
        machine_type_val = clean_text(machine_type)
        if machine_type_val:
            machine_type_lookup.setdefault(machine_type_val.lower(), machine_type_val)

    for machine_type, machine_id in db.query(MasterMachineId.machine_type, MasterMachineId.machine_id).all():
        machine_type_val = clean_text(machine_type)
        machine_id_val = clean_text(machine_id)
        if not machine_type_val or not machine_id_val:
            continue
        machine_type_key = machine_type_val.lower()
        canonical_type = machine_type_lookup.get(machine_type_key, machine_type_val)
        machine_type_lookup.setdefault(machine_type_key, canonical_type)
        machine_id_lookup.setdefault(machine_type_key, {})
        machine_id_lookup[machine_type_key].setdefault(machine_id_val.lower(), machine_id_val)

    return allowed_lines, machine_type_lookup, machine_id_lookup


def _sanitize_line_machine_map(
    line_machine_map: Dict[str, List[str]],
    allowed_lines: Set[str],
    machine_type_lookup: Dict[str, str],
    machine_id_lookup: Dict[str, Dict[str, str]],
) -> Dict[str, List[str]]:
    normalized = normalize_line_machine_map(line_machine_map)
    out: Dict[str, List[str]] = {}

    for line_no, raw_items in normalized.items():
        if line_no not in allowed_lines:
            continue

        kept: List[str] = []
        seen = set()
        for raw_item in raw_items:
            machine_type, machine_id = split_line_machine_item(raw_item)
            if not machine_type:
                continue

            machine_type_key = machine_type.lower()
            canonical_type = machine_type_lookup.get(machine_type_key)
            if not canonical_type:
                continue

            normalized_item = canonical_type
            if machine_id:
                canonical_id = (machine_id_lookup.get(machine_type_key) or {}).get(machine_id.lower())
                if not canonical_id:
                    continue
                normalized_item = f"{canonical_type}{LINE_MACHINE_ITEM_SEPARATOR}{canonical_id}"

            lowered = normalized_item.lower()
            if lowered in seen:
                continue
            seen.add(lowered)
            kept.append(normalized_item)

        if kept:
            out[line_no] = sorted(kept, key=lambda value: value.lower())
    return out


def _legacy_line_machine_map_path() -> Path:
    custom_path = clean_text(os.getenv(LINE_MACHINE_MAP_FILE_ENV))
    if custom_path:
        return Path(custom_path).expanduser()
    return Path(__file__).resolve().parents[1] / LEGACY_LINE_MACHINE_MAP_FILE


def _read_legacy_line_machine_map_file(path: Path) -> Dict[str, List[str]]:
    if not path.exists():
        return {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8") or "{}")
    except Exception as exc:
        APP_LOGGER.warning("Failed to read monitoring map file %s (%s)", path, exc)
        return {}
    return normalize_line_machine_map(raw)


def _parse_line_machine_map_audit_item(raw_item: Optional[str]) -> tuple[str, str]:
    text = clean_text(raw_item)
    if not text:
        return "", ""

    matched = _LINE_MACHINE_AUDIT_ITEM_PATTERN.match(text)
    if not matched:
        return "", ""

    line_val = clean_text(matched.group("line")).upper()
    machine_type = clean_text(matched.group("type"))
    machine_id = clean_text(matched.group("id"))
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

        action = clean_text(getattr(row, "action", "")).upper()
        existing = list(line_machine_map.get(line_val, []))
        if action == "DELETE":
            kept = [value for value in existing if clean_text(value).lower() != item_val.lower()]
            if kept:
                line_machine_map[line_val] = kept
            else:
                line_machine_map.pop(line_val, None)
            continue

        if not any(clean_text(value).lower() == item_val.lower() for value in existing):
            existing.append(item_val)
            line_machine_map[line_val] = existing

    return normalize_line_machine_map(line_machine_map)


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
        line_no = clean_text(row.line_no).upper()
        machine_type = clean_text(row.machine_type)
        machine_id = clean_text(row.machine_id)
        if not line_no or not machine_type:
            continue
        normalized_item = machine_type
        if machine_id and machine_id != "-":
            normalized_item = f"{machine_type}{LINE_MACHINE_ITEM_SEPARATOR}{machine_id}"
        append_unique_casefold(out.setdefault(line_no, []), normalized_item)
    return normalize_line_machine_map(out)


def _replace_line_machine_map_in_db(db: Session, line_machine_map: Dict[str, List[str]]) -> None:
    normalized = normalize_line_machine_map(line_machine_map)
    db.query(MasterLineMonitoringMap).delete(synchronize_session=False)
    for line_no, items in normalized.items():
        for raw_item in items:
            machine_type, machine_id = split_line_machine_item(raw_item)
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
        if row and clean_text(row.value):
            try:
                raw = json.loads(row.value)
            except Exception:
                raw = {}
            legacy_map = normalize_line_machine_map(raw)

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


def get_line_machine_map(db: Session) -> Dict[str, List[str]]:
    try:
        _bootstrap_line_machine_map_from_legacy_sources(db)
    except Exception as exc:
        db.rollback()
        APP_LOGGER.warning("Bootstrap line-monitoring map from legacy sources failed: %s", exc)

    db_map = _load_line_machine_map_from_db(db)
    allowed_lines, machine_type_lookup, machine_id_lookup = _build_line_machine_lookup(db)
    return _sanitize_line_machine_map(
        db_map,
        allowed_lines,
        machine_type_lookup,
        machine_id_lookup,
    )


def save_line_machine_map(db: Session, line_machine_map: Dict[str, List[str]]) -> None:
    allowed_lines, machine_type_lookup, machine_id_lookup = _build_line_machine_lookup(db)
    sanitized = _sanitize_line_machine_map(
        line_machine_map,
        allowed_lines,
        machine_type_lookup,
        machine_id_lookup,
    )
    _replace_line_machine_map_in_db(db, sanitized)

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
    return unique_clean(raw_values)


def _build_master_data_uncached(db: Session) -> Dict[str, object]:
    line_ops = unique_clean(
        [row.line_no for row in db.query(MasterLine).order_by(MasterLine.line_no.asc()).all()]
    )

    machine_type_map: Dict[str, List[str]] = {}
    problem_map: Dict[str, List[str]] = {}
    problem_combo_map: Dict[str, List[str]] = {}
    machine_id_map: Dict[str, List[str]] = {}
    support_area_map: Dict[str, List[str]] = {}
    support_areas: List[str] = []
    support_area_lookup: Dict[str, str] = {}
    machine_names = set()

    for row in db.query(MasterMachine).order_by(MasterMachine.machine.asc()).all():
        machine = clean_text(row.machine)
        if not machine:
            continue
        machine_names.add(machine)
        machine_type_map.setdefault(machine, [])
        problem_map.setdefault(machine, [])

    for row in (
        db.query(MasterMachineType)
        .order_by(MasterMachineType.machine.asc(), MasterMachineType.machine_type.asc())
        .all()
    ):
        machine = clean_text(row.machine)
        machine_type = clean_text(row.machine_type)
        if not machine:
            continue
        machine_names.add(machine)
        machine_type_map.setdefault(machine, [])
        problem_map.setdefault(machine, [])
        if machine_type:
            append_unique_casefold(machine_type_map[machine], machine_type)

    for row in (
        db.query(MasterProblem)
        .order_by(MasterProblem.machine.asc(), MasterProblem.machine_type.asc(), MasterProblem.problem.asc())
        .all()
    ):
        machine = clean_text(row.machine)
        machine_type = clean_text(row.machine_type)
        problem = clean_text(row.problem)
        if not machine or not problem:
            continue

        machine_names.add(machine)
        machine_type_map.setdefault(machine, [])
        problem_map.setdefault(machine, [])

        if machine_type:
            append_unique_casefold(machine_type_map[machine], machine_type)
            key = f"{machine}||{machine_type}"
            problem_combo_map.setdefault(key, [])
            append_unique_casefold(problem_combo_map[key], problem)
        else:
            append_unique_casefold(problem_map[machine], problem)

    for row in (
        db.query(MasterMachineId)
        .order_by(MasterMachineId.machine.asc(), MasterMachineId.machine_type.asc(), MasterMachineId.machine_id.asc())
        .all()
    ):
        machine = clean_text(row.machine)
        machine_type = clean_text(row.machine_type)
        machine_id = clean_text(row.machine_id)
        if not machine or not machine_type or not machine_id:
            continue

        machine_names.add(machine)
        machine_type_map.setdefault(machine, [])
        problem_map.setdefault(machine, [])
        append_unique_casefold(machine_type_map[machine], machine_type)

        key = f"{machine}||{machine_type}"
        machine_id_map.setdefault(key, [])
        append_unique_casefold(machine_id_map[key], machine_id)

    for row in (
        db.query(MasterSupportArea)
        .order_by(MasterSupportArea.created_at.asc(), MasterSupportArea.id.asc())
        .all()
    ):
        support_area = clean_text(row.support_area)
        if not support_area:
            continue
        lowered = support_area.lower()
        if lowered not in support_area_lookup:
            support_area_lookup[lowered] = support_area
            support_areas.append(support_area)
        support_area_map.setdefault(support_area_lookup[lowered], [])

    for row in (
        db.query(MasterSupportAreaMap)
        .order_by(MasterSupportAreaMap.created_at.asc(), MasterSupportAreaMap.id.asc())
        .all()
    ):
        support_area = clean_text(row.support_area)
        machine = clean_text(row.machine)
        if not support_area or not machine:
            continue
        canonical_area = support_area_lookup.get(support_area.lower())
        if not canonical_area:
            canonical_area = support_area
            support_area_lookup[support_area.lower()] = canonical_area
            support_areas.append(canonical_area)
        support_area_map.setdefault(canonical_area, [])
        append_unique_casefold(support_area_map[canonical_area], machine)

    machine_list = sorted(machine_names, key=lambda value: value.lower())
    for machine in machine_list:
        machine_type_map[machine] = unique_clean(machine_type_map.get(machine, []))
        problem_map[machine] = unique_clean(problem_map.get(machine, []))

    for key in list(problem_combo_map.keys()):
        problem_combo_map[key] = unique_clean(problem_combo_map.get(key, []))
    for key in list(machine_id_map.keys()):
        machine_id_map[key] = unique_clean(machine_id_map.get(key, []))
    for support_area in support_areas:
        support_area_map[support_area] = unique_clean(support_area_map.get(support_area, []))

    line_machine_map = get_line_machine_map(db)
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


def build_master_data(db: Session) -> Dict[str, object]:
    with _MASTER_DATA_LOCK:
        cached_version = _MASTER_DATA_CACHE.get("version")
        cached_data = _MASTER_DATA_CACHE.get("data")
        if cached_version == MASTER_DATA_VERSION and isinstance(cached_data, dict):
            return cached_data

    data = _build_master_data_uncached(db)

    with _MASTER_DATA_LOCK:
        _MASTER_DATA_CACHE["version"] = MASTER_DATA_VERSION
        _MASTER_DATA_CACHE["data"] = data
    return data


def master_status_text(status_key: str) -> str:
    return MASTER_STATUS_TEXT.get(status_key or "", "")


def add_master_audit(
    db: Session,
    actor: str,
    action: str,
    data_type: str,
    item: str,
    details: Optional[str] = None,
) -> None:
    db.add(
        MasterAuditLog(
            action=clean_text(action).upper(),
            data_type=clean_text(data_type).upper(),
            item=clean_text(item),
            actor=clean_text(actor) or "-",
            details=clean_text(details) or None,
        )
    )


def get_master_rows_sorted(db: Session, sort_time: str) -> Dict[str, list]:
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
