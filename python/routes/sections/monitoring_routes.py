from __future__ import annotations

from typing import Dict, List, Optional

from fastapi import Depends, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from python.routes.sections.history_monitoring_common import query_done_or_cancel


def register_monitoring_routes(app, templates, ctx):
    get_db = ctx["get_db"]
    Ticket = ctx["Ticket"]
    parse_th_date_range = ctx["parse_th_date_range"]
    build_monitoring_metrics = ctx["build_monitoring_metrics"]
    _clean_text = ctx["_clean_text"]
    _build_master_data = ctx["_build_master_data"]
    _apply_history_machine_filters = ctx["_apply_history_machine_filters"]
    _apply_problem_match_class_filter = ctx["_apply_problem_match_class_filter"]
    MONITORING_DOWNTIME_CLASS = ctx["MONITORING_DOWNTIME_CLASS"]
    _normalize_history_filters = ctx["_normalize_history_filters"]
    _apply_line_support_area_filter = ctx["_apply_line_support_area_filter"]
    _apply_monitoring_line_machine_map = ctx["_apply_monitoring_line_machine_map"]
    _build_monitoring_line_chart_metrics = ctx["_build_monitoring_line_chart_metrics"]
    get_current_user = ctx["get_current_user"]

    @app.get("/monitoring", response_class=HTMLResponse)
    def monitoring(
        request: Request,
        line_op: Optional[str] = Query(None),
        machine_type: Optional[str] = Query(None),
        machine_brand: Optional[str] = Query(None),
        equipment: Optional[str] = Query(None),  # backward-compatible query param
        start_date: Optional[str] = Query(None),
        end_date: Optional[str] = Query(None),
        apply: Optional[str] = Query(None),
        line_support_area: Optional[str] = Query(None),
        line_machine_type: Optional[str] = Query(None),
        line_machine_brand: Optional[str] = Query(None),
        line_start_date: Optional[str] = Query(None),
        line_end_date: Optional[str] = Query(None),
        line_apply: Optional[str] = Query(None),
        clear_availability: Optional[str] = Query(None),
        clear_oee: Optional[str] = Query(None),  # backward-compatible query param
        clear_line: Optional[str] = Query(None),
        db: Session = Depends(get_db),
    ):
        try:
            user = get_current_user(request, db)
        except HTTPException:
            return RedirectResponse("/login", status_code=302)

        master = _build_master_data(db)
        machine_type_val, machine_brand_val = _normalize_history_filters(machine_type, machine_brand, equipment)
        line_support_area_val = _clean_text(line_support_area)
        if not line_support_area_val:
            line_support_area_val = _clean_text(line_machine_type)  # backward-compatible query param
        applied = (apply or "").strip() == "1"
        line_applied = (line_apply or "").strip() == "1"

        if (clear_availability or clear_oee or "").strip() == "1":
            line_op = ""
            machine_type_val = ""
            machine_brand_val = ""
            start_date = ""
            end_date = ""
            applied = False

        if (clear_line or "").strip() == "1":
            line_support_area_val = ""
            line_start_date = ""
            line_end_date = ""
            line_applied = False

        rows: List[Ticket] = []
        metrics = None
        filtered_count = 0
        line_metrics: List[Dict[str, object]] = []

        start_utc = end_utc = None
        try:
            start_utc, end_utc = parse_th_date_range(start_date, end_date)
        except Exception:
            start_utc = end_utc = None

        if applied:
            rows = query_done_or_cancel(db, Ticket, line_op, None, start_utc, end_utc)
            rows = _apply_history_machine_filters(rows, machine_type_val, machine_brand_val, master["machine_type_map"])
            rows = _apply_problem_match_class_filter(rows, db, MONITORING_DOWNTIME_CLASS)
            filtered_count = len(rows)
            metrics = build_monitoring_metrics(rows, start_utc, end_utc)

        line_start_utc = line_end_utc = None
        try:
            line_start_utc, line_end_utc = parse_th_date_range(line_start_date, line_end_date)
        except Exception:
            line_start_utc = line_end_utc = None

        if line_applied:
            chart_rows = query_done_or_cancel(db, Ticket, None, None, line_start_utc, line_end_utc)
            chart_rows = _apply_history_machine_filters(chart_rows, "", "", master["machine_type_map"])
            chart_rows = _apply_problem_match_class_filter(chart_rows, db, MONITORING_DOWNTIME_CLASS)
            chart_rows = _apply_line_support_area_filter(
                chart_rows,
                line_support_area_val,
                master.get("support_area_map", {}),
            )
            chart_rows = _apply_monitoring_line_machine_map(
                chart_rows,
                master.get("line_machine_map", {}),
                include_full_context_label=True,
                strict_mode=True,
            )
            line_metrics = _build_monitoring_line_chart_metrics(chart_rows, line_start_utc, line_end_utc)

        return templates.TemplateResponse(
            "monitoring.html",
            {
                "request": request,
                "user": user,
                "line_ops": master["line_ops"],
                "machine_type_map": master["machine_type_map"],
                "support_areas": master.get("support_areas", []),
                "line_op": line_op or "",
                "machine_type": machine_type_val,
                "machine_brand": machine_brand_val,
                "start_date": start_date or "",
                "end_date": end_date or "",
                "applied": applied,
                "metrics": metrics,
                "filtered_count": filtered_count,
                "line_support_area": line_support_area_val,
                "line_start_date": line_start_date or "",
                "line_end_date": line_end_date or "",
                "line_applied": line_applied,
                "line_metrics": line_metrics,
                "downtime_class_name": MONITORING_DOWNTIME_CLASS,
            },
        )
