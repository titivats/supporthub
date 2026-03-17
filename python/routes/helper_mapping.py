from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional

from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from python.routes.helper_validation import default_clean_text, LINE_MACHINE_ITEM_SEPARATOR


def split_line_monitoring_item(
    raw_item: Optional[str],
    clean_text: Optional[Callable[[Optional[str]], str]] = None,
) -> tuple[str, str]:
    _clean = clean_text or default_clean_text
    item = _clean(raw_item)
    if not item:
        return "", ""
    if LINE_MACHINE_ITEM_SEPARATOR in item:
        left, right = item.split(LINE_MACHINE_ITEM_SEPARATOR, 1)
        return _clean(left), _clean(right)
    return item, ""


def normalize_line_monitoring_item(
    raw_item: Optional[str],
    clean_text: Optional[Callable[[Optional[str]], str]] = None,
) -> str:
    monitoring_item, machine_id = split_line_monitoring_item(raw_item, clean_text=clean_text)
    if not monitoring_item:
        return ""
    if machine_id:
        return f"{monitoring_item}{LINE_MACHINE_ITEM_SEPARATOR}{machine_id}"
    return monitoring_item


def line_monitoring_item_matches(
    raw_item: Optional[str],
    target_keys: set[str],
    clean_text: Optional[Callable[[Optional[str]], str]] = None,
) -> bool:
    _clean = clean_text or default_clean_text
    raw_norm = _clean(raw_item).lower()
    if raw_norm and raw_norm in target_keys:
        return True
    monitoring_item, machine_id = split_line_monitoring_item(raw_item, clean_text=_clean)
    monitoring_key = monitoring_item.lower()
    machine_id_key = machine_id.lower()
    return (monitoring_key and monitoring_key in target_keys) or (
        machine_id_key and machine_id_key in target_keys
    )


def flatten_line_machine_map(
    line_machine_map: Dict[str, List[str]],
    clean_text: Optional[Callable[[Optional[str]], str]] = None,
) -> List[Dict[str, str]]:
    _clean = clean_text or default_clean_text
    rows: List[Dict[str, str]] = []
    for line_no in sorted((line_machine_map or {}).keys(), key=lambda s: s.lower()):
        items = sorted(line_machine_map.get(line_no, []), key=lambda s: s.lower())
        for raw_item in items:
            monitoring_item, machine_id = split_line_monitoring_item(raw_item, clean_text=_clean)
            rows.append(
                {
                    "line_no": line_no,
                    "monitoring_item": monitoring_item or _clean(raw_item),
                    "machine_id": machine_id,
                    "raw_value": _clean(raw_item),
                }
            )
    return rows


def apply_monitoring_line_machine_map(
    rows: List[Any],
    line_machine_map: Dict[str, List[str]],
    include_full_context_label: bool = False,
    strict_mode: bool = True,
    clean_text: Optional[Callable[[Optional[str]], str]] = None,
) -> List[Any]:
    _clean = clean_text or default_clean_text

    normalized_map: Dict[str, List[Dict[str, str]]] = {}
    for line_no, items in (line_machine_map or {}).items():
        line_key = _clean(line_no).upper()
        if not line_key:
            continue
        allowed_entries: List[Dict[str, str]] = []
        seen = set()
        for raw_item in (items or []):
            item_type, machine_id = split_line_monitoring_item(raw_item, clean_text=_clean)
            if not item_type:
                continue
            dedupe_key = f"{item_type.lower()}{LINE_MACHINE_ITEM_SEPARATOR}{machine_id.lower()}"
            if dedupe_key in seen:
                continue
            seen.add(dedupe_key)
            allowed_entries.append(
                {
                    "item_type": item_type,
                    "item_type_l": item_type.lower(),
                    "machine_id": machine_id,
                    "machine_id_l": machine_id.lower(),
                }
            )
        if allowed_entries:
            normalized_map[line_key] = allowed_entries

    if not normalized_map:
        if strict_mode:
            return rows
        for row in rows:
            parsed_machine_raw = _clean(getattr(row, "history_machine", ""))
            parsed_type_raw = _clean(getattr(row, "history_machine_type", ""))
            parsed_machine_id_raw = _clean(getattr(row, "machine_id", ""))
            display_machine = parsed_machine_raw or "-"
            display_machine_type = parsed_type_raw or "-"
            display_machine_id = parsed_machine_id_raw or "-"
            row.mapped_monitoring_item = f"{display_machine} | {display_machine_type} | {display_machine_id}"
            row.mapped_monitoring_machine_id = parsed_machine_id_raw
        return rows

    out: List[Any] = []
    for row in rows:
        line_key = _clean(getattr(row, "machine", "")).upper()
        allowed = normalized_map.get(line_key)
        if not allowed:
            if strict_mode:
                continue
            parsed_machine_raw = _clean(getattr(row, "history_machine", ""))
            parsed_type_raw = _clean(getattr(row, "history_machine_type", ""))
            parsed_machine_id_raw = _clean(getattr(row, "machine_id", ""))
            display_machine = parsed_machine_raw or "-"
            display_machine_type = parsed_type_raw or "-"
            display_machine_id = parsed_machine_id_raw or "-"
            row.mapped_monitoring_item = f"{display_machine} | {display_machine_type} | {display_machine_id}"
            row.mapped_monitoring_machine_id = parsed_machine_id_raw
            out.append(row)
            continue

        parsed_machine_raw = _clean(getattr(row, "history_machine", ""))
        parsed_type_raw = _clean(getattr(row, "history_machine_type", ""))
        parsed_machine_id_raw = _clean(getattr(row, "machine_id", ""))
        parsed_machine = parsed_machine_raw.lower()
        parsed_type = parsed_type_raw.lower()
        parsed_machine_id = parsed_machine_id_raw.lower()
        raw_equipment = _clean(getattr(row, "equipment", "")).lower()
        candidates: List[str] = []
        for candidate in [parsed_machine_id, parsed_type, parsed_machine, raw_equipment]:
            if candidate and candidate not in candidates:
                candidates.append(candidate)
        if "||" in raw_equipment:
            left, right = raw_equipment.split("||", 1)
            for candidate in [_clean(left).lower(), _clean(right).lower()]:
                if candidate and candidate not in candidates:
                    candidates.append(candidate)

        matched_item = ""
        matched_machine_id = ""
        for entry in allowed:
            entry_machine_id = entry.get("machine_id_l", "")
            entry_type = entry.get("item_type", "")
            entry_type_l = entry.get("item_type_l", "")
            if entry_machine_id:
                id_match = any(c and c == entry_machine_id for c in candidates)
                type_match = any(c and c == entry_type_l for c in candidates)
                if id_match and (not entry_type_l or type_match):
                    matched_item = entry_type or entry.get("machine_id", "")
                    matched_machine_id = entry.get("machine_id", "")
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


