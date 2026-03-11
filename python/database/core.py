import json
import os
from datetime import datetime
from pathlib import Path

from sqlalchemy import Column, DateTime, Integer, String, Text, UniqueConstraint, create_engine, text
from sqlalchemy.orm import declarative_base, sessionmaker

from python.auth import sha256

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
DATABASE_URL = (os.getenv("SUPPORTHUB_DATABASE_URL") or "").strip()
if not DATABASE_URL:
    raise RuntimeError("SUPPORTHUB_DATABASE_URL is required (PostgreSQL only).")
if not (
    DATABASE_URL.lower().startswith("postgresql://")
    or DATABASE_URL.lower().startswith("postgresql+psycopg://")
):
    raise RuntimeError(
        "Invalid SUPPORTHUB_DATABASE_URL. PostgreSQL URL is required "
        "(postgresql:// or postgresql+psycopg://)."
    )

engine = create_engine(DATABASE_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)
Base = declarative_base()
ENABLE_POSTGRES_DISPLAY_TABLES = (
    (os.getenv("SUPPORTHUB_ENABLE_POSTGRES_DISPLAY_TABLES") or "").strip().lower()
    in {"1", "true", "yes", "on"}
)


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


class MasterLineMonitoringMap(Base):
    __tablename__ = "master_line_monitoring_maps"
    id = Column(Integer, primary_key=True)
    line_no = Column(String(50), nullable=False, index=True)
    machine_type = Column(String(100), nullable=False, index=True)
    machine_id = Column(String(100), nullable=False, default="-")
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    __table_args__ = (
        UniqueConstraint(
            "line_no",
            "machine_type",
            "machine_id",
            name="uq_master_line_monitoring_map",
        ),
    )


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


