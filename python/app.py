from pathlib import Path
from time import perf_counter
import threading

from fastapi import FastAPI, Request
from fastapi.templating import Jinja2Templates

from python.auth import (
    BadSignature,
    SECURE_COOKIES,
    SESSION_AGE,
    make_session_token,
    read_session_token,
    sha256,
    verify_password,
)
from python.config_defaults import EQUIPMENTS
from python.database import (
    MasterAuditLog,
    MasterLine,
    MasterMachine,
    MasterMachineId,
    MasterMachineType,
    MasterProblem,
    MasterSupportArea,
    MasterSupportAreaMap,
    ProblemClass,
    ProblemMatch,
    Ticket,
    TicketTakeoverLog,
    User,
    get_db,
    init_db,
    run_db_maintenance,
)
from python.database.base import RUN_DB_MAINTENANCE_ON_STARTUP
from python.iot_monitor.iot_monitor_service import iot_monitor
from python.logging_utils import (
    configure_daily_app_logging,
    get_supporthub_logger,
    should_skip_request_logging,
)
from python.master_data_service import (
    add_master_audit as _add_master_audit,
    build_master_data as _build_master_data,
    bump_active_version,
    bump_master_data_version,
    clean_text as _clean_text,
    current_active_version,
    ensure_master_seeded as _ensure_master_seeded,
    get_line_machine_map as _get_line_machine_map,
    get_master_rows_sorted as _get_master_rows_sorted,
    is_admin_user as _is_admin_user,
    master_status_text as _master_status_text,
    save_line_machine_map as _save_line_machine_map,
)
from python.monitor.monitor_service import (
    build_monitoring_line_metrics,
    build_monitoring_metrics,
    parse_th_date_range,
)
from python.routes.web_routes import register_web_routes
from python.time_utils import TH_OFFSET, fmt_hms as _fmt_hms, fmt_th


configure_daily_app_logging()
APP_LOGGER = get_supporthub_logger("app")
REQUEST_LOGGER = get_supporthub_logger("request")

PROJECT_DIR = Path(__file__).resolve().parent.parent
templates = Jinja2Templates(directory=str(PROJECT_DIR / "html"))

app = FastAPI(title="SupportHub")

_BOOTSTRAP_LOCK = threading.Lock()
_BOOTSTRAP_COMPLETE = False


def _run_optional_db_maintenance() -> None:
    try:
        run_db_maintenance()
        APP_LOGGER.info("Optional database maintenance complete")
    except Exception:
        APP_LOGGER.exception("Optional database maintenance failed")


def _run_runtime_bootstrap() -> None:
    global _BOOTSTRAP_COMPLETE
    with _BOOTSTRAP_LOCK:
        if _BOOTSTRAP_COMPLETE:
            return

        init_db()
        APP_LOGGER.info("Runtime database initialization complete")
        _ensure_master_seeded()
        bump_master_data_version()
        APP_LOGGER.info("Master data seed check complete")
        _BOOTSTRAP_COMPLETE = True


@app.on_event("startup")
def on_startup() -> None:
    _run_runtime_bootstrap()
    if RUN_DB_MAINTENANCE_ON_STARTUP:
        threading.Thread(
            target=_run_optional_db_maintenance,
            name="supporthub-db-maintenance",
            daemon=True,
        ).start()
    iot_monitor.start()
    APP_LOGGER.info("Application startup complete")


@app.on_event("shutdown")
def on_shutdown() -> None:
    iot_monitor.stop()
    APP_LOGGER.info("Application shutdown complete")


@app.get("/api/active/version")
def api_active_version():
    return {"version": current_active_version()}


@app.middleware("http")
async def log_http_requests(request: Request, call_next):
    started = perf_counter()
    path = request.url.path or "/"
    query = request.url.query or ""
    full_path = f"{path}?{query}" if query else path
    client_ip = request.client.host if request.client else "-"

    try:
        response = await call_next(request)
    except Exception:
        elapsed_ms = (perf_counter() - started) * 1000.0
        if not should_skip_request_logging(path):
            REQUEST_LOGGER.exception(
                "%s %s -> 500 | %.2f ms | ip=%s",
                request.method,
                full_path,
                elapsed_ms,
                client_ip,
            )
        raise

    elapsed_ms = (perf_counter() - started) * 1000.0
    if not should_skip_request_logging(path):
        REQUEST_LOGGER.info(
            "%s %s -> %s | %.2f ms | ip=%s",
            request.method,
            full_path,
            response.status_code,
            elapsed_ms,
            client_ip,
        )
    return response


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
        "MasterAuditLog": MasterAuditLog,
        "BadSignature": BadSignature,
        "SECURE_COOKIES": SECURE_COOKIES,
        "SESSION_AGE": SESSION_AGE,
        "make_session_token": make_session_token,
        "read_session_token": read_session_token,
        "sha256": sha256,
        "verify_password": verify_password,
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
        "bump_master_data_version": bump_master_data_version,
        "EQUIPMENTS": EQUIPMENTS,
        "iot_monitor": iot_monitor,
    },
)