def apply_line_support_area_filter(
    rows: List[Any],
    support_area: Optional[str],
    support_area_map: Dict[str, List[str]],
    clean_text: Optional[Callable[[Optional[str]], str]] = None,
) -> List[Any]:
    _clean = clean_text or default_clean_text
    selected = _clean(support_area)
    if not selected:
        return rows

    canonical_key = ""
    for key in (support_area_map or {}).keys():
        if _clean(key).lower() == selected.lower():
            canonical_key = key
            break
    if not canonical_key:
        return []

    allowed_machines = {
        _clean(machine).lower()
        for machine in (support_area_map.get(canonical_key) or [])
        if _clean(machine)
    }
    if not allowed_machines:
        return []

    out: List[Any] = []
    for row in rows:
        parsed_machine = _clean(getattr(row, "history_machine", "")).lower()
        if parsed_machine and parsed_machine in allowed_machines:
            out.append(row)
    return out


def build_monitoring_line_chart_metrics(
    rows: List[Any],
    start_utc,
    end_utc,
    build_monitoring_line_metrics: Callable[[List[Any], Any, Any], List[Dict[str, object]]],
    clean_text: Optional[Callable[[Optional[str]], str]] = None,
) -> List[Dict[str, object]]:
    _clean = clean_text or default_clean_text
    line_rows = build_monitoring_line_metrics(rows, start_utc, end_utc)
    if not line_rows:
        return []

    item_groups: Dict[tuple[str, str], List[Any]] = {}
    for row in rows:
        line_val = _clean(getattr(row, "machine", "")) or "-"
        item_val = _clean(getattr(row, "mapped_monitoring_item", ""))
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
        line_val = _clean(str(line_metric.get("line_op", ""))) or "-"
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


def redirect_admin_machines(status_key: str) -> RedirectResponse:
    return RedirectResponse(f"/admin/machines?status={status_key}", status_code=303)


def commit_master_change(db: Session, bump_active_version: Callable[[], None]) -> None:
    db.commit()
    bump_active_version()


def ensure_master_machine(
    db: Session,
    actor: str,
    machine_val: str,
    details: str,
    MasterMachine: Any,
    add_master_audit: Callable[..., None],
) -> None:
    if db.query(MasterMachine).filter(MasterMachine.machine == machine_val).first():
        return
    db.add(MasterMachine(machine=machine_val))
    add_master_audit(db, actor, "ADD", "MACHINE", machine_val, details=details)


def ensure_master_machine_type(
    db: Session,
    actor: str,
    machine_val: str,
    machine_type_val: str,
    details: str,
    MasterMachineType: Any,
    add_master_audit: Callable[..., None],
) -> None:
    if db.query(MasterMachineType).filter(
        MasterMachineType.machine == machine_val,
        MasterMachineType.machine_type == machine_type_val,
    ).first():
        return
    db.add(MasterMachineType(machine=machine_val, machine_type=machine_type_val))
    add_master_audit(
        db,
        actor,
        "ADD",
        "MACHINE_TYPE",
        f"{machine_val} || {machine_type_val}",
        details=details,
    )


def prune_line_machine_map(
    db: Session,
    target_keys: set[str],
    get_line_machine_map: Callable[[Session], Dict[str, List[str]]],
    save_line_machine_map: Callable[[Session, Dict[str, List[str]]], None],
    line_monitoring_item_matches_fn: Callable[[Optional[str], set[str]], bool],
    clean_text: Optional[Callable[[Optional[str]], str]] = None,
) -> int:
    _clean = clean_text or default_clean_text
    normalized_keys = {_clean(k).lower() for k in target_keys if _clean(k)}
    if not normalized_keys:
        return 0

    line_machine_map = get_line_machine_map(db)
    if not line_machine_map:
        return 0

    removed_items = 0
    for line_no in list(line_machine_map.keys()):
        items = list(line_machine_map.get(line_no, []))
        kept = [item for item in items if not line_monitoring_item_matches_fn(item, normalized_keys)]
        removed_items += len(items) - len(kept)
        if kept:
            line_machine_map[line_no] = kept
        else:
            line_machine_map.pop(line_no, None)

    if removed_items:
        save_line_machine_map(db, line_machine_map)
    return removed_items
