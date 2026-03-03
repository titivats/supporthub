# server_app.py

from datetime import datetime, time
from typing import Optional, List, Dict
import io
import threading

from fastapi import FastAPI, Request, Form, Depends, HTTPException, Query
from fastapi.responses import HTMLResponse, RedirectResponse, StreamingResponse

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
    SessionLocal,
    Ticket,
    TicketTakeoverLog,
    User,
    get_db,
    init_db,
)
from python.notify import line_notify
from python.OEE.oee_metrics import build_monitoring_metrics, parse_th_date_range
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

# ---------- Database (SQLite) ----------
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
    # à¹ƒà¸Šà¹‰à¸à¸±à¸šà¸ªà¸„à¸£à¸´à¸›à¸•à¹Œà¸«à¸™à¹‰à¸² index.html à¹€à¸žà¸·à¹ˆà¸­à¸•à¸£à¸§à¸ˆà¸à¸²à¸£à¹€à¸›à¸¥à¸µà¹ˆà¸¢à¸™à¹à¸›à¸¥à¸‡à¹à¸šà¸šà¹€à¸šà¸²à¹†
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
        if machine_type and machine_type.lower() not in [t.lower() for t in machine_type_map[machine]]:
            machine_type_map[machine].append(machine_type)

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
            if machine_type.lower() not in [t.lower() for t in machine_type_map[machine]]:
                machine_type_map[machine].append(machine_type)
            key = f"{machine}||{machine_type}"
            problem_combo_map.setdefault(key, [])
            if problem.lower() not in [p.lower() for p in problem_combo_map[key]]:
                problem_combo_map[key].append(problem)
        else:
            if problem.lower() not in [p.lower() for p in problem_map[machine]]:
                problem_map[machine].append(problem)

    for row in db.query(MasterMachineId).order_by(MasterMachineId.machine.asc(), MasterMachineId.machine_type.asc(), MasterMachineId.machine_id.asc()).all():
        machine = _clean_text(row.machine)
        machine_type = _clean_text(row.machine_type)
        machine_id = _clean_text(row.machine_id)
        if not machine or not machine_type or not machine_id:
            continue

        machine_names.add(machine)
        machine_type_map.setdefault(machine, [])
        problem_map.setdefault(machine, [])
        if machine_type.lower() not in [t.lower() for t in machine_type_map[machine]]:
            machine_type_map[machine].append(machine_type)

        key = f"{machine}||{machine_type}"
        machine_id_map.setdefault(key, [])
        if machine_id.lower() not in [m.lower() for m in machine_id_map[key]]:
            machine_id_map[key].append(machine_id)

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
        if machine.lower() not in [m.lower() for m in support_area_map[canonical_area]]:
            support_area_map[canonical_area].append(machine)

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

    return {
        "line_ops": line_ops,
        "machine_type_map": machine_type_map,
        "machine_id_map": machine_id_map,
        "support_areas": support_areas,
        "support_area_map": support_area_map,
        "problem_map": problem_map,
        "problem_combo_map": problem_combo_map,
        "machine_list": machine_list,
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
    if newest:
        return {
            "line_rows": db.query(MasterLine).order_by(MasterLine.created_at.desc(), MasterLine.id.desc()).all(),
            "machine_rows": db.query(MasterMachine).order_by(MasterMachine.created_at.desc(), MasterMachine.id.desc()).all(),
            "machine_type_rows": db.query(MasterMachineType).order_by(MasterMachineType.created_at.desc(), MasterMachineType.id.desc()).all(),
            "machine_id_rows": db.query(MasterMachineId).order_by(MasterMachineId.created_at.desc(), MasterMachineId.id.desc()).all(),
            "support_area_rows": db.query(MasterSupportArea).order_by(MasterSupportArea.created_at.desc(), MasterSupportArea.id.desc()).all(),
            "support_area_map_rows": db.query(MasterSupportAreaMap).order_by(MasterSupportAreaMap.created_at.desc(), MasterSupportAreaMap.id.desc()).all(),
            "problem_rows": db.query(MasterProblem).order_by(MasterProblem.created_at.desc(), MasterProblem.id.desc()).all(),
            "audit_rows": db.query(MasterAuditLog).order_by(MasterAuditLog.created_at.desc(), MasterAuditLog.id.desc()).all(),
        }
    return {
        "line_rows": db.query(MasterLine).order_by(MasterLine.created_at.asc(), MasterLine.id.asc()).all(),
        "machine_rows": db.query(MasterMachine).order_by(MasterMachine.created_at.asc(), MasterMachine.id.asc()).all(),
        "machine_type_rows": db.query(MasterMachineType).order_by(MasterMachineType.created_at.asc(), MasterMachineType.id.asc()).all(),
        "machine_id_rows": db.query(MasterMachineId).order_by(MasterMachineId.created_at.asc(), MasterMachineId.id.asc()).all(),
        "support_area_rows": db.query(MasterSupportArea).order_by(MasterSupportArea.created_at.asc(), MasterSupportArea.id.asc()).all(),
        "support_area_map_rows": db.query(MasterSupportAreaMap).order_by(MasterSupportAreaMap.created_at.asc(), MasterSupportAreaMap.id.asc()).all(),
        "problem_rows": db.query(MasterProblem).order_by(MasterProblem.created_at.asc(), MasterProblem.id.asc()).all(),
        "audit_rows": db.query(MasterAuditLog).order_by(MasterAuditLog.created_at.asc(), MasterAuditLog.id.asc()).all(),
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
        "TH_OFFSET": TH_OFFSET,
        "_fmt_hms": _fmt_hms,
        "fmt_th": fmt_th,
        "_clean_text": _clean_text,
        "_is_admin_user": _is_admin_user,
        "_build_master_data": _build_master_data,
        "_master_status_text": _master_status_text,
        "_add_master_audit": _add_master_audit,
        "_get_master_rows_sorted": _get_master_rows_sorted,
        "bump_active_version": bump_active_version,
        "EQUIPMENTS": EQUIPMENTS,
        "iot_monitor": iot_monitor,
    },
)
