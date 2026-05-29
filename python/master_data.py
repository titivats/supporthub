"""Default master data and one-time PostgreSQL seed."""

from typing import List, Optional

from python.db import (
    AppSetting,
    MasterLine,
    MasterMachine,
    MasterMachineType,
    MasterProblem,
    MasterSupportArea,
    MasterSupportAreaMap,
    SessionLocal,
)

LINE_OPS = ["BT01", "BT02", "BT03", "BT04", "BT05", "BT06", "BT07", "BT08", "BT09"]
EXTRA_LINE_OPS = ["PACKING", "REWORK", "CLEANING"]

EQUIPMENTS = [
    "Wave Soldering", "AOI Wave", "AOI Coating", "X-ray", "RTV", "Coating",
    "Robot Packing", "Conveyor", "Auto Insertion", "Router",
    "KED Cleaning Pallet", "KED Cleaning PCB", "DCT Cleaning PCB", "Etc..",
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
    "line_machine_map_added": "Mapped Line No. to Monitoring item successfully",
    "line_machine_map_exists": "This Line No. and Monitoring item mapping already exists",
    "line_machine_map_deleted": "Deleted Line No. and Monitoring item mapping successfully",
    "line_machine_map_not_found": "Line No. and Monitoring item mapping not found",
    "invalid_input": "Please provide all required fields",
}

MASTER_SEED_KEY = "master_seed_v1"


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


def ensure_master_seeded() -> str:
    """Seed default master data once. Returns 'seeded', 'skipped', or 'error'."""
    db = None
    try:
        db = SessionLocal()
        seed_row = db.query(AppSetting).filter(AppSetting.key == MASTER_SEED_KEY).first()
        if seed_row and (seed_row.value or "").strip() == "1":
            return "skipped"

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

        def add_machine_if_missing(machine_val: str) -> None:
            key = machine_val.lower()
            if key in machine_seen:
                return
            machine_seen.add(key)
            db.add(MasterMachine(machine=machine_val))

        for line in _unique_clean(LINE_OPS + EXTRA_LINE_OPS):
            line_val = _clean_text(line).upper()
            if line_val and line_val not in line_seen:
                line_seen.add(line_val)
                db.add(MasterLine(line_no=line_val))

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
        return "seeded"
    except Exception as exc:
        print("[ERROR] ensure_master_seeded:", exc)
        return "error"
    finally:
        if db is not None:
            try:
                db.close()
            except Exception:
                pass


if __name__ == "__main__":
    import python.load_env  # noqa: F401

    from python.database.core import init_db

    init_db()
    result = ensure_master_seeded()
    if result == "seeded":
        print("[OK] Master data seeded.")
    elif result == "skipped":
        print("[OK] Already seeded (master_seed_v1). Delete that row in app_settings to run again.")
    else:
        raise SystemExit(1)
