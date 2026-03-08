import os
from datetime import datetime

from sqlalchemy import Column, DateTime, Integer, String, Text, UniqueConstraint, create_engine, event
from sqlalchemy.orm import declarative_base, sessionmaker

from python.auth import sha256

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
DEFAULT_DB_PATH = os.path.join(BASE_DIR, "database", "supporthub.db")
os.makedirs(os.path.dirname(DEFAULT_DB_PATH), exist_ok=True)
DATABASE_URL = os.getenv(
    "SUPPORTHUB_DATABASE_URL",
    f"sqlite:///{DEFAULT_DB_PATH.replace(os.sep, '/')}",
)

IS_SQLITE = DATABASE_URL.lower().startswith("sqlite")
engine_kwargs = {"pool_pre_ping": True}
if IS_SQLITE:
    engine_kwargs["connect_args"] = {"check_same_thread": False}

engine = create_engine(DATABASE_URL, **engine_kwargs)
SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)
Base = declarative_base()


if IS_SQLITE:
    @event.listens_for(engine, "connect")
    def set_sqlite_pragma(dbapi_conn, connection_record):
        cursor = dbapi_conn.cursor()
        try:
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.execute("PRAGMA synchronous=NORMAL")
            cursor.execute("PRAGMA busy_timeout=5000")
            cursor.execute("PRAGMA foreign_keys=ON")
        finally:
            cursor.close()


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
    closed_at = Column(DateTime, nullable=True)

    requester = Column(String(50), nullable=False)
    machine = Column(String(50), nullable=True)
    equipment = Column(String(200), nullable=True)
    machine_id = Column(String(100), nullable=True)
    problem = Column(String(100), nullable=True)
    description = Column(Text, nullable=True)

    status = Column(String(12), default="PENDING", nullable=False)
    doing_started_at = Column(DateTime, nullable=True)
    hold_started_at = Column(DateTime, nullable=True)
    doing_secs = Column(Integer, default=0, nullable=False)
    hold_secs = Column(Integer, default=0, nullable=False)

    current_actor = Column(String(50), nullable=True)
    last_action = Column(String(10), nullable=True)
    hold_reason = Column(Text, nullable=True)
    solution = Column(Text, nullable=True)
    done_by = Column(String(50), nullable=True)
    cancel_reason = Column(Text, nullable=True)
    canceled_by = Column(String(50), nullable=True)

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


class TicketTakeoverLog(Base):
    __tablename__ = "ticket_takeover_logs"
    id = Column(Integer, primary_key=True)
    ticket_id = Column(Integer, nullable=False, index=True)
    from_actor = Column(String(50), nullable=True)
    to_actor = Column(String(50), nullable=False)
    status = Column(String(12), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)


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


class MasterAuditLog(Base):
    __tablename__ = "master_audit_logs"
    id = Column(Integer, primary_key=True)
    action = Column(String(20), nullable=False, index=True)
    data_type = Column(String(50), nullable=False, index=True)
    item = Column(String(250), nullable=False)
    actor = Column(String(50), nullable=False, index=True)
    details = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _ensure_columns_and_indexes() -> None:
    with engine.begin() as con:
        if engine.dialect.name == "sqlite":
            cols = {row[1] for row in con.exec_driver_sql("PRAGMA table_info(tickets)").fetchall()}
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
            for column_name, column_type in need.items():
                if column_name not in cols:
                    con.exec_driver_sql(f"ALTER TABLE tickets ADD COLUMN {column_name} {column_type}")

        con.exec_driver_sql("CREATE INDEX IF NOT EXISTS idx_tickets_status ON tickets(status)")
        con.exec_driver_sql("CREATE INDEX IF NOT EXISTS idx_tickets_closed_at ON tickets(closed_at)")
        con.exec_driver_sql("CREATE INDEX IF NOT EXISTS idx_tickets_machine ON tickets(machine)")
        con.exec_driver_sql("CREATE INDEX IF NOT EXISTS idx_tickets_machine_id ON tickets(machine_id)")


