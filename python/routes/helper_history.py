from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional

from sqlalchemy.orm import Session

from python.routes.helper_validation import default_clean_text


def normalize_history_filters(
    machine_type: Optional[str],
    machine_brand: Optional[str],
    equipment: Optional[str],
    clean_text: Optional[Callable[[Optional[str]], str]] = None,
) -> tuple[str, str]:
    _clean = clean_text or default_clean_text
    type_val = _clean(machine_type)
    brand_val = _clean(machine_brand)
    if type_val or brand_val:
        return type_val, brand_val

    raw = _clean(equipment)
    if not raw:
        return "", ""
    if "||" in raw:
        left, right = raw.split("||", 1)
        return _clean(left), _clean(right)
    return "", raw


def build_history_type_lookup(
    machine_type_map: Dict[str, List[str]],
    clean_text: Optional[Callable[[Optional[str]], str]] = None,
) -> tuple[Dict[str, str], Dict[str, str]]:
    _clean = clean_text or default_clean_text
    type_by_key: Dict[str, str] = {}
    brand_to_type: Dict[str, str] = {}

    for machine_type, brands in (machine_type_map or {}).items():
        machine_type_val = _clean(machine_type)
        if not machine_type_val:
            continue
        type_by_key[machine_type_val.lower()] = machine_type_val
        brand_to_type.setdefault(machine_type_val.lower(), machine_type_val)
        for brand in brands or []:
            brand_val = _clean(brand)
            if not brand_val:
                continue
            brand_to_type.setdefault(brand_val.lower(), machine_type_val)

    return type_by_key, brand_to_type


def parse_ticket_machine_and_brand(
    raw_equipment: Optional[str],
    type_by_key: Dict[str, str],
    brand_to_type: Dict[str, str],
    clean_text: Optional[Callable[[Optional[str]], str]] = None,
) -> tuple[str, str]:
    _clean = clean_text or default_clean_text
    raw = _clean(raw_equipment)
    if "||" in raw:
        left, right = raw.split("||", 1)
        return _clean(left), _clean(right)

    brand = raw
    if not brand:
        return "", ""

    if brand.lower() == "other m/c or tools":
        return "Etc..", brand

    machine_type = type_by_key.get(brand.lower()) or brand_to_type.get(brand.lower(), "")
    return machine_type, brand


def apply_history_machine_filters(
    rows: List[Any],
    machine_type: str,
    machine_brand: str,
    machine_type_map: Dict[str, List[str]],
    clean_text: Optional[Callable[[Optional[str]], str]] = None,
) -> List[Any]:
    _clean = clean_text or default_clean_text
    sel_type = _clean(machine_type).lower()
    sel_brand = _clean(machine_brand).lower()
    type_by_key, brand_to_type = build_history_type_lookup(machine_type_map, clean_text=_clean)
    out: List[Any] = []

    for row in rows:
        parsed_type, parsed_brand = parse_ticket_machine_and_brand(
            getattr(row, "equipment", None),
            type_by_key,
            brand_to_type,
            clean_text=_clean,
        )
        row.history_machine = parsed_type
        row.history_machine_type = parsed_brand

        if sel_type and parsed_type.lower() != sel_type:
            continue
        if sel_brand and parsed_brand.lower() != sel_brand:
            continue
        out.append(row)
    return out


def apply_problem_match_class_filter(
    rows: List[Any],
    db: Session,
    class_name: str,
    ProblemMatch: Any,
    clean_text: Optional[Callable[[Optional[str]], str]] = None,
) -> List[Any]:
    _clean = clean_text or default_clean_text
    class_key = _clean(class_name).lower()
    if not class_key:
        return rows

    match_rows = [
        row
        for row in db.query(ProblemMatch).all()
        if _clean(row.class_name).lower() == class_key and _clean(row.machine) and _clean(row.problem)
    ]
    if not match_rows:
        return []

    scoped_matches: Dict[tuple[str, str], List[Dict[str, str]]] = {}
    for row in match_rows:
        machine_val = _clean(row.machine)
        problem_val = _clean(row.problem)
        if not machine_val or not problem_val:
            continue
        scoped_matches.setdefault((machine_val.lower(), problem_val.lower()), []).append(
            {
                "machine_type": _clean(getattr(row, "machine_type", "")),
                "machine_id": _clean(getattr(row, "machine_id", "")),
            }
        )
    if not scoped_matches:
        return []

    out: List[Any] = []
    for row in rows:
        machine_val = _clean(getattr(row, "history_machine", ""))
        if not machine_val:
            equipment_val = _clean(getattr(row, "equipment", ""))
            if "||" in equipment_val:
                machine_val = _clean(equipment_val.split("||", 1)[0])
            else:
                machine_val = equipment_val
        machine_type_val = _clean(getattr(row, "history_machine_type", ""))
        machine_id_val = _clean(getattr(row, "machine_id", ""))
        problem_val = _clean(getattr(row, "problem", ""))
        if not machine_val or not problem_val:
            continue
        candidates = scoped_matches.get((machine_val.lower(), problem_val.lower()), [])
        best_score = -1
        for candidate in candidates:
            candidate_type = _clean(candidate.get("machine_type", ""))
            candidate_id = _clean(candidate.get("machine_id", ""))
            if candidate_type and candidate_type.lower() != machine_type_val.lower():
                continue
            if candidate_id and candidate_id.lower() != machine_id_val.lower():
                continue
            score = (1 if candidate_type else 0) + (1 if candidate_id else 0)
            if score > best_score:
                best_score = score
        if best_score >= 0:
            out.append(row)
    return out