class ProblemClass(Base):
    __tablename__ = "problem_classes"
    id = Column(Integer, primary_key=True)
    class_name = Column(String(100), nullable=False, unique=True, index=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class ProblemMatch(Base):
    __tablename__ = "problem_matches"
    id = Column(Integer, primary_key=True)
    machine = Column(String(100), nullable=False, index=True)
    problem = Column(String(150), nullable=False, index=True)
    class_name = Column(String(100), nullable=False, index=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    __table_args__ = (
        UniqueConstraint("machine", "problem", name="uq_problem_match_machine_problem"),
    )


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _ensure_columns_and_indexes() -> None:
    with engine.begin() as con:
        ticket_columns = (
            ("equipment", "TEXT"),
            ("machine_id", "TEXT"),
            ("problem", "TEXT"),
            ("status", "TEXT DEFAULT 'PENDING'"),
            ("doing_started_at", "TIMESTAMPTZ"),
            ("hold_started_at", "TIMESTAMPTZ"),
            ("doing_secs", "INTEGER DEFAULT 0"),
            ("hold_secs", "INTEGER DEFAULT 0"),
            ("current_actor", "TEXT"),
            ("last_action", "TEXT"),
            ("hold_reason", "TEXT"),
            ("solution", "TEXT"),
            ("done_by", "TEXT"),
            ("cancel_reason", "TEXT"),
            ("canceled_by", "TEXT"),
        )
        for column_name, column_type in ticket_columns:
            con.exec_driver_sql(
                "ALTER TABLE public.tickets "
                f"ADD COLUMN IF NOT EXISTS {column_name} {column_type}"
            )
        # plaintext password storage is intentionally removed for security.
        con.exec_driver_sql("ALTER TABLE public.users DROP COLUMN IF EXISTS password_plain")

        for index_sql in (
            "CREATE INDEX IF NOT EXISTS idx_tickets_status ON tickets(status)",
            "CREATE INDEX IF NOT EXISTS idx_tickets_closed_at ON tickets(closed_at)",
            "CREATE INDEX IF NOT EXISTS idx_tickets_machine ON tickets(machine)",
            "CREATE INDEX IF NOT EXISTS idx_tickets_machine_id ON tickets(machine_id)",
        ):
            con.exec_driver_sql(index_sql)


def _ensure_postgres_iot_tables() -> None:
    if engine.dialect.name != "postgresql":
        return

    with engine.begin() as con:
        con.exec_driver_sql(
            """
            CREATE TABLE IF NOT EXISTS public.iot_monitor_measurements (
                id BIGSERIAL PRIMARY KEY,
                recorded_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                broker VARCHAR(255),
                topic VARCHAR(255),
                mqtt_client VARCHAR(255),
                voltage NUMERIC(14,4),
                current NUMERIC(14,4),
                power NUMERIC(14,4),
                power_factor NUMERIC(8,4),
                energy NUMERIC(18,6),
                frequency NUMERIC(10,4),
                raw_payload TEXT,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                CONSTRAINT ck_iot_power_factor_range
                    CHECK (power_factor IS NULL OR (power_factor >= -1 AND power_factor <= 1))
            )
            """
        )
        for col_name in ("broker", "topic", "mqtt_client"):
            con.exec_driver_sql(
                "ALTER TABLE public.iot_monitor_measurements "
                f"ADD COLUMN IF NOT EXISTS {col_name} VARCHAR(255)"
            )
        for index_name in (
            "idx_iot_monitor_measurements_machine_time",
            "idx_iot_monitor_measurements_line_time",
        ):
            con.exec_driver_sql(f"DROP INDEX IF EXISTS {index_name}")
        for legacy_col in ("source_topic", "line_no", "machine", "machine_type", "machine_id"):
            con.exec_driver_sql(
                "ALTER TABLE public.iot_monitor_measurements "
                f"DROP COLUMN IF EXISTS {legacy_col}"
            )
        con.exec_driver_sql(
            """
            CREATE INDEX IF NOT EXISTS idx_iot_monitor_measurements_recorded_at
            ON public.iot_monitor_measurements (recorded_at DESC)
            """
        )
        con.exec_driver_sql(
            """
            CREATE TABLE IF NOT EXISTS public.iot_monitor_status_logs (
                id BIGSERIAL PRIMARY KEY,
                recorded_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                broker VARCHAR(255),
                topic VARCHAR(255),
                mqtt_client VARCHAR(255),
                connected BOOLEAN NOT NULL DEFAULT FALSE,
                last_message_at TIMESTAMPTZ,
                message_count BIGINT NOT NULL DEFAULT 0,
                parse_error_count BIGINT NOT NULL DEFAULT 0,
                last_payload TEXT,
                last_error TEXT,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
            """
        )
        for col_name, col_type in (
            ("broker", "VARCHAR(255)"),
            ("topic", "VARCHAR(255)"),
            ("mqtt_client", "VARCHAR(255)"),
            ("connected", "BOOLEAN NOT NULL DEFAULT FALSE"),
            ("last_message_at", "TIMESTAMPTZ"),
            ("message_count", "BIGINT NOT NULL DEFAULT 0"),
            ("parse_error_count", "BIGINT NOT NULL DEFAULT 0"),
            ("last_payload", "TEXT"),
            ("last_error", "TEXT"),
        ):
            con.exec_driver_sql(
                "ALTER TABLE public.iot_monitor_status_logs "
                f"ADD COLUMN IF NOT EXISTS {col_name} {col_type}"
            )
        con.exec_driver_sql(
            """
            CREATE INDEX IF NOT EXISTS idx_iot_monitor_status_logs_recorded_at
            ON public.iot_monitor_status_logs (recorded_at DESC)
            """
        )


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
                to_char(l.created_at + interval '7 hour', 'DD-MM-YYYY HH24:MI:SS')
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
        to_char(t.created_at + interval '7 hour', 'DD-MM-YYYY HH24:MI:SS') AS "Created (TH)",
        CASE
            WHEN t.closed_at IS NULL THEN '-'
            ELSE to_char(t.closed_at + interval '7 hour', 'DD-MM-YYYY HH24:MI:SS')
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


def _ensure_postgres_manage_users_table() -> None:
    if engine.dialect.name != "postgresql":
        return

    select_sql = """
    SELECT
        coalesce(u.username, '-') AS "Username",
        coalesce(u.role, '-') AS "Role",
        ''::text AS "Set New Password",
        to_char(u.created_at + interval '7 hour', 'DD-MM-YYYY HH24:MI:SS') AS "Created",
        ''::text AS "Action"
    FROM public.users u
    ORDER BY
        CASE WHEN upper(coalesce(u.username, '')) = 'ADMIN' THEN 0 ELSE 1 END,
        u.username ASC
    """

    with engine.begin() as con:
        con.exec_driver_sql("DROP TABLE IF EXISTS public.manage_users_table")
        con.exec_driver_sql(
            "CREATE TABLE public.manage_users_table AS "
            "SELECT * FROM (" + select_sql + ") t WITH NO DATA"
        )
        con.exec_driver_sql(
            "INSERT INTO public.manage_users_table "
            + select_sql
        )
        con.exec_driver_sql(
            """
            CREATE OR REPLACE FUNCTION public.refresh_manage_users_table()
            RETURNS trigger
            LANGUAGE plpgsql
            AS $$
            BEGIN
                TRUNCATE TABLE public.manage_users_table;
                INSERT INTO public.manage_users_table
                SELECT
                    coalesce(u.username, '-') AS "Username",
                    coalesce(u.role, '-') AS "Role",
                    ''::text AS "Set New Password",
                    to_char(u.created_at + interval '7 hour', 'DD-MM-YYYY HH24:MI:SS') AS "Created",
                    ''::text AS "Action"
                FROM public.users u
                ORDER BY
                    CASE WHEN upper(coalesce(u.username, '')) = 'ADMIN' THEN 0 ELSE 1 END,
                    u.username ASC;
                RETURN NULL;
            END;
            $$;
            """
        )
        con.exec_driver_sql(
            "DROP TRIGGER IF EXISTS trg_refresh_manage_users_table_users ON public.users"
        )
        con.exec_driver_sql(
            """
            CREATE TRIGGER trg_refresh_manage_users_table_users
            AFTER INSERT OR UPDATE OR DELETE OR TRUNCATE
            ON public.users
            FOR EACH STATEMENT
            EXECUTE FUNCTION public.refresh_manage_users_table()
            """
        )


LINE_MACHINE_ITEM_SEPARATOR = "|||"
LINE_MACHINE_MAP_SETTING_KEY = "line_machine_map_v1"
DEFAULT_LINE_MACHINE_MAP_FILE = os.path.join(
    os.path.abspath(os.path.join(BASE_DIR, "..")), "database", "monitoring_line_map.json"
)


def _load_line_monitoring_raw_from_file():
    map_path_env = (os.getenv("SUPPORTHUB_LINE_MACHINE_MAP_FILE") or "").strip()
    map_path = Path(map_path_env).expanduser() if map_path_env else Path(DEFAULT_LINE_MACHINE_MAP_FILE)
    if not map_path.exists():
        return {}
    try:
        raw = json.loads(map_path.read_text(encoding="utf-8") or "{}")
    except Exception as exc:
        print(f"[INIT] Failed to read line-monitoring map file ({map_path}): {exc}")
        return {}
    return raw if isinstance(raw, dict) else {}


def _normalize_line_monitoring_rows(raw_map):
    if not isinstance(raw_map, dict):
        return []

    rows = []
    seen = set()
    for raw_line_no, raw_items in raw_map.items():
        line_no = str(raw_line_no or "").strip().upper()
        if not line_no:
            continue
        values = raw_items if isinstance(raw_items, list) else [raw_items]
        for raw_item in values:
            item = str(raw_item or "").strip()
            if not item:
                continue
            machine_type = item
            machine_id = "-"
            if LINE_MACHINE_ITEM_SEPARATOR in item:
                left, right = item.split(LINE_MACHINE_ITEM_SEPARATOR, 1)
                machine_type = (left or "").strip()
                machine_id = (right or "").strip() or "-"
            if not machine_type:
                continue
            dedupe_key = (line_no.lower(), machine_type.lower(), machine_id.lower())
            if dedupe_key in seen:
                continue
            seen.add(dedupe_key)
            rows.append({
                "line_no": line_no,
                "machine_type": machine_type,
                "machine_id": machine_id,
                "action": "",
            })

    rows.sort(key=lambda r: (r["line_no"].lower(), r["machine_type"].lower(), r["machine_id"].lower()))
    return rows


def _load_line_monitoring_rows_for_postgres(con):
    line_map_table_exists = con.execute(
        text("SELECT to_regclass('public.master_line_monitoring_maps')")
    ).scalar()
    if line_map_table_exists:
        db_rows = con.execute(
            text(
                """
                SELECT line_no, machine_type, machine_id
                FROM public.master_line_monitoring_maps
                ORDER BY line_no ASC, machine_type ASC, machine_id ASC, id ASC
                """
            )
        ).mappings().all()
        if db_rows:
            return [
                {
                    "line_no": str(r["line_no"] or "").strip().upper(),
                    "machine_type": str(r["machine_type"] or "").strip(),
                    "machine_id": str(r["machine_id"] or "").strip() or "-",
                    "action": "",
                }
                for r in db_rows
                if str(r["line_no"] or "").strip() and str(r["machine_type"] or "").strip()
            ]

    raw_map = _load_line_monitoring_raw_from_file()
    if raw_map:
        return _normalize_line_monitoring_rows(raw_map)

    legacy_row = con.execute(
        text("SELECT value FROM public.app_settings WHERE key = :k LIMIT 1"),
        {"k": LINE_MACHINE_MAP_SETTING_KEY},
    ).scalar()
    if not legacy_row:
        return []
    try:
        legacy_raw = json.loads(legacy_row)
    except Exception:
        return []
    return _normalize_line_monitoring_rows(legacy_raw)


def _refresh_postgres_line_to_monitoring_page_table(con) -> None:
    table_name = "add_machine_line_to_monitoring_page_table"
    con.exec_driver_sql(f"DROP TABLE IF EXISTS public.{table_name}")
    con.exec_driver_sql(
        f"""
        CREATE TABLE public.{table_name} (
            "Line No." text,
            "Machine Type" text,
            "Machine ID" text,
            "Action" text
        )
        """
    )

    rows = _load_line_monitoring_rows_for_postgres(con)
    if rows:
        con.execute(
            text(
                f"""
                INSERT INTO public.{table_name} ("Line No.", "Machine Type", "Machine ID", "Action")
                VALUES (:line_no, :machine_type, :machine_id, :action)
                """
            ),
            rows,
        )


def refresh_postgres_line_to_monitoring_page_table() -> None:
    if engine.dialect.name != "postgresql" or not ENABLE_POSTGRES_DISPLAY_TABLES:
        return
    with engine.begin() as con:
        _refresh_postgres_line_to_monitoring_page_table(con)


def _ensure_postgres_add_machine_tables() -> None:
    if engine.dialect.name != "postgresql":
        return

    def _rebuild_table(con, table_name: str, select_sql: str, source_table: str, refresh_fn: str, trigger_name: str):
        con.exec_driver_sql(f"DROP TABLE IF EXISTS public.{table_name}")
        con.exec_driver_sql(
            f"CREATE TABLE public.{table_name} AS SELECT * FROM ({select_sql}) t WITH NO DATA"
        )
        con.exec_driver_sql(f"INSERT INTO public.{table_name} {select_sql}")
        con.exec_driver_sql(
            f"""
            CREATE OR REPLACE FUNCTION public.{refresh_fn}()
            RETURNS trigger
            LANGUAGE plpgsql
            AS $$
            BEGIN
                TRUNCATE TABLE public.{table_name};
                INSERT INTO public.{table_name}
                {select_sql};
                RETURN NULL;
            END;
            $$;
            """
        )
        con.exec_driver_sql(f"DROP TRIGGER IF EXISTS {trigger_name} ON public.{source_table}")
        con.exec_driver_sql(
            f"""
            CREATE TRIGGER {trigger_name}
            AFTER INSERT OR UPDATE OR DELETE OR TRUNCATE
            ON public.{source_table}
            FOR EACH STATEMENT
            EXECUTE FUNCTION public.{refresh_fn}()
            """
        )

    table_specs = (
        {
            "table_name": "add_machine_support_area_table",
            "source_table": "master_support_areas",
            "refresh_fn": "refresh_am_support_area_table",
            "trigger_name": "trg_refresh_am_support_area",
            "select_sql": """
            SELECT
                coalesce(sa.support_area, '-') AS "Support Area",
                to_char(sa.created_at + interval '7 hour', 'DD-MM-YYYY HH24:MI:SS') AS "Created",
                ''::text AS "Action"
            FROM public.master_support_areas sa
            ORDER BY sa.created_at ASC, sa.id ASC
            """,
        },
        {
            "table_name": "add_machine_support_area_to_machine_table",
            "source_table": "master_support_area_maps",
            "refresh_fn": "refresh_am_support_area_to_machine_table",
            "trigger_name": "trg_refresh_am_support_area_to_machine",
            "select_sql": """
            SELECT
                coalesce(sm.support_area, '-') AS "Support Area",
                coalesce(sm.machine, '-') AS "Machine",
                to_char(sm.created_at + interval '7 hour', 'DD-MM-YYYY HH24:MI:SS') AS "Created",
                ''::text AS "Action"
            FROM public.master_support_area_maps sm
            ORDER BY sm.created_at ASC, sm.id ASC
            """,
        },
        {
            "table_name": "add_machine_line_no_table",
            "source_table": "master_lines",
            "refresh_fn": "refresh_am_line_no_table",
            "trigger_name": "trg_refresh_am_line_no",
            "select_sql": """
            SELECT
                coalesce(l.line_no, '-') AS "Line No.",
                to_char(l.created_at + interval '7 hour', 'DD-MM-YYYY HH24:MI:SS') AS "Created",
                ''::text AS "Action"
            FROM public.master_lines l
            ORDER BY l.line_no ASC
            """,
        },
        {
            "table_name": "add_machine_machine_table",
            "source_table": "master_machines",
            "refresh_fn": "refresh_am_machine_table",
            "trigger_name": "trg_refresh_am_machine",
            "select_sql": """
            SELECT
                coalesce(m.machine, '-') AS "Machine",
                to_char(m.created_at + interval '7 hour', 'DD-MM-YYYY HH24:MI:SS') AS "Created",
                ''::text AS "Action"
            FROM public.master_machines m
            ORDER BY m.machine ASC
            """,
        },
        {
            "table_name": "add_machine_machine_type_table",
            "source_table": "master_machine_types",
            "refresh_fn": "refresh_am_machine_type_table",
            "trigger_name": "trg_refresh_am_machine_type",
            "select_sql": """
            SELECT
                coalesce(mt.machine, '-') AS "Machine",
                coalesce(mt.machine_type, '-') AS "Machine Type",
                to_char(mt.created_at + interval '7 hour', 'DD-MM-YYYY HH24:MI:SS') AS "Created",
                ''::text AS "Action"
            FROM public.master_machine_types mt
            ORDER BY mt.machine ASC, mt.machine_type ASC
            """,
        },
        {
            "table_name": "add_machine_machine_id_table",
            "source_table": "master_machine_ids",
            "refresh_fn": "refresh_am_machine_id_table",
            "trigger_name": "trg_refresh_am_machine_id",
            "select_sql": """
            SELECT
                coalesce(mi.machine, '-') AS "Machine",
                coalesce(mi.machine_type, '-') AS "Machine Type",
                coalesce(mi.machine_id, '-') AS "Machine ID",
                to_char(mi.created_at + interval '7 hour', 'DD-MM-YYYY HH24:MI:SS') AS "Created",
                ''::text AS "Action"
            FROM public.master_machine_ids mi
            ORDER BY mi.machine ASC, mi.machine_type ASC, mi.machine_id ASC
            """,
        },
        {
            "table_name": "add_machine_problem_table",
            "source_table": "master_problems",
            "refresh_fn": "refresh_am_problem_table",
            "trigger_name": "trg_refresh_am_problem",
            "select_sql": """
            SELECT
                coalesce(p.machine, '-') AS "Machine",
                coalesce(nullif(p.machine_type, ''), '-') AS "Machine Type",
                coalesce(p.problem, '-') AS "Problem",
                to_char(p.created_at + interval '7 hour', 'DD-MM-YYYY HH24:MI:SS') AS "Created",
                ''::text AS "Action"
            FROM public.master_problems p
            ORDER BY p.machine ASC, p.machine_type ASC, p.problem ASC
            """,
        },
        {
            "table_name": "add_machine_update_history_table",
            "source_table": "master_audit_logs",
            "refresh_fn": "refresh_am_update_history_table",
            "trigger_name": "trg_refresh_am_update_history",
            "select_sql": """
            SELECT
                to_char(a.created_at + interval '7 hour', 'DD-MM-YYYY HH24:MI:SS') AS "Created",
                coalesce(a.actor, '-') AS "User",
                coalesce(a.action, '-') AS "Action",
                coalesce(a.data_type, '-') AS "Data Type",
                coalesce(a.item, '-') AS "Item",
                coalesce(a.details, '-') AS "Details"
            FROM public.master_audit_logs a
            ORDER BY a.created_at DESC, a.id DESC
            """,
        },
    )

    with engine.begin() as con:
        for spec in table_specs:
            _rebuild_table(
                con,
                spec["table_name"],
                spec["select_sql"],
                spec["source_table"],
                spec["refresh_fn"],
                spec["trigger_name"],
            )

        _refresh_postgres_line_to_monitoring_page_table(con)


def _drop_postgres_display_table_artifacts() -> None:
    if engine.dialect.name != "postgresql":
        return

    display_tables = (
        "history_log_table",
        "manage_users_table",
        "add_machine_support_area_table",
        "add_machine_support_area_to_machine_table",
        "add_machine_line_no_table",
        "add_machine_machine_table",
        "add_machine_machine_type_table",
        "add_machine_machine_id_table",
        "add_machine_problem_table",
        "add_machine_update_history_table",
        "add_machine_line_to_monitoring_page_table",
    )
    trigger_specs = (
        ("trg_refresh_history_log_table_tickets", "tickets"),
        ("trg_refresh_history_log_table_takeover", "ticket_takeover_logs"),
        ("trg_refresh_manage_users_table_users", "users"),
        ("trg_refresh_am_support_area", "master_support_areas"),
        ("trg_refresh_am_support_area_to_machine", "master_support_area_maps"),
        ("trg_refresh_am_line_no", "master_lines"),
        ("trg_refresh_am_machine", "master_machines"),
        ("trg_refresh_am_machine_type", "master_machine_types"),
        ("trg_refresh_am_machine_id", "master_machine_ids"),
        ("trg_refresh_am_problem", "master_problems"),
        ("trg_refresh_am_update_history", "master_audit_logs"),
    )
    refresh_functions = (
        "refresh_history_log_table",
        "refresh_manage_users_table",
        "refresh_am_support_area_table",
        "refresh_am_support_area_to_machine_table",
        "refresh_am_line_no_table",
        "refresh_am_machine_table",
        "refresh_am_machine_type_table",
        "refresh_am_machine_id_table",
        "refresh_am_problem_table",
        "refresh_am_update_history_table",
    )

    with engine.begin() as con:
        for trigger_name, source_table in trigger_specs:
            con.exec_driver_sql(
                f"DROP TRIGGER IF EXISTS {trigger_name} ON public.{source_table}"
            )
        for fn_name in refresh_functions:
            con.exec_driver_sql(f"DROP FUNCTION IF EXISTS public.{fn_name}()")
        for table_name in display_tables:
            con.exec_driver_sql(f"DROP TABLE IF EXISTS public.{table_name}")


def _ensure_admin_user() -> None:
    db = None
    try:
        db = SessionLocal()
        admin = db.query(User).filter(User.username == "ADMIN").first()
        if not admin:
            bootstrap_password = (os.getenv("SUPPORTHUB_BOOTSTRAP_ADMIN_PASSWORD") or "").strip()
            if not bootstrap_password:
                raise RuntimeError(
                    "ADMIN user is missing. Set SUPPORTHUB_BOOTSTRAP_ADMIN_PASSWORD once to bootstrap ADMIN."
                )
            db.add(User(username="ADMIN", password_hash=sha256(bootstrap_password), role="Admin"))
            db.commit()
            return

        changed = False
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
    _ensure_postgres_iot_tables()
    _ensure_postgres_history_view()
    if ENABLE_POSTGRES_DISPLAY_TABLES:
        _ensure_postgres_history_table()
        _ensure_postgres_manage_users_table()
        _ensure_postgres_add_machine_tables()
    else:
        _drop_postgres_display_table_artifacts()
    _ensure_admin_user()