def _ensure_postgres_history_view() -> None:
    if engine.dialect.name != "postgresql":
        return

    sql = """
    DROP VIEW IF EXISTS public.v_history_log;
    CREATE VIEW public.v_history_log AS
    WITH takeover AS (
        SELECT
            l.ticket_id,
            string_agg(
                to_char(l.created_at + interval '7 hour', 'YYYY-MM-DD HH24:MI:SS')
                || ' | ' || coalesce(l.from_actor, '-')
                || ' -> ' || coalesce(l.to_actor, '-'),
                E'\\n'
                ORDER BY l.created_at, l.id
            ) AS takeover_log
        FROM ticket_takeover_logs l
        GROUP BY l.ticket_id
    ),
    brand_map AS (
        SELECT lower(mt.machine_type) AS key_name, min(mt.machine) AS machine_name
        FROM master_machine_types mt
        GROUP BY lower(mt.machine_type)
    ),
    machine_map AS (
        SELECT lower(mt.machine) AS key_name, min(mt.machine) AS machine_name
        FROM master_machine_types mt
        GROUP BY lower(mt.machine)
    )
    SELECT
        t.id AS "ID",
        t.status AS "Status",
        to_char(t.created_at + interval '7 hour', 'YYYY-MM-DD HH24:MI:SS') AS "Created (TH)",
        CASE
            WHEN t.closed_at IS NULL THEN '-'
            ELSE to_char(t.closed_at + interval '7 hour', 'YYYY-MM-DD HH24:MI:SS')
        END AS "Closed (TH)",
        t.requester AS "Request by",
        t.machine AS "Line No.",
        CASE
            WHEN position('||' in coalesce(t.equipment, '')) > 0
                THEN nullif(trim(split_part(t.equipment, '||', 1)), '')
            WHEN lower(coalesce(t.equipment, '')) = 'other m/c or tools'
                THEN 'Etc..'
            ELSE coalesce(mm.machine_name, bm.machine_name, '')
        END AS "Machine",
        CASE
            WHEN position('||' in coalesce(t.equipment, '')) > 0
                THEN nullif(trim(split_part(t.equipment, '||', 2)), '')
            ELSE coalesce(nullif(trim(t.equipment), ''), '')
        END AS "Machine Type",
        coalesce(t.machine_id, '-') AS "Machine ID",
        coalesce(t.problem, '') AS "Problem",
        coalesce(t.description, '-') AS "Description",
        lpad((dur.doing_secs / 3600)::text, 2, '0') || ':' ||
        lpad(((mod(dur.doing_secs, 3600)) / 60)::text, 2, '0') || ':' ||
        lpad((mod(dur.doing_secs, 60))::text, 2, '0') AS "Doing",
        lpad((dur.hold_secs / 3600)::text, 2, '0') || ':' ||
        lpad(((mod(dur.hold_secs, 3600)) / 60)::text, 2, '0') || ':' ||
        lpad((mod(dur.hold_secs, 60))::text, 2, '0') AS "Hold",
        coalesce(t.hold_reason, '-') AS "Hold Reason",
        lpad((dur.wait_secs / 3600)::text, 2, '0') || ':' ||
        lpad(((mod(dur.wait_secs, 3600)) / 60)::text, 2, '0') || ':' ||
        lpad((mod(dur.wait_secs, 60))::text, 2, '0') AS "Waiting Time",
        lpad((dur.sum_secs / 3600)::text, 2, '0') || ':' ||
        lpad(((mod(dur.sum_secs, 3600)) / 60)::text, 2, '0') || ':' ||
        lpad((mod(dur.sum_secs, 60))::text, 2, '0') AS "Downtime",
        coalesce(t.solution, '-') AS "Solution",
        coalesce(t.cancel_reason, '-') AS "Cancel Reason",
        coalesce(tk.takeover_log, '-') AS "Takeover Log",
        CASE
            WHEN t.status = 'DONE' THEN coalesce(t.done_by, '-')
            WHEN t.status = 'CANCELLED' THEN coalesce(t.canceled_by, '-')
            ELSE '-'
        END AS "Done By"
    FROM tickets t
    LEFT JOIN brand_map bm
        ON bm.key_name = lower(coalesce(t.equipment, ''))
    LEFT JOIN machine_map mm
        ON mm.key_name = lower(coalesce(t.equipment, ''))
    LEFT JOIN takeover tk
        ON tk.ticket_id = t.id
    LEFT JOIN LATERAL (
        SELECT
            greatest(coalesce(t.doing_secs, 0), 0) AS doing_secs,
            greatest(coalesce(t.hold_secs, 0), 0) AS hold_secs,
            greatest(
                coalesce(extract(epoch FROM (coalesce(t.closed_at, t.created_at) - t.created_at))::int, 0),
                0
            ) AS sum_secs,
            greatest(
                coalesce(extract(epoch FROM (coalesce(t.closed_at, t.created_at) - t.created_at))::int, 0)
                - greatest(coalesce(t.doing_secs, 0), 0)
                - greatest(coalesce(t.hold_secs, 0), 0),
                0
            ) AS wait_secs
    ) dur ON true
    ORDER BY t.id DESC;
    """
    with engine.begin() as con:
        con.exec_driver_sql(sql)


