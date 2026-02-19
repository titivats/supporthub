# server_app.py

from datetime import datetime, timedelta, time
from typing import Optional, List, Dict
import os, re, hmac, hashlib, io, threading

from fastapi import FastAPI, Request, Form, Depends, HTTPException, Query
from fastapi.responses import HTMLResponse, RedirectResponse, StreamingResponse

from sqlalchemy import create_engine, Column, Integer, String, DateTime, Text, UniqueConstraint, event
from sqlalchemy.orm import sessionmaker, declarative_base, Session

from itsdangerous import TimestampSigner, BadSignature
import requests

app = FastAPI(title="SupportHub")
from fastapi.templating import Jinja2Templates
templates = Jinja2Templates(directory="templates")

# ---------- Database (SQLite) ----------
DATABASE_URL = "sqlite:///E:/Data/Web/supporthub/supporthub.db"  # ใช้พาธเต็ม กัน DB หลุดไป System32
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)
Base = declarative_base()

@event.listens_for(engine, "connect")
def set_sqlite_pragma(dbapi_conn, connection_record):
    cur = dbapi_conn.cursor()
    try:
        cur.execute("PRAGMA journal_mode=WAL")
        cur.execute("PRAGMA synchronous=NORMAL")
        cur.execute("PRAGMA busy_timeout=5000")
        cur.execute("PRAGMA foreign_keys=ON")
    finally:
        cur.close()

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True)
    username = Column(String(50), nullable=False)
    password_hash = Column(String(128), nullable=False)
    role = Column(String(20), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    __table_args__ = (UniqueConstraint("username", name="uq_username"),)

class Ticket(Base):
    __tablename__ = "tickets"
    id = Column(Integer, primary_key=True)

    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    closed_at  = Column(DateTime, nullable=True)

    requester  = Column(String(50), nullable=False)
    machine    = Column(String(50), nullable=True)     # Line No.
    equipment  = Column(String(200), nullable=True)    # Machine (type||brand)
    machine_id = Column(String(100), nullable=True)
    problem    = Column(String(100), nullable=True)
    description = Column(Text, nullable=True)

    status = Column(String(12), default="PENDING", nullable=False)  # PENDING/DOING/HOLD/DONE/CANCELLED
    doing_started_at = Column(DateTime, nullable=True)
    hold_started_at  = Column(DateTime, nullable=True)
    doing_secs       = Column(Integer, default=0, nullable=False)
    hold_secs        = Column(Integer, default=0, nullable=False)

    current_actor = Column(String(50), nullable=True)
    last_action   = Column(String(10), nullable=True)
    hold_reason   = Column(Text, nullable=True)
    solution      = Column(Text, nullable=True)
    done_by       = Column(String(50), nullable=True)
    cancel_reason = Column(Text, nullable=True)
    canceled_by   = Column(String(50), nullable=True)

    def _acc_doing_until_now(self, now=None):
        if self.doing_started_at:
            now = now or datetime.utcnow()
            self.doing_secs += int((now - self.doing_started_at).total_seconds())
            self.doing_started_at = None

    def _acc_hold_until_now(self, now=None):
        if self.hold_started_at:
            now = now or datetime.utcnow()
            self.hold_secs += int((now - self.hold_started_at).total_seconds())
            self.hold_started_at = None

    def start_doing(self):
        self._acc_hold_until_now()
        self.doing_started_at = datetime.utcnow()
        self.status = "DOING"

    def start_hold(self, reason: str):
        self._acc_doing_until_now()
        self.hold_started_at = datetime.utcnow()
        self.hold_reason = (reason or "").strip()
        self.status = "HOLD"

    def done(self, solution: str, by: str):
        now = datetime.utcnow()
        self._acc_doing_until_now(now)
        self._acc_hold_until_now(now)
        self.status = "DONE"
        self.closed_at = now
        self.solution = (solution or "").strip()
        self.done_by = by

    def cancel(self, reason: str, by: str):
        now = datetime.utcnow()
        self._acc_doing_until_now(now)
        self._acc_hold_until_now(now)
        self.status = "CANCELLED"
        self.closed_at = now
        self.cancel_reason = (reason or "").strip()
        self.canceled_by = by

class MasterLine(Base):
    __tablename__ = "master_lines"
    id = Column(Integer, primary_key=True)
    line_no = Column(String(50), nullable=False, unique=True, index=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

class MasterMachine(Base):
    __tablename__ = "master_machines"
    id = Column(Integer, primary_key=True)
    machine = Column(String(100), nullable=False, unique=True, index=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

class MasterMachineType(Base):
    __tablename__ = "master_machine_types"
    id = Column(Integer, primary_key=True)
    machine = Column(String(100), nullable=False, index=True)
    machine_type = Column(String(100), nullable=False, index=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    __table_args__ = (UniqueConstraint("machine", "machine_type", name="uq_master_machine_type"),)

class MasterProblem(Base):
    __tablename__ = "master_problems"
    id = Column(Integer, primary_key=True)
    machine = Column(String(100), nullable=False, index=True)
    machine_type = Column(String(100), nullable=True, index=True)
    problem = Column(String(150), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    __table_args__ = (UniqueConstraint("machine", "machine_type", "problem", name="uq_master_problem"),)

class MasterMachineId(Base):
    __tablename__ = "master_machine_ids"
    id = Column(Integer, primary_key=True)
    machine = Column(String(100), nullable=False, index=True)
    machine_type = Column(String(100), nullable=False, index=True)
    machine_id = Column(String(100), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    __table_args__ = (UniqueConstraint("machine", "machine_type", "machine_id", name="uq_master_machine_id"),)

class MasterSupportArea(Base):
    __tablename__ = "master_support_areas"
    id = Column(Integer, primary_key=True)
    support_area = Column(String(100), nullable=False, unique=True, index=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

class MasterSupportAreaMap(Base):
    __tablename__ = "master_support_area_maps"
    id = Column(Integer, primary_key=True)
    support_area = Column(String(100), nullable=False, index=True)
    machine = Column(String(100), nullable=False, index=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    __table_args__ = (UniqueConstraint("support_area", "machine", name="uq_master_support_area_machine"),)

class AppSetting(Base):
    __tablename__ = "app_settings"
    id = Column(Integer, primary_key=True)
    key = Column(String(100), nullable=False, unique=True, index=True)
    value = Column(String(200), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

Base.metadata.create_all(bind=engine)

def _ensure_columns_and_indexes():
    with engine.connect() as con:
        cols = {r[1] for r in con.exec_driver_sql("PRAGMA table_info(tickets)").fetchall()}
        need = {
            "equipment": "TEXT",
            "machine_id": "TEXT",
            "problem": "TEXT",
            "status": "TEXT DEFAULT 'PENDING'",
            "doing_started_at": "DATETIME",
            "hold_started_at": "DATETIME",
            "doing_secs": "INTEGER DEFAULT 0",
            "hold_secs": "INTEGER DEFAULT 0",
            "current_actor": "TEXT",
            "last_action": "TEXT",
            "hold_reason": "TEXT",
            "solution": "TEXT",
            "done_by": "TEXT",
            "cancel_reason": "TEXT",
            "canceled_by": "TEXT",
        }
        for c, typ in need.items():
            if c not in cols:
                con.exec_driver_sql(f"ALTER TABLE tickets ADD COLUMN {c} {typ}")
        con.exec_driver_sql("CREATE INDEX IF NOT EXISTS idx_tickets_status ON tickets(status)")
        con.exec_driver_sql("CREATE INDEX IF NOT EXISTS idx_tickets_closed_at ON tickets(closed_at)")
        con.exec_driver_sql("CREATE INDEX IF NOT EXISTS idx_tickets_machine ON tickets(machine)")
        con.exec_driver_sql("CREATE INDEX IF NOT EXISTS idx_tickets_machine_id ON tickets(machine_id)")
_ensure_columns_and_indexes()

# ---------- Auth helpers ----------
SECRET = os.getenv("SUPPORTHUB_SECRET", "supporthub-secret")
signer = TimestampSigner(SECRET)
HEX64 = re.compile(r"^[0-9a-f]{64}$", re.I)

SESSION_AGE = int(os.getenv("SUPPORTHUB_SESSION_AGE", str(60*60*24*7)))  # 7 วัน
SECURE_COOKIES = os.getenv("SUPPORTHUB_SECURE_COOKIES", "false").lower() in ("1","true","yes","on")

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def sha256(s: str) -> str:
    return hashlib.sha256(s.encode()).hexdigest()

def verify_password(plain: str, stored: str) -> bool:
    # รองรับทั้งแบบ hash และเคสเก่าแบบ plaintext
    plain, stored = (plain or "").strip(), (stored or "").strip()
    if HEX64.match(stored):
        return hmac.compare_digest(sha256(plain), stored.lower())
    return hmac.compare_digest(plain, stored)

def _ensure_admin_user():
    try:
        db = SessionLocal()
        admin = db.query(User).filter(User.username == "ADMIN").first()
        target_hash = sha256("259487123")
        if not admin:
            admin = User(username="ADMIN", password_hash=target_hash, role="Admin")
            db.add(admin); db.commit()
        else:
            changed = False
            if admin.password_hash != target_hash:
                admin.password_hash = target_hash; changed = True
            if admin.role != "Admin":
                admin.role = "Admin"; changed = True
            if changed:
                db.add(admin); db.commit()
    except Exception as e:
        print("[INIT] _ensure_admin_user error:", e)
    finally:
        try: db.close()
        except: pass

_ensure_admin_user()

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
    # ใช้กับสคริปต์หน้า index.html เพื่อตรวจการเปลี่ยนแปลงแบบเบาๆ
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
        }
    return {
        "line_rows": db.query(MasterLine).order_by(MasterLine.created_at.asc(), MasterLine.id.asc()).all(),
        "machine_rows": db.query(MasterMachine).order_by(MasterMachine.created_at.asc(), MasterMachine.id.asc()).all(),
        "machine_type_rows": db.query(MasterMachineType).order_by(MasterMachineType.created_at.asc(), MasterMachineType.id.asc()).all(),
        "machine_id_rows": db.query(MasterMachineId).order_by(MasterMachineId.created_at.asc(), MasterMachineId.id.asc()).all(),
        "support_area_rows": db.query(MasterSupportArea).order_by(MasterSupportArea.created_at.asc(), MasterSupportArea.id.asc()).all(),
        "support_area_map_rows": db.query(MasterSupportAreaMap).order_by(MasterSupportAreaMap.created_at.asc(), MasterSupportAreaMap.id.asc()).all(),
        "problem_rows": db.query(MasterProblem).order_by(MasterProblem.created_at.asc(), MasterProblem.id.asc()).all(),
    }

# ---------- Utils ----------
TH_OFFSET = timedelta(hours=7)
def to_th(dt: datetime | None) -> datetime | None:
    return (dt + TH_OFFSET) if dt else None
def fmt_th(dt: datetime | None) -> str:
    d = to_th(dt)
    return d.strftime("%d-%m-%Y %H:%M:%S") if d else ""
def _fmt_hms(sec: int) -> str:
    s = int(sec or 0); h=s//3600; m=(s%3600)//60; ss=s%60
    return f"{h:02d}:{m:02d}:{ss:02d}"

# ---------- LINE Notify (optional) ----------
LINE_TOKEN = os.getenv("LINE_NOTIFY_TOKEN", "").strip()
def line_notify(message: str):
    if not LINE_TOKEN: return
    try:
        requests.post(
            "https://notify-api.line.me/api/notify",
            headers={"Authorization": f"Bearer {LINE_TOKEN}"},
            data={"message": message},
            timeout=3.0
        )
    except Exception:
        pass

# ---------- Auth routes ----------
@app.get("/login", response_class=HTMLResponse)
def login_page(request: Request):
    created = request.query_params.get("created") == "1"
    return templates.TemplateResponse("login.html", {"request": request, "error": None, "created": created})

@app.post("/login")
def do_login(request: Request, username: str = Form(...), password: str = Form(...), db: Session = Depends(get_db)):
    user = db.query(User).filter(User.username == username.strip()).first()
    if not user or not verify_password(password, user.password_hash):
        return templates.TemplateResponse("login.html", {"request": request, "error": "ชื่อผู้ใช้หรือรหัสผ่านไม่ถูกต้อง", "created": False}, status_code=400)
    token = TimestampSigner(SECRET).sign(user.username).decode()
    resp = RedirectResponse("/", status_code=303)
    resp.set_cookie("session", token, httponly=True, samesite="lax", secure=SECURE_COOKIES, max_age=SESSION_AGE)
    return resp

@app.get("/logout")
def logout():
    resp = RedirectResponse("/login", status_code=303)
    resp.delete_cookie("session")
    return resp

@app.get("/signup", response_class=HTMLResponse)
def signup_page(request: Request):
    return templates.TemplateResponse("add_user.html", {"request": request, "error": None})

@app.post("/signup")
def do_signup(username: str = Form(...), password: str = Form(...), role: str = Form("Operator"), db: Session = Depends(get_db)):
    username = username.strip()
    if not username or not password:
        return templates.TemplateResponse("add_user.html", {"request": {}, "error": "กรอกข้อมูลให้ครบ"}, status_code=400)
    if db.query(User).filter(User.username == username).first():
        return templates.TemplateResponse("add_user.html", {"request": {}, "error": "Username ซ้ำ"}, status_code=400)
    db.add(User(username=username, password_hash=sha256(password), role=role)); db.commit()
    return RedirectResponse("/login?created=1", status_code=303)

# ---------- Admin: Users ----------
@app.get("/admin/users", response_class=HTMLResponse)
def admin_users(request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if user.role.lower() != "admin" and user.username.upper() != "ADMIN":
        raise HTTPException(status_code=403, detail="Forbidden")
    users = db.query(User).order_by(User.username.asc()).all()
    users_sorted = sorted(users, key=lambda u: (u.username.upper() != "ADMIN", u.username.lower()))
    pw_updated = request.query_params.get("pw_updated") == "1"
    return templates.TemplateResponse("manage_users.html", {
        "request": request, "me": user, "users": users_sorted, "pw_updated": pw_updated, "fmt_th": fmt_th,
    })

@app.post("/admin/users/create")
def admin_create_user(request: Request,
                      username: str = Form(...),
                      password: str = Form(...),
                      role: str = Form(...),
                      db: Session = Depends(get_db)):
    me = get_current_user(request, db)
    if me.role.lower() != "admin" and me.username.upper() != "ADMIN":
        raise HTTPException(status_code=403, detail="Forbidden")
    username = username.strip()
    if not username or not password:
        raise HTTPException(status_code=400, detail="invalid params")
    if db.query(User).filter(User.username == username).first():
        raise HTTPException(status_code=400, detail="duplicated")
    u = User(username=username, password_hash=sha256(password), role=role)
    db.add(u); db.commit()
    return RedirectResponse("/admin/users", status_code=303)

@app.post("/admin/users/update/{user_id}")
def admin_update_user(user_id: int,
                      request: Request,
                      role: str = Form(...),
                      new_password: Optional[str] = Form(None),
                      db: Session = Depends(get_db)):
    me = get_current_user(request, db)
    if me.role.lower() != "admin" and me.username.upper() != "ADMIN":
        raise HTTPException(status_code=403, detail="Forbidden")

    u = db.query(User).filter(User.id == user_id).first()
    if not u: raise HTTPException(status_code=404, detail="not found")
    if u.username.upper() == "ADMIN" and (me.username.upper() != "ADMIN"):
        raise HTTPException(status_code=403, detail="Cannot edit ADMIN")

    u.role = role
    if new_password and new_password.strip():
        u.password_hash = sha256(new_password.strip())
        u.created_at = datetime.utcnow()
        db.add(u); db.commit()
        return RedirectResponse("/admin/users?pw_updated=1", status_code=303)

    db.add(u); db.commit()
    return RedirectResponse("/admin/users", status_code=303)

@app.post("/admin/users/delete/{user_id}")
def admin_delete_user(user_id: int, request: Request, db: Session = Depends(get_db)):
    me = get_current_user(request, db)
    if me.role.lower() != "admin" and me.username.upper() != "ADMIN":
        raise HTTPException(status_code=403, detail="Forbidden")
    u = db.query(User).filter(User.id == user_id).first()
    if not u: raise HTTPException(status_code=404, detail="not found")
    if u.username.upper() == "ADMIN":
        raise HTTPException(status_code=400, detail="ADMIN cannot be deleted")
    db.delete(u); db.commit()
    return RedirectResponse("/admin/users", status_code=303)

@app.get("/admin/machines", response_class=HTMLResponse)
def admin_machines(request: Request, db: Session = Depends(get_db)):
    me = get_current_user(request, db)
    if not _is_admin_user(me):
        raise HTTPException(status_code=403, detail="Forbidden")

    master = _build_master_data(db)
    status = request.query_params.get("status", "")
    rows = _get_master_rows_sorted(db, "desc")

    return templates.TemplateResponse("manage_machines.html", {
        "request": request,
        "me": me,
        "line_rows": rows["line_rows"],
        "machine_rows": rows["machine_rows"],
        "machine_type_rows": rows["machine_type_rows"],
        "machine_id_rows": rows["machine_id_rows"],
        "support_area_rows": rows["support_area_rows"],
        "support_area_map_rows": rows["support_area_map_rows"],
        "problem_rows": rows["problem_rows"],
        "machine_options": master["machine_list"],
        "support_area_options": master["support_areas"],
        "machine_type_map": master["machine_type_map"],
        "machine_id_map": master["machine_id_map"],
        "support_area_map": master["support_area_map"],
        "status_text": _master_status_text(status),
        "status_key": status,
        "fmt_th": fmt_th,
    })

@app.get("/admin/machines/export/excel")
def admin_export_machines_excel(request: Request, db: Session = Depends(get_db)):
    me = get_current_user(request, db)
    if not _is_admin_user(me):
        raise HTTPException(status_code=403, detail="Forbidden")

    import xlsxwriter

    rows = _get_master_rows_sorted(db, "desc")
    line_rows = rows["line_rows"]
    machine_rows = rows["machine_rows"]
    machine_type_rows = rows["machine_type_rows"]
    machine_id_rows = rows["machine_id_rows"]
    support_area_rows = rows["support_area_rows"]
    support_area_map_rows = rows["support_area_map_rows"]
    problem_rows = rows["problem_rows"]

    buf = io.BytesIO()
    wb = xlsxwriter.Workbook(buf, {'in_memory': True})

    hdr = wb.add_format({'bold': True, 'bg_color': '#EEF2FF', 'border': 1})
    cell = wb.add_format({'border': 1})

    def make_sheet(name: str, headers: List[str], rows: List[List[str]], widths: List[int]):
        ws = wb.add_worksheet(name[:31])
        ws.freeze_panes(1, 0)
        ws.autofilter(0, 0, 0, len(headers) - 1)

        for c, h in enumerate(headers):
            ws.write(0, c, h, hdr)
        for r, row_data in enumerate(rows, start=1):
            for c, value in enumerate(row_data):
                ws.write(r, c, value, cell)
        for c, w in enumerate(widths):
            ws.set_column(c, c, w)

    make_sheet(
        "Line No.",
        ["Line No.", "Created (TH)"],
        [[r.line_no or "-", fmt_th(r.created_at)] for r in line_rows],
        [24, 20],
    )
    make_sheet(
        "Machine",
        ["Machine", "Created (TH)"],
        [[r.machine or "-", fmt_th(r.created_at)] for r in machine_rows],
        [30, 20],
    )
    make_sheet(
        "Machine Type",
        ["Machine", "Machine Type", "Created (TH)"],
        [[r.machine or "-", r.machine_type or "-", fmt_th(r.created_at)] for r in machine_type_rows],
        [26, 30, 20],
    )
    make_sheet(
        "Machine ID",
        ["Machine", "Machine Type", "Machine ID", "Created (TH)"],
        [[r.machine or "-", r.machine_type or "-", r.machine_id or "-", fmt_th(r.created_at)] for r in machine_id_rows],
        [24, 26, 22, 20],
    )
    make_sheet(
        "Support Area",
        ["Support Area", "Created (TH)"],
        [[r.support_area or "-", fmt_th(r.created_at)] for r in support_area_rows],
        [26, 20],
    )
    make_sheet(
        "Support Area Map",
        ["Support Area", "Machine", "Created (TH)"],
        [[r.support_area or "-", r.machine or "-", fmt_th(r.created_at)] for r in support_area_map_rows],
        [26, 28, 20],
    )
    make_sheet(
        "Problem",
        ["Machine", "Machine Type", "Problem", "Created (TH)"],
        [[r.machine or "-", r.machine_type or "-", r.problem or "-", fmt_th(r.created_at)] for r in problem_rows],
        [24, 26, 36, 20],
    )

    wb.close()
    buf.seek(0)

    filename = f'master_data_{datetime.utcnow().strftime("%Y%m%d_%H%M%S")}.xlsx'
    return StreamingResponse(
        buf,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )

@app.post("/admin/machines/add-support-area")
def admin_add_support_area(request: Request, support_area: str = Form(...), db: Session = Depends(get_db)):
    me = get_current_user(request, db)
    if not _is_admin_user(me):
        raise HTTPException(status_code=403, detail="Forbidden")

    area_val = _clean_text(support_area)
    if not area_val:
        return RedirectResponse("/admin/machines?status=invalid_input", status_code=303)

    exists = db.query(MasterSupportArea).filter(MasterSupportArea.support_area == area_val).first()
    if exists:
        return RedirectResponse("/admin/machines?status=support_area_exists", status_code=303)

    db.add(MasterSupportArea(support_area=area_val))
    db.commit()
    bump_active_version()
    return RedirectResponse("/admin/machines?status=support_area_added", status_code=303)

@app.post("/admin/machines/add-support-area-machine")
def admin_add_support_area_machine(request: Request,
                                   support_area: str = Form(...),
                                   machine: str = Form(...),
                                   db: Session = Depends(get_db)):
    me = get_current_user(request, db)
    if not _is_admin_user(me):
        raise HTTPException(status_code=403, detail="Forbidden")

    area_val = _clean_text(support_area)
    machine_val = _clean_text(machine)
    if not area_val or not machine_val:
        return RedirectResponse("/admin/machines?status=invalid_input", status_code=303)

    area_exists = db.query(MasterSupportArea).filter(MasterSupportArea.support_area == area_val).first()
    if not area_exists:
        db.add(MasterSupportArea(support_area=area_val))

    machine_exists = db.query(MasterMachine).filter(MasterMachine.machine == machine_val).first()
    if not machine_exists:
        db.add(MasterMachine(machine=machine_val))

    exists = db.query(MasterSupportAreaMap).filter(
        MasterSupportAreaMap.support_area == area_val,
        MasterSupportAreaMap.machine == machine_val,
    ).first()
    if exists:
        return RedirectResponse("/admin/machines?status=support_area_map_exists", status_code=303)

    db.add(MasterSupportAreaMap(support_area=area_val, machine=machine_val))
    db.commit()
    bump_active_version()
    return RedirectResponse("/admin/machines?status=support_area_map_added", status_code=303)

@app.post("/admin/machines/delete-support-area-machine")
def admin_delete_support_area_machine(request: Request, map_id: int = Form(...), db: Session = Depends(get_db)):
    me = get_current_user(request, db)
    if not _is_admin_user(me):
        raise HTTPException(status_code=403, detail="Forbidden")

    row = db.query(MasterSupportAreaMap).filter(MasterSupportAreaMap.id == map_id).first()
    if not row:
        return RedirectResponse("/admin/machines?status=support_area_map_not_found", status_code=303)

    db.delete(row)
    db.commit()
    bump_active_version()
    return RedirectResponse("/admin/machines?status=support_area_map_deleted", status_code=303)

@app.post("/admin/machines/delete-support-area")
def admin_delete_support_area(request: Request, support_area_id: int = Form(...), db: Session = Depends(get_db)):
    me = get_current_user(request, db)
    if not _is_admin_user(me):
        raise HTTPException(status_code=403, detail="Forbidden")

    row = db.query(MasterSupportArea).filter(MasterSupportArea.id == support_area_id).first()
    if not row:
        return RedirectResponse("/admin/machines?status=support_area_not_found", status_code=303)

    area_val = _clean_text(row.support_area)
    if area_val:
        db.query(MasterSupportAreaMap).filter(MasterSupportAreaMap.support_area == area_val).delete(synchronize_session=False)
    db.delete(row)
    db.commit()
    bump_active_version()
    return RedirectResponse("/admin/machines?status=support_area_deleted", status_code=303)

@app.post("/admin/machines/delete-line")
def admin_delete_line(request: Request, line_id: int = Form(...), db: Session = Depends(get_db)):
    me = get_current_user(request, db)
    if not _is_admin_user(me):
        raise HTTPException(status_code=403, detail="Forbidden")

    row = db.query(MasterLine).filter(MasterLine.id == line_id).first()
    if not row:
        return RedirectResponse("/admin/machines?status=line_not_found", status_code=303)

    db.delete(row)
    db.commit()
    bump_active_version()
    return RedirectResponse("/admin/machines?status=line_deleted", status_code=303)

@app.post("/admin/machines/delete-machine")
def admin_delete_machine(request: Request, machine_row_id: int = Form(...), db: Session = Depends(get_db)):
    me = get_current_user(request, db)
    if not _is_admin_user(me):
        raise HTTPException(status_code=403, detail="Forbidden")

    row = db.query(MasterMachine).filter(MasterMachine.id == machine_row_id).first()
    if not row:
        return RedirectResponse("/admin/machines?status=machine_not_found", status_code=303)

    machine_val = _clean_text(row.machine)
    if machine_val:
        db.query(MasterSupportAreaMap).filter(MasterSupportAreaMap.machine == machine_val).delete(synchronize_session=False)
        db.query(MasterMachineId).filter(MasterMachineId.machine == machine_val).delete(synchronize_session=False)
        db.query(MasterMachineType).filter(MasterMachineType.machine == machine_val).delete(synchronize_session=False)
        db.query(MasterProblem).filter(MasterProblem.machine == machine_val).delete(synchronize_session=False)
    db.delete(row)
    db.commit()
    bump_active_version()
    return RedirectResponse("/admin/machines?status=machine_deleted", status_code=303)

@app.post("/admin/machines/delete-machine-type")
def admin_delete_machine_type(request: Request, machine_type_id: int = Form(...), db: Session = Depends(get_db)):
    me = get_current_user(request, db)
    if not _is_admin_user(me):
        raise HTTPException(status_code=403, detail="Forbidden")

    row = db.query(MasterMachineType).filter(MasterMachineType.id == machine_type_id).first()
    if not row:
        return RedirectResponse("/admin/machines?status=machine_type_not_found", status_code=303)

    machine_val = _clean_text(row.machine)
    machine_type_val = _clean_text(row.machine_type)
    if machine_val and machine_type_val:
        db.query(MasterMachineId).filter(
            MasterMachineId.machine == machine_val,
            MasterMachineId.machine_type == machine_type_val,
        ).delete(synchronize_session=False)
        db.query(MasterProblem).filter(
            MasterProblem.machine == machine_val,
            MasterProblem.machine_type == machine_type_val,
        ).delete(synchronize_session=False)
    db.delete(row)
    db.commit()
    bump_active_version()
    return RedirectResponse("/admin/machines?status=machine_type_deleted", status_code=303)

@app.post("/admin/machines/delete-machine-id")
def admin_delete_machine_id(request: Request, machine_id_row_id: int = Form(...), db: Session = Depends(get_db)):
    me = get_current_user(request, db)
    if not _is_admin_user(me):
        raise HTTPException(status_code=403, detail="Forbidden")

    row = db.query(MasterMachineId).filter(MasterMachineId.id == machine_id_row_id).first()
    if not row:
        return RedirectResponse("/admin/machines?status=machine_id_not_found", status_code=303)

    db.delete(row)
    db.commit()
    bump_active_version()
    return RedirectResponse("/admin/machines?status=machine_id_deleted", status_code=303)

@app.post("/admin/machines/delete-problem")
def admin_delete_problem(request: Request, problem_id: int = Form(...), db: Session = Depends(get_db)):
    me = get_current_user(request, db)
    if not _is_admin_user(me):
        raise HTTPException(status_code=403, detail="Forbidden")

    row = db.query(MasterProblem).filter(MasterProblem.id == problem_id).first()
    if not row:
        return RedirectResponse("/admin/machines?status=problem_not_found", status_code=303)

    db.delete(row)
    db.commit()
    bump_active_version()
    return RedirectResponse("/admin/machines?status=problem_deleted", status_code=303)

@app.post("/admin/machines/add-line")
def admin_add_line(request: Request, line_no: str = Form(...), db: Session = Depends(get_db)):
    me = get_current_user(request, db)
    if not _is_admin_user(me):
        raise HTTPException(status_code=403, detail="Forbidden")

    val = _clean_text(line_no).upper()
    if not val:
        return RedirectResponse("/admin/machines?status=invalid_input", status_code=303)

    exists = db.query(MasterLine).filter(MasterLine.line_no == val).first()
    if exists:
        return RedirectResponse("/admin/machines?status=line_exists", status_code=303)

    db.add(MasterLine(line_no=val))
    db.commit()
    bump_active_version()
    return RedirectResponse("/admin/machines?status=line_added", status_code=303)

@app.post("/admin/machines/add-machine")
def admin_add_machine(request: Request, machine: str = Form(...), db: Session = Depends(get_db)):
    me = get_current_user(request, db)
    if not _is_admin_user(me):
        raise HTTPException(status_code=403, detail="Forbidden")

    machine_val = _clean_text(machine)
    if not machine_val:
        return RedirectResponse("/admin/machines?status=invalid_input", status_code=303)

    exists = db.query(MasterMachine).filter(MasterMachine.machine == machine_val).first()
    if exists:
        return RedirectResponse("/admin/machines?status=machine_exists", status_code=303)

    db.add(MasterMachine(machine=machine_val))
    db.commit()
    bump_active_version()
    return RedirectResponse("/admin/machines?status=machine_added", status_code=303)

@app.post("/admin/machines/add-machine-type")
def admin_add_machine_type(request: Request,
                           machine: str = Form(...),
                           machine_type: str = Form(...),
                           db: Session = Depends(get_db)):
    me = get_current_user(request, db)
    if not _is_admin_user(me):
        raise HTTPException(status_code=403, detail="Forbidden")

    machine_val = _clean_text(machine)
    machine_type_val = _clean_text(machine_type)
    if not machine_val or not machine_type_val:
        return RedirectResponse("/admin/machines?status=invalid_input", status_code=303)

    m_exists = db.query(MasterMachine).filter(MasterMachine.machine == machine_val).first()
    if not m_exists:
        db.add(MasterMachine(machine=machine_val))

    exists = db.query(MasterMachineType).filter(
        MasterMachineType.machine == machine_val,
        MasterMachineType.machine_type == machine_type_val,
    ).first()
    if exists:
        return RedirectResponse("/admin/machines?status=machine_type_exists", status_code=303)

    db.add(MasterMachineType(machine=machine_val, machine_type=machine_type_val))
    db.commit()
    bump_active_version()
    return RedirectResponse("/admin/machines?status=machine_type_added", status_code=303)

@app.post("/admin/machines/add-machine-id")
def admin_add_machine_id(request: Request,
                         machine: str = Form(...),
                         machine_type: str = Form(...),
                         machine_id: str = Form(...),
                         db: Session = Depends(get_db)):
    me = get_current_user(request, db)
    if not _is_admin_user(me):
        raise HTTPException(status_code=403, detail="Forbidden")

    machine_val = _clean_text(machine)
    machine_type_val = _clean_text(machine_type)
    machine_id_val = _clean_text(machine_id)
    if not machine_val or not machine_type_val or not machine_id_val:
        return RedirectResponse("/admin/machines?status=invalid_input", status_code=303)

    m_exists = db.query(MasterMachine).filter(MasterMachine.machine == machine_val).first()
    if not m_exists:
        db.add(MasterMachine(machine=machine_val))

    mt_exists = db.query(MasterMachineType).filter(
        MasterMachineType.machine == machine_val,
        MasterMachineType.machine_type == machine_type_val,
    ).first()
    if not mt_exists:
        db.add(MasterMachineType(machine=machine_val, machine_type=machine_type_val))

    exists = db.query(MasterMachineId).filter(
        MasterMachineId.machine == machine_val,
        MasterMachineId.machine_type == machine_type_val,
        MasterMachineId.machine_id == machine_id_val,
    ).first()
    if exists:
        return RedirectResponse("/admin/machines?status=machine_id_exists", status_code=303)

    db.add(MasterMachineId(machine=machine_val, machine_type=machine_type_val, machine_id=machine_id_val))
    db.commit()
    bump_active_version()
    return RedirectResponse("/admin/machines?status=machine_id_added", status_code=303)

@app.post("/admin/machines/add-problem")
def admin_add_problem(request: Request,
                      machine: str = Form(...),
                      machine_type: Optional[str] = Form(None),
                      problem: str = Form(...),
                      db: Session = Depends(get_db)):
    me = get_current_user(request, db)
    if not _is_admin_user(me):
        raise HTTPException(status_code=403, detail="Forbidden")

    machine_val = _clean_text(machine)
    machine_type_val = _clean_text(machine_type) or None
    problem_val = _clean_text(problem)
    if not machine_val or not problem_val:
        return RedirectResponse("/admin/machines?status=invalid_input", status_code=303)

    m_exists = db.query(MasterMachine).filter(MasterMachine.machine == machine_val).first()
    if not m_exists:
        db.add(MasterMachine(machine=machine_val))

    if machine_type_val:
        mt_exists = db.query(MasterMachineType).filter(
            MasterMachineType.machine == machine_val,
            MasterMachineType.machine_type == machine_type_val,
        ).first()
        if not mt_exists:
            db.add(MasterMachineType(machine=machine_val, machine_type=machine_type_val))

    q = db.query(MasterProblem).filter(
        MasterProblem.machine == machine_val,
        MasterProblem.problem == problem_val,
    )
    if machine_type_val:
        q = q.filter(MasterProblem.machine_type == machine_type_val)
    else:
        q = q.filter(MasterProblem.machine_type.is_(None))

    if q.first():
        return RedirectResponse("/admin/machines?status=problem_exists", status_code=303)

    db.add(MasterProblem(machine=machine_val, machine_type=machine_type_val, problem=problem_val))
    db.commit()
    bump_active_version()
    return RedirectResponse("/admin/machines?status=problem_added", status_code=303)

# ---------- Current user ----------
def get_current_user(request: Request, db: Session) -> User:
    token = request.cookies.get("session")
    if not token:
        raise HTTPException(status_code=401, detail="Not logged in")
    try:
        username = TimestampSigner(SECRET).unsign(token, max_age=SESSION_AGE).decode()
    except BadSignature:
        raise HTTPException(status_code=401, detail="Bad/expired session")
    user = db.query(User).filter(User.username == username).first()
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    return user

# ---------- Main / Request / Action ----------
@app.get("/", response_class=HTMLResponse)
def index(request: Request, db: Session = Depends(get_db)):
    try:
        user = get_current_user(request, db)
    except HTTPException:
        return RedirectResponse("/login", status_code=302)

    master = _build_master_data(db)

    tickets = (
        db.query(Ticket)
          .filter(Ticket.status != "DONE", Ticket.status != "CANCELLED")
          .order_by(Ticket.id.desc())
          .all()
    )
    return templates.TemplateResponse("index.html", {
        "request": request,
        "user": user,
        "line_ops": master["line_ops"],
        "equipments": EQUIPMENTS,
        "machine_type_map": master["machine_type_map"],
        "machine_id_map": master["machine_id_map"],
        "support_areas": master["support_areas"],
        "support_area_map": master["support_area_map"],
        "problem_map": master["problem_map"],
        "problem_combo_map": master["problem_combo_map"],
        "tickets": tickets,
        "fmt_th": fmt_th,
    })

@app.post("/request/create")
def create_request(
    request: Request,
    machine: str = Form(...),               # Line No.
    equipment: Optional[str] = Form(None),  # Machine (type||brand) หรือ brand เดี่ยว
    machine_id: Optional[str] = Form(None),
    problem: Optional[str] = Form(None),
    description: Optional[str] = Form(None),
    db: Session = Depends(get_db),
):
    user = get_current_user(request, db)
    t = Ticket(
        requester=user.username,
        machine=machine.strip(),
        equipment=(equipment or "").strip() or None,
        machine_id=(machine_id or "").strip() or None,
        problem=(problem or "").strip() or None,
        description=(description or "").strip() or None,
    )
    db.add(t); db.commit()
    bump_active_version()  # <<<<<< สำคัญ: กระตุ้นให้หน้า Active รีโหลด
    line_notify(f"[REQUEST] {t.machine} | {t.equipment or '-'} | {t.machine_id or '-'} | {t.problem or '-'} by {t.requester}")
    return RedirectResponse("/", status_code=303)

@app.post("/tickets/{ticket_id}/action")
def ticket_action(
    ticket_id: int,
    action: str = Form(...),                 # doing|hold|done|cancel
    password: str = Form(...),
    who: Optional[str] = Form(None),
    reason: Optional[str] = Form(None),      # hold/cancel
    solution: Optional[str] = Form(None),    # done
    request: Request = None,
    db: Session = Depends(get_db),
):
    session_user = get_current_user(request, db)
    actor_username = (who or session_user.username).strip()

    actor = db.query(User).filter(User.username == actor_username).first()
    if not actor:
        raise HTTPException(status_code=404, detail="ไม่พบผู้ใช้ที่ระบุ")
    if not verify_password(password, actor.password_hash):
        raise HTTPException(status_code=403, detail="รหัสผ่านไม่ถูกต้อง")

    ticket = db.query(Ticket).filter(Ticket.id == ticket_id).first()
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")

    act = action.lower().strip()

    if ticket.status in ("DOING", "HOLD") and act == "done":
        if ticket.current_actor and ticket.current_actor != actor.username:
            raise HTTPException(status_code=409, detail=f"Username ไม่ตรงกับคนปฏิบัติงานอยู่ ({ticket.current_actor})")

    if act == "doing" and ticket.status == "DOING":
        raise HTTPException(status_code=409, detail="ไม่สามารถกด Doing ซ้ำเพื่อเริ่มนับเวลาใหม่ได้")
    if act == "hold" and ticket.status == "HOLD":
        raise HTTPException(status_code=409, detail="ไม่สามารถกด Hold ซ้ำเพื่อเริ่มนับเวลาใหม่ได้")

    if act == "doing":
        ticket.start_doing()
        ticket.current_actor = actor.username
        ticket.last_action = "doing"
    elif act == "hold":
        if not (reason and reason.strip()):
            raise HTTPException(status_code=400, detail="กรอกเหตุผล Hold")
        ticket.start_hold(reason.strip())
        ticket.current_actor = actor.username
        ticket.last_action = "hold"
    elif act == "done":
        if not (solution and solution.strip()):
            raise HTTPException(status_code=400, detail="กรอก Solution ก่อน Done")
        ticket.done(solution.strip(), by=actor.username)
        ticket.current_actor = None
        ticket.last_action = "done"
    elif act == "cancel":
        if not (reason and reason.strip()):
            raise HTTPException(status_code=400, detail="กรอกเหตุผล Cancel")
        ticket.cancel(reason.strip(), by=actor.username)
        ticket.current_actor = None
        ticket.last_action = "cancel"
    else:
        raise HTTPException(status_code=400, detail="invalid action")

    db.add(ticket); db.commit()
    bump_active_version()  # <<<<<< สำคัญ: กระตุ้นให้หน้า Active รีโหลด
    return {
        "ok": True,
        "id": ticket.id,
        "status": ticket.status,
        "doing_secs": ticket.doing_secs,
        "hold_secs": ticket.hold_secs,
        "current_actor": ticket.current_actor,
        "last_action": ticket.last_action,
        "solution": ticket.solution,
        "done_by": ticket.done_by,
        "cancel_reason": ticket.cancel_reason,
        "canceled_by": ticket.canceled_by,
        "doing_started_at": ticket.doing_started_at.isoformat() if ticket.doing_started_at else None,
        "hold_started_at": ticket.hold_started_at.isoformat() if ticket.hold_started_at else None,
    }

# ---------- History + Export ----------
def _query_done_or_cancel(db: Session,
                          line_op: Optional[str] = None,
                          equipment: Optional[str] = None,
                          start_utc: Optional[datetime] = None,
                          end_utc: Optional[datetime] = None) -> List[Ticket]:
    q = db.query(Ticket).filter(Ticket.status.in_(["DONE","CANCELLED"]))
    if line_op: q = q.filter(Ticket.machine == line_op)
    if equipment: q = q.filter(Ticket.equipment == equipment)
    if start_utc: q = q.filter(Ticket.created_at >= start_utc)
    if end_utc: q = q.filter(Ticket.created_at <= end_utc)
    return q.order_by(Ticket.closed_at.desc().nullslast()).all()

def _normalize_history_filters(machine_type: Optional[str],
                               machine_brand: Optional[str],
                               equipment: Optional[str]) -> tuple[str, str]:
    type_val = _clean_text(machine_type)
    brand_val = _clean_text(machine_brand)
    if type_val or brand_val:
        return type_val, brand_val

    raw = _clean_text(equipment)
    if not raw:
        return "", ""
    if "||" in raw:
        left, right = raw.split("||", 1)
        return _clean_text(left), _clean_text(right)
    return "", raw

def _build_history_type_lookup(machine_type_map: Dict[str, List[str]]) -> tuple[Dict[str, str], Dict[str, str]]:
    type_by_key: Dict[str, str] = {}
    brand_to_type: Dict[str, str] = {}

    for machine_type, brands in (machine_type_map or {}).items():
        machine_type_val = _clean_text(machine_type)
        if not machine_type_val:
            continue
        type_by_key[machine_type_val.lower()] = machine_type_val
        brand_to_type.setdefault(machine_type_val.lower(), machine_type_val)
        for brand in brands or []:
            brand_val = _clean_text(brand)
            if not brand_val:
                continue
            brand_to_type.setdefault(brand_val.lower(), machine_type_val)

    return type_by_key, brand_to_type

def _parse_ticket_machine_and_brand(raw_equipment: Optional[str],
                                    type_by_key: Dict[str, str],
                                    brand_to_type: Dict[str, str]) -> tuple[str, str]:
    raw = _clean_text(raw_equipment)
    if "||" in raw:
        left, right = raw.split("||", 1)
        return _clean_text(left), _clean_text(right)

    brand = raw
    if not brand:
        return "", ""

    if brand.lower() == "other m/c or tools":
        return "Etc..", brand

    machine_type = type_by_key.get(brand.lower()) or brand_to_type.get(brand.lower(), "")
    return machine_type, brand

def _apply_history_machine_filters(rows: List[Ticket],
                                   machine_type: str,
                                   machine_brand: str,
                                   machine_type_map: Dict[str, List[str]]) -> List[Ticket]:
    sel_type = _clean_text(machine_type).lower()
    sel_brand = _clean_text(machine_brand).lower()
    type_by_key, brand_to_type = _build_history_type_lookup(machine_type_map)
    out: List[Ticket] = []

    for row in rows:
        parsed_type, parsed_brand = _parse_ticket_machine_and_brand(row.equipment, type_by_key, brand_to_type)
        row.history_machine = parsed_type
        row.history_machine_type = parsed_brand

        if sel_type and parsed_type.lower() != sel_type:
            continue
        if sel_brand and parsed_brand.lower() != sel_brand:
            continue
        out.append(row)
    return out

@app.get("/history", response_class=HTMLResponse)
def history(request: Request,
            line_op: Optional[str] = Query(None),
            machine_type: Optional[str] = Query(None),
            machine_brand: Optional[str] = Query(None),
            equipment: Optional[str] = Query(None),  # backward-compatible query param
            start_date: Optional[str] = Query(None),
            end_date: Optional[str] = Query(None),
            db: Session = Depends(get_db)):
    try:
        user = get_current_user(request, db)
    except HTTPException:
        return RedirectResponse("/login", status_code=302)

    start_utc = end_utc = None
    try:
        if start_date:
            start_utc = datetime.combine(datetime.strptime(start_date, "%Y-%m-%d").date(), time.min) - TH_OFFSET
        if end_date:
            end_utc = datetime.combine(datetime.strptime(end_date, "%Y-%m-%d").date(), time.max) - TH_OFFSET
    except Exception:
        start_utc = end_utc = None

    master = _build_master_data(db)
    machine_type_val, machine_brand_val = _normalize_history_filters(machine_type, machine_brand, equipment)

    rows = _query_done_or_cancel(db, line_op, None, start_utc, end_utc)
    rows = _apply_history_machine_filters(rows, machine_type_val, machine_brand_val, master["machine_type_map"])
    total_doing = sum((t.doing_secs or 0) for t in rows)
    total_hold  = sum((t.hold_secs  or 0) for t in rows)
    summary = {"doing": _fmt_hms(total_doing), "hold": _fmt_hms(total_hold)}

    return templates.TemplateResponse("history.html", {
        "request": request,
        "user": user,
        "rows": rows,
        "summary": summary,
        "line_ops": master["line_ops"],
        "machine_type_map": master["machine_type_map"],
        "line_op": line_op or "",
        "machine_type": machine_type_val,
        "machine_brand": machine_brand_val,
        "start_date": start_date or "",
        "end_date": end_date or "",
        "fmt_th": fmt_th,
    })

@app.get("/export/excel")
def export_excel(request: Request,
                 line_op: Optional[str] = Query(None),
                 machine_type: Optional[str] = Query(None),
                 machine_brand: Optional[str] = Query(None),
                 equipment: Optional[str] = Query(None),  # backward-compatible query param
                 start_date: Optional[str] = Query(None),
                 end_date: Optional[str] = Query(None),
                 db: Session = Depends(get_db)):
    try:
        _ = get_current_user(request, db)
    except HTTPException:
        return RedirectResponse("/login", status_code=302)

    import xlsxwriter

    start_utc = end_utc = None
    try:
        if start_date:
            start_utc = datetime.combine(datetime.strptime(start_date, "%Y-%m-%d").date(), time.min) - TH_OFFSET
        if end_date:
            end_utc = datetime.combine(datetime.strptime(end_date, "%Y-%m-%d").date(), time.max) - TH_OFFSET
    except Exception:
        start_utc = end_utc = None

    machine_type_val, machine_brand_val = _normalize_history_filters(machine_type, machine_brand, equipment)
    master = _build_master_data(db)
    rows = _query_done_or_cancel(db, line_op, None, start_utc, end_utc)
    rows = _apply_history_machine_filters(rows, machine_type_val, machine_brand_val, master["machine_type_map"])
    type_by_key, brand_to_type = _build_history_type_lookup(master["machine_type_map"])

    buf = io.BytesIO()
    wb = xlsxwriter.Workbook(buf, {'in_memory': True})
    ws = wb.add_worksheet('History (TH)')

    ws.freeze_panes(1, 0)
    ws.autofilter(0, 0, 0, 18)
    ws.set_landscape()
    ws.fit_to_pages(1, 0)

    hdr   = wb.add_format({'bold': True, 'bg_color': '#EEF2FF', 'border': 1})
    cell  = wb.add_format({'border': 1})
    center= wb.add_format({'border': 1, 'align': 'center'})
    wrap  = wb.add_format({'border': 1, 'text_wrap': True})

    headers = [
        "ID", "Status", "Created (TH)", "Closed (TH)",
        "Request by", "Line No.", "Machine", "Machine Type",
        "Machine ID", "Problem", "Description", "Doing", "Hold",
        "Hold Reason", "Waiting Time", "Downtime",
        "Solution", "Cancel Reason", "Done By",
    ]
    for c, h in enumerate(headers):
        ws.write(0, c, h, hdr)

    def hms(sec: int) -> str:
        s = int(sec or 0); h, m, ss = s // 3600, (s % 3600) // 60, s % 60
        return f"{h:02d}:{m:02d}:{ss:02d}"

    def nz(v: Optional[str]) -> str:
        v = (v or "").strip()
        return v if v else "-"

    r = 1
    for t in rows:
        mtype, brand = _parse_ticket_machine_and_brand(t.equipment, type_by_key, brand_to_type)

        sum_secs = int((t.closed_at - t.created_at).total_seconds()) if (t.closed_at and t.created_at) else 0
        doing = int(t.doing_secs or 0)
        hold  = int(t.hold_secs or 0)
        waiting = max(0, sum_secs - doing - hold)

        ws.write(r,  0, t.id, center)
        ws.write(r,  1, nz(t.status), center)
        ws.write(r,  2, nz(fmt_th(t.created_at)), cell)
        ws.write(r,  3, nz(fmt_th(t.closed_at)), cell)
        ws.write(r,  4, nz(t.requester), cell)
        ws.write(r,  5, nz(t.machine), cell)
        ws.write(r,  6, nz(mtype), cell)
        ws.write(r,  7, nz(brand), cell)
        ws.write(r,  8, nz(t.machine_id), cell)
        ws.write(r,  9, nz(t.problem), cell)
        ws.write(r, 10, nz(t.description), wrap)
        ws.write(r, 11, hms(doing), center)
        ws.write(r, 12, hms(hold), center)
        ws.write(r, 13, nz(t.hold_reason), wrap)
        ws.write(r, 14, hms(waiting), center)
        ws.write(r, 15, hms(sum_secs), center)
        ws.write(r, 16, nz(t.solution), wrap)
        ws.write(r, 17, nz(t.cancel_reason), wrap)
        ws.write(r, 18, nz(t.done_by or t.canceled_by), cell)
        r += 1

    widths = [6, 10, 18, 18, 12, 10, 16, 18, 14, 20, 36, 10, 10, 20, 14, 12, 20, 20, 12]
    for i, w in enumerate(widths):
        ws.set_column(i, i, w)

    wb.close(); buf.seek(0)

    filename = "history"
    if line_op: filename += f"_{line_op}"
    if machine_type_val: filename += f"_{machine_type_val}"
    if machine_brand_val: filename += f"_{machine_brand_val}"
    if start_date or end_date: filename += f"_{start_date or ''}-{end_date or ''}"
    filename += ".xlsx"

    return StreamingResponse(
        buf,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'}
    )
