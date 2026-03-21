from typing import Dict, List, Optional

from fastapi import HTTPException, Request
from sqlalchemy.orm import Session

from python.routes.helpers import (
    apply_history_machine_filters,
    apply_line_support_area_filter,
    apply_monitoring_line_machine_map,
    apply_problem_match_class_filter,
    build_history_type_lookup,
    build_monitoring_line_chart_metrics,
    commit_master_change,
    ensure_master_machine,
    ensure_master_machine_type,
    flatten_line_machine_map,
    is_valid_manage_password,
    is_valid_manage_username,
    line_monitoring_item_matches,
    normalize_history_filters,
    normalize_line_monitoring_item,
    normalize_role,
    parse_ticket_machine_and_brand,
    prune_line_machine_map,
    redirect_admin_machines,
    split_line_monitoring_item,
)
from python.routes.sections import (
    register_admin_machines_routes,
    register_auth_user_routes,
    register_history_monitoring_iot_routes,
    register_problem_match_routes,
    register_ticket_action_routes,
)


def register_web_routes(app, templates, deps):
    get_db = deps["get_db"]
    User = deps["User"]
    Ticket = deps["Ticket"]
    TicketTakeoverLog = deps["TicketTakeoverLog"]
    MasterLine = deps["MasterLine"]
    MasterMachine = deps["MasterMachine"]
    MasterMachineType = deps["MasterMachineType"]
    MasterMachineId = deps["MasterMachineId"]
    MasterProblem = deps["MasterProblem"]
    ProblemClass = deps["ProblemClass"]
    ProblemMatch = deps["ProblemMatch"]
    MasterSupportArea = deps["MasterSupportArea"]
    MasterSupportAreaMap = deps["MasterSupportAreaMap"]
    BadSignature = deps["BadSignature"]
    SECURE_COOKIES = deps["SECURE_COOKIES"]
    SESSION_AGE = deps["SESSION_AGE"]
    make_session_token = deps["make_session_token"]
    read_session_token = deps["read_session_token"]
    sha256 = deps["sha256"]
    verify_password = deps["verify_password"]
    parse_th_date_range = deps["parse_th_date_range"]
    build_monitoring_metrics = deps["build_monitoring_metrics"]
    build_monitoring_line_metrics = deps["build_monitoring_line_metrics"]
    TH_OFFSET = deps["TH_OFFSET"]
    _fmt_hms = deps["_fmt_hms"]
    fmt_th = deps["fmt_th"]
    _clean_text = deps["_clean_text"]
    _is_admin_user = deps["_is_admin_user"]
    _build_master_data = deps["_build_master_data"]
    get_line_machine_map = deps["get_line_machine_map"]
    save_line_machine_map = deps["save_line_machine_map"]
    _master_status_text = deps["_master_status_text"]
    _add_master_audit = deps["_add_master_audit"]
    _get_master_rows_sorted = deps["_get_master_rows_sorted"]
    bump_active_version = deps["bump_active_version"]
    bump_master_data_version = deps["bump_master_data_version"]
    EQUIPMENTS = deps["EQUIPMENTS"]
    iot_monitor = deps["iot_monitor"]

    MONITORING_DOWNTIME_CLASS = "Machine Downtime"

    def _is_valid_manage_username(username: str) -> bool:
        return is_valid_manage_username(username)

    def _is_valid_manage_password(password: str) -> bool:
        return is_valid_manage_password(password)

    def _normalize_role(role: Optional[str], allow_admin: bool) -> str:
        return normalize_role(role, allow_admin)

    def _split_line_monitoring_item(raw_item: Optional[str]) -> tuple[str, str]:
        return split_line_monitoring_item(raw_item, clean_text=_clean_text)

    def _normalize_line_monitoring_item(raw_item: Optional[str]) -> str:
        return normalize_line_monitoring_item(raw_item, clean_text=_clean_text)

    def _line_monitoring_item_matches(raw_item: Optional[str], target_keys: set[str]) -> bool:
        return line_monitoring_item_matches(raw_item, target_keys, clean_text=_clean_text)

    def _flatten_line_machine_map(line_machine_map: Dict[str, List[str]]) -> List[Dict[str, str]]:
        return flatten_line_machine_map(line_machine_map, clean_text=_clean_text)

    def _apply_monitoring_line_machine_map(
        rows: List[Ticket],
        line_machine_map: Dict[str, List[str]],
        include_full_context_label: bool = False,
        strict_mode: bool = True,
    ) -> List[Ticket]:
        return apply_monitoring_line_machine_map(
            rows,
            line_machine_map,
            include_full_context_label=include_full_context_label,
            strict_mode=strict_mode,
            clean_text=_clean_text,
        )

    def _apply_line_support_area_filter(
        rows: List[Ticket],
        support_area: Optional[str],
        support_area_map: Dict[str, List[str]],
    ) -> List[Ticket]:
        return apply_line_support_area_filter(
            rows,
            support_area,
            support_area_map,
            clean_text=_clean_text,
        )

    def _build_monitoring_line_chart_metrics(
        rows: List[Ticket],
        start_utc,
        end_utc,
    ) -> List[Dict[str, object]]:
        return build_monitoring_line_chart_metrics(
            rows,
            start_utc,
            end_utc,
            build_monitoring_line_metrics=build_monitoring_line_metrics,
            clean_text=_clean_text,
        )

    def _normalize_history_filters(
        machine_type: Optional[str],
        machine_brand: Optional[str],
        equipment: Optional[str],
    ) -> tuple[str, str]:
        return normalize_history_filters(
            machine_type,
            machine_brand,
            equipment,
            clean_text=_clean_text,
        )

    def _build_history_type_lookup(machine_type_map: Dict[str, List[str]]) -> tuple[Dict[str, str], Dict[str, str]]:
        return build_history_type_lookup(machine_type_map, clean_text=_clean_text)

    def _parse_ticket_machine_and_brand(
        raw_equipment: Optional[str],
        type_by_key: Dict[str, str],
        brand_to_type: Dict[str, str],
    ) -> tuple[str, str]:
        return parse_ticket_machine_and_brand(
            raw_equipment,
            type_by_key,
            brand_to_type,
            clean_text=_clean_text,
        )

    def _apply_history_machine_filters(
        rows: List[Ticket],
        machine_type: str,
        machine_brand: str,
        machine_type_map: Dict[str, List[str]],
    ) -> List[Ticket]:
        return apply_history_machine_filters(
            rows,
            machine_type,
            machine_brand,
            machine_type_map,
            clean_text=_clean_text,
        )

    def _apply_problem_match_class_filter(
        rows: List[Ticket],
        db: Session,
        class_name: str,
    ) -> List[Ticket]:
        return apply_problem_match_class_filter(
            rows,
            db,
            class_name,
            ProblemMatch=ProblemMatch,
            clean_text=_clean_text,
        )

    def _redirect_admin_machines(status_key: str):
        return redirect_admin_machines(status_key)

    def get_current_user(request: Request, db: Session) -> User:
        token = request.cookies.get("session")
        if not token:
            raise HTTPException(status_code=401, detail="Not logged in")
        try:
            username = read_session_token(token)
        except BadSignature:
            raise HTTPException(status_code=401, detail="Bad/expired session")
        user = db.query(User).filter(User.username == username).first()
        if not user:
            raise HTTPException(status_code=401, detail="User not found")
        return user

    def _require_admin_user(request: Request, db: Session) -> User:
        me = get_current_user(request, db)
        if not _is_admin_user(me):
            raise HTTPException(status_code=403, detail="Forbidden")
        return me

    def _commit_master_change(db: Session) -> None:
        commit_master_change(
            db,
            bump_active_version=bump_active_version,
            bump_master_data_version=bump_master_data_version,
        )

    def _ensure_master_machine(db: Session, actor: str, machine_val: str, details: str) -> None:
        ensure_master_machine(
            db,
            actor,
            machine_val,
            details,
            MasterMachine=MasterMachine,
            add_master_audit=_add_master_audit,
        )

    def _ensure_master_machine_type(
        db: Session,
        actor: str,
        machine_val: str,
        machine_type_val: str,
        details: str,
    ) -> None:
        ensure_master_machine_type(
            db,
            actor,
            machine_val,
            machine_type_val,
            details,
            MasterMachineType=MasterMachineType,
            add_master_audit=_add_master_audit,
        )

    def _prune_line_machine_map(db: Session, target_keys: set[str]) -> int:
        return prune_line_machine_map(
            db,
            target_keys,
            get_line_machine_map=get_line_machine_map,
            save_line_machine_map=save_line_machine_map,
            line_monitoring_item_matches_fn=_line_monitoring_item_matches,
            clean_text=_clean_text,
        )

    route_ctx = {
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
        "SECURE_COOKIES": SECURE_COOKIES,
        "SESSION_AGE": SESSION_AGE,
        "make_session_token": make_session_token,
        "sha256": sha256,
        "verify_password": verify_password,
        "parse_th_date_range": parse_th_date_range,
        "build_monitoring_metrics": build_monitoring_metrics,
        "build_monitoring_line_metrics": build_monitoring_line_metrics,
        "TH_OFFSET": TH_OFFSET,
        "_fmt_hms": _fmt_hms,
        "fmt_th": fmt_th,
        "_clean_text": _clean_text,
        "_build_master_data": _build_master_data,
        "get_line_machine_map": get_line_machine_map,
        "save_line_machine_map": save_line_machine_map,
        "_master_status_text": _master_status_text,
        "_add_master_audit": _add_master_audit,
        "_get_master_rows_sorted": _get_master_rows_sorted,
        "bump_active_version": bump_active_version,
        "EQUIPMENTS": EQUIPMENTS,
        "iot_monitor": iot_monitor,
        "_is_valid_manage_username": _is_valid_manage_username,
        "_is_valid_manage_password": _is_valid_manage_password,
        "_normalize_role": _normalize_role,
        "_split_line_monitoring_item": _split_line_monitoring_item,
        "_normalize_line_monitoring_item": _normalize_line_monitoring_item,
        "_flatten_line_machine_map": _flatten_line_machine_map,
        "_apply_monitoring_line_machine_map": _apply_monitoring_line_machine_map,
        "_apply_line_support_area_filter": _apply_line_support_area_filter,
        "_build_monitoring_line_chart_metrics": _build_monitoring_line_chart_metrics,
        "_normalize_history_filters": _normalize_history_filters,
        "_build_history_type_lookup": _build_history_type_lookup,
        "_parse_ticket_machine_and_brand": _parse_ticket_machine_and_brand,
        "_apply_history_machine_filters": _apply_history_machine_filters,
        "_apply_problem_match_class_filter": _apply_problem_match_class_filter,
        "MONITORING_DOWNTIME_CLASS": MONITORING_DOWNTIME_CLASS,
        "_redirect_admin_machines": _redirect_admin_machines,
        "_require_admin_user": _require_admin_user,
        "_commit_master_change": _commit_master_change,
        "_ensure_master_machine": _ensure_master_machine,
        "_ensure_master_machine_type": _ensure_master_machine_type,
        "_prune_line_machine_map": _prune_line_machine_map,
        "get_current_user": get_current_user,
    }

    register_auth_user_routes(app, templates, route_ctx)
    register_admin_machines_routes(app, templates, route_ctx)
    register_problem_match_routes(app, templates, route_ctx)
    register_ticket_action_routes(app, templates, route_ctx)
    register_history_monitoring_iot_routes(app, templates, route_ctx)