def _ensure_postgres_history_table() -> None:
    if engine.dialect.name != "postgresql":
        return

    with engine.begin() as con:
        con.exec_driver_sql("DROP TABLE IF EXISTS public.history_log_table")
        con.exec_driver_sql(
            "CREATE TABLE public.history_log_table AS "
            "SELECT * FROM public.v_history_log WITH NO DATA"
        )
        con.exec_driver_sql(
            "INSERT INTO public.history_log_table "
            "SELECT * FROM public.v_history_log"
        )
        con.exec_driver_sql(
            """
            CREATE OR REPLACE FUNCTION public.refresh_history_log_table()
            RETURNS trigger
            LANGUAGE plpgsql
            AS $$
            BEGIN
                TRUNCATE TABLE public.history_log_table;
                INSERT INTO public.history_log_table
                SELECT * FROM public.v_history_log;
                RETURN NULL;
            END;
            $$;
            """
        )
        con.exec_driver_sql(
            "DROP TRIGGER IF EXISTS trg_refresh_history_log_table_tickets ON public.tickets"
        )
        con.exec_driver_sql(
            """
            CREATE TRIGGER trg_refresh_history_log_table_tickets
            AFTER INSERT OR UPDATE OR DELETE OR TRUNCATE
            ON public.tickets
            FOR EACH STATEMENT
            EXECUTE FUNCTION public.refresh_history_log_table()
            """
        )
        con.exec_driver_sql(
            "DROP TRIGGER IF EXISTS trg_refresh_history_log_table_takeover ON public.ticket_takeover_logs"
        )
        con.exec_driver_sql(
            """
            CREATE TRIGGER trg_refresh_history_log_table_takeover
            AFTER INSERT OR UPDATE OR DELETE OR TRUNCATE
            ON public.ticket_takeover_logs
            FOR EACH STATEMENT
            EXECUTE FUNCTION public.refresh_history_log_table()
            """
        )


def _ensure_admin_user() -> None:
    db = None
    try:
        db = SessionLocal()
        admin = db.query(User).filter(User.username == "ADMIN").first()
        target_hash = sha256("259487123")
        if not admin:
            db.add(User(username="ADMIN", password_hash=target_hash, role="Admin"))
            db.commit()
            return

        changed = False
        if admin.password_hash != target_hash:
            admin.password_hash = target_hash
            changed = True
        if admin.role != "Admin":
            admin.role = "Admin"
            changed = True
        if changed:
            db.add(admin)
            db.commit()
    except Exception as exc:
        print("[INIT] _ensure_admin_user error:", exc)
    finally:
        if db is not None:
            db.close()


def init_db() -> None:
    Base.metadata.create_all(bind=engine)
    _ensure_columns_and_indexes()
    _ensure_postgres_history_view()
    _ensure_postgres_history_table()
    _ensure_admin_user()
