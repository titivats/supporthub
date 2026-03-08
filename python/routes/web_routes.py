from datetime import datetime
from typing import Dict, List, Optional
import re

from fastapi import HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from python.routes.sections import (
    register_admin_machines_routes,
    register_auth_user_routes,
    register_history_monitoring_iot_routes,
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
    MasterSupportArea = deps["MasterSupportArea"]
    MasterSupportAreaMap = deps["MasterSupportAreaMap"]
    BadSignature = deps["BadSignature"]
    SECURE_COOKIES = deps["SECURE_COOKIES"]
    SESSION_AGE = deps["SESSION_AGE"]
    make_session_token = deps["make_session_token"]
    read_session_token = deps["read_session_token"]
    sha256 = deps["sha256"]
    verify_password = deps["verify_password"]
    line_notify = deps["line_notify"]
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
    EQUIPMENTS = deps["EQUIPMENTS"]
    iot_monitor = deps["iot_monitor"]

    LINE_MACHINE_ITEM_SEPARATOR = "|||"
    USERNAME_NUMERIC_PATTERN = re.compile(r"^\d{6}$")
    ALLOWED_ROLES = ("Operator", "Engineer", "Technician", "Admin")
    PUBLIC_SIGNUP_ROLES = ("Operator", "Engineer", "Technician")

    def _is_valid_manage_username(username: str) -> bool:
        return bool(USERNAME_NUMERIC_PATTERN.fullmatch((username or "").strip()))

    def _is_valid_manage_password(password: str) -> bool:
        return 1 <= len((password or "")) <= 12

    def _normalize_role(role: Optional[str], allow_admin: bool) -> str:
        raw = (role or "").strip()
        allowed = ALLOWED_ROLES if allow_admin else PUBLIC_SIGNUP_ROLES
        return raw if raw in allowed else ""

    def _split_line_monitoring_item(raw_item: Optional[str]) -> tuple[str, str]:
        item = _clean_text(raw_item)
        if not item:
            return "", ""
        if LINE_MACHINE_ITEM_SEPARATOR in item:
            left, right = item.split(LINE_MACHINE_ITEM_SEPARATOR, 1)
            return _clean_text(left), _clean_text(right)
        return item, ""

    def _normalize_line_monitoring_item(raw_item: Optional[str]) -> str:
        monitoring_item, machine_id = _split_line_monitoring_item(raw_item)
        if not monitoring_item:
            return ""
        if machine_id:
            return f"{monitoring_item}{LINE_MACHINE_ITEM_SEPARATOR}{machine_id}"
        return monitoring_item

    def _line_monitoring_item_matches(raw_item: Optional[str], target_keys: set[str]) -> bool:
        raw_norm = _clean_text(raw_item).lower()
        if raw_norm and raw_norm in target_keys:
            return True
        monitoring_item, machine_id = _split_line_monitoring_item(raw_item)
        monitoring_key = monitoring_item.lower()
        machine_id_key = machine_id.lower()
        return (monitoring_key and monitoring_key in target_keys) or (machine_id_key and machine_id_key in target_keys)

    def _flatten_line_machine_map(line_machine_map: Dict[str, List[str]]) -> List[Dict[str, str]]:
        rows: List[Dict[str, str]] = []
        for line_no in sorted((line_machine_map or {}).keys(), key=lambda s: s.lower()):
            items = sorted(line_machine_map.get(line_no, []), key=lambda s: s.lower())
            for raw_item in items:
                monitoring_item, machine_id = _split_line_monitoring_item(raw_item)
                rows.append({
                    "line_no": line_no,
                    "monitoring_item": monitoring_item or _clean_text(raw_item),
                    "machine_id": machine_id,
                    "raw_value": _clean_text(raw_item),
                })
        return rows

    def _apply_monitoring_line_machine_map(
        rows: List[Ticket],
        line_machine_map: Dict[str, List[str]],
        include_full_context_label: bool = False,
        strict_mode: bool = True,
    ) -> List[Ticket]:
        normalized_map: Dict[str, List[Dict[str, str]]] = {}
        for line_no, items in (line_machine_map or {}).items():
            line_key = _clean_text(line_no).upper()
            if not line_key:
                continue
            allowed_entries: List[Dict[str, str]] = []
            seen = set()
            for raw_item in (items or []):
                item_type, machine_id = _split_line_monitoring_item(raw_item)
                if not item_type:
                    continue
                dedupe_key = f"{item_type.lower()}{LINE_MACHINE_ITEM_SEPARATOR}{machine_id.lower()}"
                if dedupe_key in seen:
                    continue
                seen.add(dedupe_key)
                allowed_entries.append({
                    "item_type": item_type,
                    "item_type_l": item_type.lower(),
                    "machine_id": machine_id,
                    "machine_id_l": machine_id.lower(),
                })
            if allowed_entries:
                normalized_map[line_key] = allowed_entries

        if not normalized_map:
            if strict_mode:
                return rows
            for row in rows:
                parsed_machine_raw = _clean_text(getattr(row, "history_machine", ""))
                parsed_type_raw = _clean_text(getattr(row, "history_machine_type", ""))
                parsed_machine_id_raw = _clean_text(getattr(row, "machine_id", ""))
                display_machine = parsed_machine_raw or "-"
                display_machine_type = parsed_type_raw or "-"
                display_machine_id = parsed_machine_id_raw or "-"
                row.mapped_monitoring_item = f"{display_machine} | {display_machine_type} | {display_machine_id}"
                row.mapped_monitoring_machine_id = parsed_machine_id_raw
            return rows

        out: List[Ticket] = []
        for row in rows:
            line_key = _clean_text(getattr(row, "machine", "")).upper()
            allowed = normalized_map.get(line_key)
            if not allowed:
                if strict_mode:
                    continue
                parsed_machine_raw = _clean_text(getattr(row, "history_machine", ""))
                parsed_type_raw = _clean_text(getattr(row, "history_machine_type", ""))
                parsed_machine_id_raw = _clean_text(getattr(row, "machine_id", ""))
                display_machine = parsed_machine_raw or "-"
                display_machine_type = parsed_type_raw or "-"
                display_machine_id = parsed_machine_id_raw or "-"
                row.mapped_monitoring_item = f"{display_machine} | {display_machine_type} | {display_machine_id}"
                row.mapped_monitoring_machine_id = parsed_machine_id_raw
                out.append(row)
                continue

            parsed_machine_raw = _clean_text(getattr(row, "history_machine", ""))
            parsed_type_raw = _clean_text(getattr(row, "history_machine_type", ""))
            parsed_machine_id_raw = _clean_text(getattr(row, "machine_id", ""))
            parsed_machine = parsed_machine_raw.lower()
            parsed_type = parsed_type_raw.lower()
            parsed_machine_id = parsed_machine_id_raw.lower()
            raw_equipment = _clean_text(getattr(row, "equipment", "")).lower()
            candidates: List[str] = []
            for candidate in [parsed_machine_id, parsed_type, parsed_machine, raw_equipment]:
                if candidate and candidate not in candidates:
                    candidates.append(candidate)
            if "||" in raw_equipment:
                left, right = raw_equipment.split("||", 1)
                for candidate in [_clean_text(left).lower(), _clean_text(right).lower()]:
                    if candidate and candidate not in candidates:
                        candidates.append(candidate)

            matched_item = ""
            matched_machine_id = ""
            for entry in allowed:
                entry_machine_id = entry.get("machine_id_l", "")
                entry_type = entry.get("item_type", "")
                entry_type_l = entry.get("item_type_l", "")
                if entry_machine_id:
                    if any(c and c == entry_machine_id for c in candidates):
                        matched_item = entry_type or entry.get("machine_id", "")
                        matched_machine_id = entry.get("machine_id", "")
                        break
                    if any(c and c == entry_type_l for c in candidates):
                        matched_item = entry_type
                        matched_machine_id = ""
                        break
                    continue
                if any(c and c == entry_type_l for c in candidates):
                    matched_item = entry_type
                    break

            if not matched_item:
                for c in candidates:
                    if not c or len(c) < 3:
                        continue
                    for entry in allowed:
                        if entry.get("machine_id_l", ""):
                            continue
                        entry_type_l = entry.get("item_type_l", "")
                        if len(entry_type_l) >= 3 and (entry_type_l in c or c in entry_type_l):
                            matched_item = entry.get("item_type", "")
                            matched_machine_id = entry.get("machine_id", "")
                            break
                    if matched_item:
                        break

            if matched_item:
                if include_full_context_label:
                    display_machine = parsed_machine_raw or matched_item or "-"
                    display_machine_type = parsed_type_raw or matched_item or "-"
                    display_machine_id = parsed_machine_id_raw or matched_machine_id or "-"
                    row.mapped_monitoring_item = f"{display_machine} | {display_machine_type} | {display_machine_id}"
                else:
                    row.mapped_monitoring_item = matched_item
                row.mapped_monitoring_machine_id = matched_machine_id
                out.append(row)
            elif not strict_mode:
                display_machine = parsed_machine_raw or "-"
                display_machine_type = parsed_type_raw or "-"
                display_machine_id = parsed_machine_id_raw or "-"
                row.mapped_monitoring_item = f"{display_machine} | {display_machine_type} | {display_machine_id}"
                row.mapped_monitoring_machine_id = parsed_machine_id_raw
                out.append(row)

        return out

    def _apply_line_support_area_filter(rows: List[Ticket],
                                        support_area: Optional[str],
                                        support_area_map: Dict[str, List[str]]) -> List[Ticket]:
        selected = _clean_text(support_area)
        if not selected:
            return rows

        canonical_key = ""
        for key in (support_area_map or {}).keys():
            if _clean_text(key).lower() == selected.lower():
                canonical_key = key
                break
        if not canonical_key:
            return []

        allowed_machines = {
            _clean_text(machine).lower()
            for machine in (support_area_map.get(canonical_key) or [])
            if _clean_text(machine)
        }
        if not allowed_machines:
            return []

        out: List[Ticket] = []
        for row in rows:
            parsed_machine = _clean_text(getattr(row, "history_machine", "")).lower()
            if parsed_machine and parsed_machine in allowed_machines:
                out.append(row)
        return out

    def _build_monitoring_line_chart_metrics(rows: List[Ticket],
                                             start_utc: Optional[datetime],
                                             end_utc: Optional[datetime]) -> List[Dict[str, object]]:
        line_rows = build_monitoring_line_metrics(rows, start_utc, end_utc)
        if not line_rows:
            return []

        item_groups: Dict[tuple[str, str], List[Ticket]] = {}
        for row in rows:
            line_val = _clean_text(getattr(row, "machine", "")) or "-"
            item_val = _clean_text(getattr(row, "mapped_monitoring_item", ""))
            if not item_val:
                continue
            item_groups.setdefault((line_val, item_val), []).append(row)

        item_metrics_by_line: Dict[str, List[Dict[str, object]]] = {}
        for (line_val, item_val), group_rows in item_groups.items():
            grouped_metric_rows = build_monitoring_line_metrics(group_rows, start_utc, end_utc)
            if not grouped_metric_rows:
                continue

            metric = dict(grouped_metric_rows[0])
            metric["line_op"] = item_val
            metric["line_parent"] = line_val
            metric["is_item_breakdown"] = True
            item_metrics_by_line.setdefault(line_val.upper(), []).append(metric)

        out: List[Dict[str, object]] = []
        seen_lines = set()
        for line_metric in line_rows:
            line_val = _clean_text(str(line_metric.get("line_op", ""))) or "-"
            line_key = line_val.upper()
            seen_lines.add(line_key)

            line_copy = dict(line_metric)
            line_copy["line_parent"] = line_val
            line_copy["is_item_breakdown"] = False
            out.append(line_copy)

            item_rows = sorted(
                item_metrics_by_line.get(line_key, []),
                key=lambda m: str(m.get("line_op", "")).lower(),
            )
            out.extend(item_rows)

        for line_key in sorted(item_metrics_by_line.keys()):
            if line_key in seen_lines:
                continue
            extra_rows = sorted(
                item_metrics_by_line[line_key],
                key=lambda m: str(m.get("line_op", "")).lower(),
            )
            out.extend(extra_rows)

        return out

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

    def _redirect_admin_machines(status_key: str) -> RedirectResponse:
        return RedirectResponse(f"/admin/machines?status={status_key}", status_code=303)

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
        db.commit()
        bump_active_version()

    def _ensure_master_machine(db: Session, actor: str, machine_val: str, details: str) -> None:
        if db.query(MasterMachine).filter(MasterMachine.machine == machine_val).first():
            return
        db.add(MasterMachine(machine=machine_val))
        _add_master_audit(db, actor, "ADD", "MACHINE", machine_val, details=details)

    def _ensure_master_machine_type(
        db: Session,
        actor: str,
        machine_val: str,
        machine_type_val: str,
        details: str,
    ) -> None:
        if db.query(MasterMachineType).filter(
            MasterMachineType.machine == machine_val,
            MasterMachineType.machine_type == machine_type_val,
        ).first():
            return
        db.add(MasterMachineType(machine=machine_val, machine_type=machine_type_val))
        _add_master_audit(
            db,
            actor,
            "ADD",
            "MACHINE_TYPE",
            f"{machine_val} || {machine_type_val}",
            details=details,
        )

    def _prune_line_machine_map(db: Session, target_keys: set[str]) -> int:
        normalized_keys = {_clean_text(k).lower() for k in target_keys if _clean_text(k)}
        if not normalized_keys:
            return 0

        line_machine_map = get_line_machine_map(db)
        if not line_machine_map:
            return 0

        removed_items = 0
        for line_no in list(line_machine_map.keys()):
            items = list(line_machine_map.get(line_no, []))
            kept = [item for item in items if not _line_monitoring_item_matches(item, normalized_keys)]
            removed_items += len(items) - len(kept)
            if kept:
                line_machine_map[line_no] = kept
            else:
                line_machine_map.pop(line_no, None)

        if removed_items:
            save_line_machine_map(db, line_machine_map)
        return removed_items

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
        "MasterSupportArea": MasterSupportArea,
        "MasterSupportAreaMap": MasterSupportAreaMap,
        "SECURE_COOKIES": SECURE_COOKIES,
        "SESSION_AGE": SESSION_AGE,
        "make_session_token": make_session_token,
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
        "_apply_history_machine_filters": _apply_history_machine_filters,
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
    register_ticket_action_routes(app, templates, route_ctx)
    register_history_monitoring_iot_routes(app, templates, route_ctx)
