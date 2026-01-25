# server_app.py

from datetime import datetime, timedelta, time
from typing import Optional, List
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

Base.metadata.create_all(bind=engine)

def _ensure_columns_and_indexes():
    with engine.connect() as con:
        cols = {r[1] for r in con.exec_driver_sql("PRAGMA table_info(tickets)").fetchall()}
        need = {
            "equipment": "TEXT",
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

    tickets = (
        db.query(Ticket)
          .filter(Ticket.status != "DONE", Ticket.status != "CANCELLED")
          .order_by(Ticket.id.desc())
          .all()
    )
    return templates.TemplateResponse("index.html", {
        "request": request,
        "user": user,
        "line_ops": LINE_OPS,
        "equipments": EQUIPMENTS,
        "problem_map": PROBLEM_MAP,
        "tickets": tickets,
        "fmt_th": fmt_th,
    })

@app.post("/request/create")
def create_request(
    request: Request,
    machine: str = Form(...),               # Line No.
    equipment: Optional[str] = Form(None),  # Machine (type||brand) หรือ brand เดี่ยว
    problem: Optional[str] = Form(None),
    description: Optional[str] = Form(None),
    db: Session = Depends(get_db),
):
    user = get_current_user(request, db)
    t = Ticket(
        requester=user.username,
        machine=machine.strip(),
        equipment=(equipment or "").strip() or None,
        problem=(problem or "").strip() or None,
        description=(description or "").strip() or None,
    )
    db.add(t); db.commit()
    bump_active_version()  # <<<<<< สำคัญ: กระตุ้นให้หน้า Active รีโหลด
    line_notify(f"[REQUEST] {t.machine} | {t.equipment or '-'} | {t.problem or '-'} by {t.requester}")
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

    if ticket.status in ("DOING", "HOLD"):
        if ticket.current_actor and ticket.current_actor != actor.username:
            raise HTTPException(status_code=409, detail=f"งานนี้กำลังถูกดำเนินการโดย {ticket.current_actor} อยู่")

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

@app.get("/history", response_class=HTMLResponse)
def history(request: Request,
            line_op: Optional[str] = Query(None),
            equipment: Optional[str] = Query(None),
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

    rows = _query_done_or_cancel(db, line_op, equipment, start_utc, end_utc)
    total_doing = sum((t.doing_secs or 0) for t in rows)
    total_hold  = sum((t.hold_secs  or 0) for t in rows)
    summary = {"doing": _fmt_hms(total_doing), "hold": _fmt_hms(total_hold)}

    return templates.TemplateResponse("history.html", {
        "request": request,
        "user": user,
        "rows": rows,
        "summary": summary,
        "line_ops": LINE_OPS,
        "equipments": EQUIPMENTS,
        "line_op": line_op or "",
        "equipment": equipment or "",
        "start_date": start_date or "",
        "end_date": end_date or "",
        "fmt_th": fmt_th,
    })

@app.get("/export/excel")
def export_excel(line_op: Optional[str] = Query(None),
                 equipment: Optional[str] = Query(None),
                 start_date: Optional[str] = Query(None),
                 end_date: Optional[str] = Query(None),
                 db: Session = Depends(get_db)):
    import xlsxwriter

    start_utc = end_utc = None
    try:
        if start_date:
            start_utc = datetime.combine(datetime.strptime(start_date, "%Y-%m-%d").date(), time.min) - TH_OFFSET
        if end_date:
            end_utc = datetime.combine(datetime.strptime(end_date, "%Y-%m-%d").date(), time.max) - TH_OFFSET
    except Exception:
        start_utc = end_utc = None

    rows = _query_done_or_cancel(db, line_op, equipment, start_utc, end_utc)

    buf = io.BytesIO()
    wb = xlsxwriter.Workbook(buf, {'in_memory': True})
    ws = wb.add_worksheet('History (TH)')

    ws.freeze_panes(1, 0)
    ws.autofilter(0, 0, 0, 17)
    ws.set_landscape()
    ws.fit_to_pages(1, 0)

    hdr   = wb.add_format({'bold': True, 'bg_color': '#EEF2FF', 'border': 1})
    cell  = wb.add_format({'border': 1})
    center= wb.add_format({'border': 1, 'align': 'center'})
    wrap  = wb.add_format({'border': 1, 'text_wrap': True})

    headers = [
        "ID", "Status", "Created (TH)", "Closed (TH)",
        "Request by", "Line No.", "Machine", "Machine Type",
        "Problem", "Description", "Doing", "Hold",
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
        raw = (t.equipment or "").strip()
        if "||" in raw:
            mtype, brand = raw.split("||", 1)
        else:
            mtype, brand = "", raw
            if brand.lower() == "other m/c or tools":
                mtype = "Etc.."

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
        ws.write(r,  8, nz(t.problem), cell)
        ws.write(r,  9, nz(t.description), wrap)
        ws.write(r, 10, hms(doing), center)
        ws.write(r, 11, hms(hold), center)
        ws.write(r, 12, nz(t.hold_reason), wrap)
        ws.write(r, 13, hms(waiting), center)
        ws.write(r, 14, hms(sum_secs), center)
        ws.write(r, 15, nz(t.solution), wrap)
        ws.write(r, 16, nz(t.cancel_reason), wrap)
        ws.write(r, 17, nz(t.done_by or t.canceled_by), cell)
        r += 1

    widths = [6, 10, 18, 18, 12, 10, 16, 18, 20, 36, 10, 10, 20, 14, 12, 20, 20, 12]
    for i, w in enumerate(widths):
        ws.set_column(i, i, w)

    wb.close(); buf.seek(0)

    filename = "history"
    if line_op: filename += f"_{line_op}"
    if equipment: filename += f"_{equipment.replace('||','-')}"
    if start_date or end_date: filename += f"_{start_date or ''}-{end_date or ''}"
    filename += ".xlsx"

    return StreamingResponse(
        buf,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'}
    )
