from __future__ import annotations

from datetime import datetime
from typing import List
import io

from fastapi import Depends, Request
from fastapi.responses import HTMLResponse, StreamingResponse
from sqlalchemy.orm import Session


def register_admin_machine_page_routes(app, templates, ctx):
    get_db = ctx["get_db"]
    fmt_th = ctx["fmt_th"]
    _build_master_data = ctx["_build_master_data"]
    _master_status_text = ctx["_master_status_text"]
    _get_master_rows_sorted = ctx["_get_master_rows_sorted"]
    _flatten_line_machine_map = ctx["_flatten_line_machine_map"]
    _require_admin_user = ctx["_require_admin_user"]

    @app.get("/admin/machines", response_class=HTMLResponse)
    def admin_machines(request: Request, db: Session = Depends(get_db)):
        me = _require_admin_user(request, db)

        master = _build_master_data(db)
        status = request.query_params.get("status", "")
        rows = _get_master_rows_sorted(db, "desc")

        return templates.TemplateResponse(
            "add_machine.html",
            {
                "request": request,
                "me": me,
                "line_rows": rows["line_rows"],
                "machine_rows": rows["machine_rows"],
                "machine_type_rows": rows["machine_type_rows"],
                "machine_id_rows": rows["machine_id_rows"],
                "support_area_rows": rows["support_area_rows"],
                "support_area_map_rows": rows["support_area_map_rows"],
                "problem_rows": rows["problem_rows"],
                "audit_rows": rows["audit_rows"],
                "machine_options": master["machine_list"],
                "line_options": master["line_ops"],
                "support_area_options": master["support_areas"],
                "machine_type_map": master["machine_type_map"],
                "machine_id_map": master["machine_id_map"],
                "support_area_map": master["support_area_map"],
                "monitoring_item_options": master["monitoring_item_options"],
                "line_machine_map_rows": _flatten_line_machine_map(master["line_machine_map"]),
                "status_text": _master_status_text(status),
                "status_key": status,
                "fmt_th": fmt_th,
            },
        )

    @app.get("/admin/machines/export/excel")
    def admin_export_machines_excel(request: Request, db: Session = Depends(get_db)):
        _require_admin_user(request, db)

        import xlsxwriter

        master = _build_master_data(db)
        rows = _get_master_rows_sorted(db, "desc")
        line_rows = rows["line_rows"]
        machine_rows = rows["machine_rows"]
        machine_type_rows = rows["machine_type_rows"]
        machine_id_rows = rows["machine_id_rows"]
        support_area_rows = rows["support_area_rows"]
        support_area_map_rows = rows["support_area_map_rows"]
        line_machine_map_rows = _flatten_line_machine_map(master["line_machine_map"])
        problem_rows = rows["problem_rows"]
        audit_rows = rows["audit_rows"]

        buf = io.BytesIO()
        wb = xlsxwriter.Workbook(buf, {"in_memory": True})

        hdr = wb.add_format({"bold": True, "bg_color": "#EEF2FF", "border": 1})
        cell = wb.add_format({"border": 1})

        def make_sheet(name: str, headers: List[str], rows_data: List[List[str]], widths: List[int]):
            ws = wb.add_worksheet(name[:31])
            ws.freeze_panes(1, 0)
            ws.autofilter(0, 0, 0, len(headers) - 1)

            for c, h in enumerate(headers):
                ws.write(0, c, h, hdr)
            for r, row_data in enumerate(rows_data, start=1):
                for c, value in enumerate(row_data):
                    ws.write(r, c, value, cell)
            for c, w in enumerate(widths):
                ws.set_column(c, c, w)

        make_sheet(
            "Support Area",
            ["Support Area", "Created"],
            [[r.support_area or "-", fmt_th(r.created_at)] for r in support_area_rows],
            [26, 20],
        )
        make_sheet(
            "Support Area to Machine",
            ["Support Area", "Machine", "Created"],
            [[r.support_area or "-", r.machine or "-", fmt_th(r.created_at)] for r in support_area_map_rows],
            [26, 28, 20],
        )
        make_sheet(
            "Line to Monitoring Page",
            ["Line No.", "Machine Type", "Machine ID"],
            [[r["line_no"] or "-", r["monitoring_item"] or "-", r.get("machine_id") or "-"] for r in line_machine_map_rows],
            [24, 30, 24],
        )
        make_sheet(
            "Line No.",
            ["Line No.", "Created"],
            [[r.line_no or "-", fmt_th(r.created_at)] for r in line_rows],
            [24, 20],
        )
        make_sheet(
            "Machine",
            ["Machine", "Created"],
            [[r.machine or "-", fmt_th(r.created_at)] for r in machine_rows],
            [30, 20],
        )
        make_sheet(
            "Machine Type",
            ["Machine", "Machine Type", "Created"],
            [[r.machine or "-", r.machine_type or "-", fmt_th(r.created_at)] for r in machine_type_rows],
            [26, 30, 20],
        )
        make_sheet(
            "Machine ID",
            ["Machine", "Machine Type", "Machine ID", "Created"],
            [[r.machine or "-", r.machine_type or "-", r.machine_id or "-", fmt_th(r.created_at)] for r in machine_id_rows],
            [24, 26, 22, 20],
        )
        make_sheet(
            "Problem",
            ["Machine", "Machine Type", "Problem", "Created"],
            [[r.machine or "-", r.machine_type or "-", r.problem or "-", fmt_th(r.created_at)] for r in problem_rows],
            [24, 26, 36, 20],
        )
        make_sheet(
            "Update History",
            ["Created", "User", "Action", "Data Type", "Item", "Details"],
            [[fmt_th(r.created_at), r.actor or "-", r.action or "-", r.data_type or "-", r.item or "-", r.details or "-"] for r in audit_rows],
            [20, 16, 10, 16, 40, 42],
        )

        wb.close()
        buf.seek(0)

        filename = f'master_data_{datetime.utcnow().strftime("%Y%m%d_%H%M%S")}.xlsx'
        return StreamingResponse(
            buf,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": f"attachment; filename=\"{filename}\""},
        )

