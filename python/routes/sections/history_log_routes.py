from __future__ import annotations

from datetime import datetime, time
from typing import Optional
import io

from fastapi import Depends, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse, StreamingResponse
from sqlalchemy.orm import Session

from python.routes.sections.history_monitoring_common import (
    build_takeover_logs_map,
    query_done_or_cancel,
)


def register_history_log_routes(app, templates, ctx):
    get_db = ctx["get_db"]
    Ticket = ctx["Ticket"]
    TicketTakeoverLog = ctx["TicketTakeoverLog"]
    TH_OFFSET = ctx["TH_OFFSET"]
    _fmt_hms = ctx["_fmt_hms"]
    fmt_th = ctx["fmt_th"]
    _build_master_data = ctx["_build_master_data"]
    _build_history_type_lookup = ctx["_build_history_type_lookup"]
    _parse_ticket_machine_and_brand = ctx["_parse_ticket_machine_and_brand"]
    _apply_history_machine_filters = ctx["_apply_history_machine_filters"]
    _normalize_history_filters = ctx["_normalize_history_filters"]
    get_current_user = ctx["get_current_user"]

    @app.get("/history", response_class=HTMLResponse)
    def history(
        request: Request,
        line_op: Optional[str] = Query(None),
        machine_type: Optional[str] = Query(None),
        machine_brand: Optional[str] = Query(None),
        machine_id: Optional[str] = Query(None),
        problem: Optional[str] = Query(None),
        equipment: Optional[str] = Query(None),  # backward-compatible query param
        start_date: Optional[str] = Query(None),
        end_date: Optional[str] = Query(None),
        db: Session = Depends(get_db),
    ):
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
        machine_id_val = (machine_id or "").strip()
        problem_val = (problem or "").strip()

        rows = query_done_or_cancel(db, Ticket, line_op, None, start_utc, end_utc)
        rows = _apply_history_machine_filters(rows, machine_type_val, machine_brand_val, master["machine_type_map"])
        machine_id_options = sorted(
            {(t.machine_id or "").strip() for t in rows if (t.machine_id or "").strip()},
            key=lambda s: s.lower(),
        )
        problem_options = sorted(
            {(t.problem or "").strip() for t in rows if (t.problem or "").strip()},
            key=lambda s: s.lower(),
        )
        if machine_id_val:
            rows = [t for t in rows if ((t.machine_id or "").strip().lower() == machine_id_val.lower())]
        if problem_val:
            rows = [t for t in rows if ((t.problem or "").strip().lower() == problem_val.lower())]
        takeover_logs_map = build_takeover_logs_map(db, TicketTakeoverLog, [t.id for t in rows])
        total_doing = sum((t.doing_secs or 0) for t in rows)
        total_hold = sum((t.hold_secs or 0) for t in rows)
        summary = {"doing": _fmt_hms(total_doing), "hold": _fmt_hms(total_hold)}

        return templates.TemplateResponse(
            "history_log.html",
            {
                "request": request,
                "user": user,
                "rows": rows,
                "summary": summary,
                "line_ops": master["line_ops"],
                "machine_type_map": master["machine_type_map"],
                "line_op": line_op or "",
                "machine_type": machine_type_val,
                "machine_brand": machine_brand_val,
                "machine_id": machine_id_val,
                "problem": problem_val,
                "machine_id_options": machine_id_options,
                "problem_options": problem_options,
                "takeover_logs_map": takeover_logs_map,
                "start_date": start_date or "",
                "end_date": end_date or "",
                "fmt_th": fmt_th,
            },
        )

    @app.get("/export/excel")
    def export_excel(
        request: Request,
        line_op: Optional[str] = Query(None),
        machine_type: Optional[str] = Query(None),
        machine_brand: Optional[str] = Query(None),
        machine_id: Optional[str] = Query(None),
        problem: Optional[str] = Query(None),
        equipment: Optional[str] = Query(None),  # backward-compatible query param
        start_date: Optional[str] = Query(None),
        end_date: Optional[str] = Query(None),
        db: Session = Depends(get_db),
    ):
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
        machine_id_val = (machine_id or "").strip()
        problem_val = (problem or "").strip()
        master = _build_master_data(db)
        rows = query_done_or_cancel(db, Ticket, line_op, None, start_utc, end_utc)
        rows = _apply_history_machine_filters(rows, machine_type_val, machine_brand_val, master["machine_type_map"])
        if machine_id_val:
            rows = [t for t in rows if ((t.machine_id or "").strip().lower() == machine_id_val.lower())]
        if problem_val:
            rows = [t for t in rows if ((t.problem or "").strip().lower() == problem_val.lower())]
        takeover_logs_map = build_takeover_logs_map(db, TicketTakeoverLog, [t.id for t in rows])
        type_by_key, brand_to_type = _build_history_type_lookup(master["machine_type_map"])

        buf = io.BytesIO()
        wb = xlsxwriter.Workbook(buf, {"in_memory": True})
        ws = wb.add_worksheet("History (TH)")

        ws.freeze_panes(1, 0)
        ws.autofilter(0, 0, 0, 19)
        ws.set_landscape()
        ws.fit_to_pages(1, 0)

        hdr = wb.add_format({"bold": True, "bg_color": "#EEF2FF", "border": 1})
        cell = wb.add_format({"border": 1})
        center = wb.add_format({"border": 1, "align": "center"})
        wrap = wb.add_format({"border": 1, "text_wrap": True})

        headers = [
            "ID",
            "Status",
            "Created (TH)",
            "Closed (TH)",
            "Request by",
            "Line No.",
            "Machine",
            "Machine Type",
            "Machine ID",
            "Problem",
            "Description",
            "Doing",
            "Hold",
            "Hold Reason",
            "Waiting Time",
            "Downtime",
            "Solution",
            "Cancel Reason",
            "Takeover Log",
            "Done By",
        ]
        for c, h in enumerate(headers):
            ws.write(0, c, h, hdr)

        def hms(sec: int) -> str:
            s = int(sec or 0)
            h, m, ss = s // 3600, (s % 3600) // 60, s % 60
            return f"{h:02d}:{m:02d}:{ss:02d}"

        def nz(v: Optional[str]) -> str:
            value = (v or "").strip()
            return value if value else "-"

        r = 1
        for t in rows:
            mtype, brand = _parse_ticket_machine_and_brand(t.equipment, type_by_key, brand_to_type)
            takeover_logs = takeover_logs_map.get(t.id, [])
            takeover_text = (
                "\n".join(f"{fmt_th(log.created_at)} | {log.from_actor or '-'} -> {log.to_actor}" for log in takeover_logs)
                if takeover_logs
                else "-"
            )

            sum_secs = int((t.closed_at - t.created_at).total_seconds()) if (t.closed_at and t.created_at) else 0
            doing = int(t.doing_secs or 0)
            hold = int(t.hold_secs or 0)
            waiting = max(0, sum_secs - doing - hold)

            ws.write(r, 0, t.id, center)
            ws.write(r, 1, nz(t.status), center)
            ws.write(r, 2, nz(fmt_th(t.created_at)), cell)
            ws.write(r, 3, nz(fmt_th(t.closed_at)), cell)
            ws.write(r, 4, nz(t.requester), cell)
            ws.write(r, 5, nz(t.machine), cell)
            ws.write(r, 6, nz(mtype), cell)
            ws.write(r, 7, nz(brand), cell)
            ws.write(r, 8, nz(t.machine_id), cell)
            ws.write(r, 9, nz(t.problem), cell)
            ws.write(r, 10, nz(t.description), wrap)
            ws.write(r, 11, hms(doing), center)
            ws.write(r, 12, hms(hold), center)
            ws.write(r, 13, nz(t.hold_reason), wrap)
            ws.write(r, 14, hms(waiting), center)
            ws.write(r, 15, hms(sum_secs), center)
            ws.write(r, 16, nz(t.solution), wrap)
            ws.write(r, 17, nz(t.cancel_reason), wrap)
            ws.write(r, 18, nz(takeover_text), wrap)
            ws.write(r, 19, nz(t.done_by or t.canceled_by), cell)
            r += 1

        widths = [6, 10, 18, 18, 12, 10, 16, 18, 14, 20, 36, 10, 10, 20, 14, 12, 20, 20, 34, 12]
        for i, w in enumerate(widths):
            ws.set_column(i, i, w)

        wb.close()
        buf.seek(0)

        filename = "history"
        if line_op:
            filename += f"_{line_op}"
        if machine_type_val:
            filename += f"_{machine_type_val}"
        if machine_brand_val:
            filename += f"_{machine_brand_val}"
        if machine_id_val:
            filename += f"_{machine_id_val}"
        if problem_val:
            filename += f"_{problem_val}"
        if start_date or end_date:
            filename += f"_{start_date or ''}-{end_date or ''}"
        filename += ".xlsx"

        return StreamingResponse(
            buf,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )
