from datetime import datetime, time
from typing import Dict, List, Optional
import io

from fastapi import Depends, Form, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse, StreamingResponse
from sqlalchemy.orm import Session


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
    TH_OFFSET = deps["TH_OFFSET"]
    _fmt_hms = deps["_fmt_hms"]
    fmt_th = deps["fmt_th"]
    _clean_text = deps["_clean_text"]
    _is_admin_user = deps["_is_admin_user"]
    _build_master_data = deps["_build_master_data"]
    _master_status_text = deps["_master_status_text"]
    _add_master_audit = deps["_add_master_audit"]
    _get_master_rows_sorted = deps["_get_master_rows_sorted"]
    bump_active_version = deps["bump_active_version"]
    EQUIPMENTS = deps["EQUIPMENTS"]
    iot_monitor = deps["iot_monitor"]
    # ---------- Auth routes ----------
    @app.get("/login", response_class=HTMLResponse)
    def login_page(request: Request):
        created = request.query_params.get("created") == "1"
        return templates.TemplateResponse("login.html", {"request": request, "error": None, "created": created})
    
    @app.post("/login")
    def do_login(request: Request, username: str = Form(...), password: str = Form(...), db: Session = Depends(get_db)):
        user = db.query(User).filter(User.username == username.strip()).first()
        if not user or not verify_password(password, user.password_hash):
            return templates.TemplateResponse("login.html", {"request": request, "error": "à¸Šà¸·à¹ˆà¸­à¸œà¸¹à¹‰à¹ƒà¸Šà¹‰à¸«à¸£à¸·à¸­à¸£à¸«à¸±à¸ªà¸œà¹ˆà¸²à¸™à¹„à¸¡à¹ˆà¸–à¸¹à¸à¸•à¹‰à¸­à¸‡", "created": False}, status_code=400)
        token = make_session_token(user.username)
        resp = RedirectResponse("/", status_code=303)
        resp.set_cookie("session", token, httponly=True, samesite="lax", secure=SECURE_COOKIES, max_age=SESSION_AGE)
        return resp
    
    @app.get("/logout")
    def logout():
        resp = RedirectResponse("/login", status_code=303)
        resp.delete_cookie("session")
        return resp
    
    @app.get("/signup", response_class=HTMLResponse)
    def signup_page(request: Request):
        return templates.TemplateResponse("add_user.html", {"request": request, "error": None})
    
    @app.post("/signup")
    def do_signup(username: str = Form(...), password: str = Form(...), role: str = Form("Operator"), db: Session = Depends(get_db)):
        username = username.strip()
        if not username or not password:
            return templates.TemplateResponse("add_user.html", {"request": {}, "error": "à¸à¸£à¸­à¸à¸‚à¹‰à¸­à¸¡à¸¹à¸¥à¹ƒà¸«à¹‰à¸„à¸£à¸š"}, status_code=400)
        if db.query(User).filter(User.username == username).first():
            return templates.TemplateResponse("add_user.html", {"request": {}, "error": "Username à¸‹à¹‰à¸³"}, status_code=400)
        db.add(User(username=username, password_hash=sha256(password), role=role)); db.commit()
        return RedirectResponse("/login?created=1", status_code=303)
    
    # ---------- Admin: Users ----------
    @app.get("/admin/users", response_class=HTMLResponse)
    def admin_users(request: Request, db: Session = Depends(get_db)):
        user = get_current_user(request, db)
        if user.role.lower() != "admin" and user.username.upper() != "ADMIN":
            raise HTTPException(status_code=403, detail="Forbidden")
        users = db.query(User).order_by(User.username.asc()).all()
        users_sorted = sorted(users, key=lambda u: (u.username.upper() != "ADMIN", u.username.lower()))
        pw_updated = request.query_params.get("pw_updated") == "1"
        return templates.TemplateResponse("manage_users.html", {
            "request": request, "me": user, "users": users_sorted, "pw_updated": pw_updated, "fmt_th": fmt_th,
        })
    
    @app.post("/admin/users/create")
    def admin_create_user(request: Request,
                          username: str = Form(...),
                          password: str = Form(...),
                          role: str = Form(...),
                          db: Session = Depends(get_db)):
        me = get_current_user(request, db)
        if me.role.lower() != "admin" and me.username.upper() != "ADMIN":
            raise HTTPException(status_code=403, detail="Forbidden")
        username = username.strip()
        if not username or not password:
            raise HTTPException(status_code=400, detail="invalid params")
        if db.query(User).filter(User.username == username).first():
            raise HTTPException(status_code=400, detail="duplicated")
        u = User(username=username, password_hash=sha256(password), role=role)
        db.add(u); db.commit()
        return RedirectResponse("/admin/users", status_code=303)
    
    @app.post("/admin/users/update/{user_id}")
    def admin_update_user(user_id: int,
                          request: Request,
                          role: str = Form(...),
                          new_password: Optional[str] = Form(None),
                          db: Session = Depends(get_db)):
        me = get_current_user(request, db)
        if me.role.lower() != "admin" and me.username.upper() != "ADMIN":
            raise HTTPException(status_code=403, detail="Forbidden")
    
        u = db.query(User).filter(User.id == user_id).first()
        if not u: raise HTTPException(status_code=404, detail="not found")
        if u.username.upper() == "ADMIN" and (me.username.upper() != "ADMIN"):
            raise HTTPException(status_code=403, detail="Cannot edit ADMIN")
    
        u.role = role
        if new_password and new_password.strip():
            u.password_hash = sha256(new_password.strip())
            u.created_at = datetime.utcnow()
            db.add(u); db.commit()
            return RedirectResponse("/admin/users?pw_updated=1", status_code=303)
    
        db.add(u); db.commit()
        return RedirectResponse("/admin/users", status_code=303)
    
    @app.post("/admin/users/delete/{user_id}")
    def admin_delete_user(user_id: int, request: Request, db: Session = Depends(get_db)):
        me = get_current_user(request, db)
        if me.role.lower() != "admin" and me.username.upper() != "ADMIN":
            raise HTTPException(status_code=403, detail="Forbidden")
        u = db.query(User).filter(User.id == user_id).first()
        if not u: raise HTTPException(status_code=404, detail="not found")
        if u.username.upper() == "ADMIN":
            raise HTTPException(status_code=400, detail="ADMIN cannot be deleted")
        db.delete(u); db.commit()
        return RedirectResponse("/admin/users", status_code=303)
    
    @app.get("/admin/machines", response_class=HTMLResponse)
    def admin_machines(request: Request, db: Session = Depends(get_db)):
        me = get_current_user(request, db)
        if not _is_admin_user(me):
            raise HTTPException(status_code=403, detail="Forbidden")
    
        master = _build_master_data(db)
        status = request.query_params.get("status", "")
        rows = _get_master_rows_sorted(db, "desc")
    
        return templates.TemplateResponse("manage_machines.html", {
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
            "support_area_options": master["support_areas"],
            "machine_type_map": master["machine_type_map"],
            "machine_id_map": master["machine_id_map"],
            "support_area_map": master["support_area_map"],
            "status_text": _master_status_text(status),
            "status_key": status,
            "fmt_th": fmt_th,
        })
    
    @app.get("/admin/machines/export/excel")
    def admin_export_machines_excel(request: Request, db: Session = Depends(get_db)):
        me = get_current_user(request, db)
        if not _is_admin_user(me):
            raise HTTPException(status_code=403, detail="Forbidden")
    
        import xlsxwriter
    
        rows = _get_master_rows_sorted(db, "desc")
        line_rows = rows["line_rows"]
        machine_rows = rows["machine_rows"]
        machine_type_rows = rows["machine_type_rows"]
        machine_id_rows = rows["machine_id_rows"]
        support_area_rows = rows["support_area_rows"]
        support_area_map_rows = rows["support_area_map_rows"]
        problem_rows = rows["problem_rows"]
        audit_rows = rows["audit_rows"]
    
        buf = io.BytesIO()
        wb = xlsxwriter.Workbook(buf, {'in_memory': True})
    
        hdr = wb.add_format({'bold': True, 'bg_color': '#EEF2FF', 'border': 1})
        cell = wb.add_format({'border': 1})
    
        def make_sheet(name: str, headers: List[str], rows: List[List[str]], widths: List[int]):
            ws = wb.add_worksheet(name[:31])
            ws.freeze_panes(1, 0)
            ws.autofilter(0, 0, 0, len(headers) - 1)
    
            for c, h in enumerate(headers):
                ws.write(0, c, h, hdr)
            for r, row_data in enumerate(rows, start=1):
                for c, value in enumerate(row_data):
                    ws.write(r, c, value, cell)
            for c, w in enumerate(widths):
                ws.set_column(c, c, w)
    
        make_sheet(
            "Line No.",
            ["Line No.", "Created (TH)"],
            [[r.line_no or "-", fmt_th(r.created_at)] for r in line_rows],
            [24, 20],
        )
        make_sheet(
            "Machine",
            ["Machine", "Created (TH)"],
            [[r.machine or "-", fmt_th(r.created_at)] for r in machine_rows],
            [30, 20],
        )
        make_sheet(
            "Machine Type",
            ["Machine", "Machine Type", "Created (TH)"],
            [[r.machine or "-", r.machine_type or "-", fmt_th(r.created_at)] for r in machine_type_rows],
            [26, 30, 20],
        )
        make_sheet(
            "Machine ID",
            ["Machine", "Machine Type", "Machine ID", "Created (TH)"],
            [[r.machine or "-", r.machine_type or "-", r.machine_id or "-", fmt_th(r.created_at)] for r in machine_id_rows],
            [24, 26, 22, 20],
        )
        make_sheet(
            "Support Area",
            ["Support Area", "Created (TH)"],
            [[r.support_area or "-", fmt_th(r.created_at)] for r in support_area_rows],
            [26, 20],
        )
        make_sheet(
            "Support Area Map",
            ["Support Area", "Machine", "Created (TH)"],
            [[r.support_area or "-", r.machine or "-", fmt_th(r.created_at)] for r in support_area_map_rows],
            [26, 28, 20],
        )
        make_sheet(
            "Problem",
            ["Machine", "Machine Type", "Problem", "Created (TH)"],
            [[r.machine or "-", r.machine_type or "-", r.problem or "-", fmt_th(r.created_at)] for r in problem_rows],
            [24, 26, 36, 20],
        )
        make_sheet(
            "Audit Log",
            ["Created (TH)", "User", "Action", "Data Type", "Item", "Details"],
            [[fmt_th(r.created_at), r.actor or "-", r.action or "-", r.data_type or "-", r.item or "-", r.details or "-"] for r in audit_rows],
            [20, 16, 10, 16, 40, 42],
        )
    
        wb.close()
        buf.seek(0)
    
        filename = f'master_data_{datetime.utcnow().strftime("%Y%m%d_%H%M%S")}.xlsx'
        return StreamingResponse(
            buf,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )
    
    @app.post("/admin/machines/add-support-area")
    def admin_add_support_area(request: Request, support_area: str = Form(...), db: Session = Depends(get_db)):
        me = get_current_user(request, db)
        if not _is_admin_user(me):
            raise HTTPException(status_code=403, detail="Forbidden")
    
        area_val = _clean_text(support_area)
        if not area_val:
            return RedirectResponse("/admin/machines?status=invalid_input", status_code=303)
    
        exists = db.query(MasterSupportArea).filter(MasterSupportArea.support_area == area_val).first()
        if exists:
            return RedirectResponse("/admin/machines?status=support_area_exists", status_code=303)
    
        db.add(MasterSupportArea(support_area=area_val))
        _add_master_audit(db, me.username, "ADD", "SUPPORT_AREA", area_val)
        db.commit()
        bump_active_version()
        return RedirectResponse("/admin/machines?status=support_area_added", status_code=303)
    
    @app.post("/admin/machines/add-support-area-machine")
    def admin_add_support_area_machine(request: Request,
                                       support_area: str = Form(...),
                                       machine: str = Form(...),
                                       db: Session = Depends(get_db)):
        me = get_current_user(request, db)
        if not _is_admin_user(me):
            raise HTTPException(status_code=403, detail="Forbidden")
    
        area_val = _clean_text(support_area)
        machine_val = _clean_text(machine)
        if not area_val or not machine_val:
            return RedirectResponse("/admin/machines?status=invalid_input", status_code=303)
    
        area_exists = db.query(MasterSupportArea).filter(MasterSupportArea.support_area == area_val).first()
        if not area_exists:
            db.add(MasterSupportArea(support_area=area_val))
            _add_master_audit(db, me.username, "ADD", "SUPPORT_AREA", area_val, details="auto-created by support area mapping")
    
        machine_exists = db.query(MasterMachine).filter(MasterMachine.machine == machine_val).first()
        if not machine_exists:
            db.add(MasterMachine(machine=machine_val))
            _add_master_audit(db, me.username, "ADD", "MACHINE", machine_val, details="auto-created by support area mapping")
    
        exists = db.query(MasterSupportAreaMap).filter(
            MasterSupportAreaMap.support_area == area_val,
            MasterSupportAreaMap.machine == machine_val,
        ).first()
        if exists:
            return RedirectResponse("/admin/machines?status=support_area_map_exists", status_code=303)
    
        db.add(MasterSupportAreaMap(support_area=area_val, machine=machine_val))
        _add_master_audit(db, me.username, "ADD", "SUPPORT_AREA_MAP", f"{area_val} -> {machine_val}")
        db.commit()
        bump_active_version()
        return RedirectResponse("/admin/machines?status=support_area_map_added", status_code=303)
    
    @app.post("/admin/machines/delete-support-area-machine")
    def admin_delete_support_area_machine(request: Request, map_id: int = Form(...), db: Session = Depends(get_db)):
        me = get_current_user(request, db)
        if not _is_admin_user(me):
            raise HTTPException(status_code=403, detail="Forbidden")
    
        row = db.query(MasterSupportAreaMap).filter(MasterSupportAreaMap.id == map_id).first()
        if not row:
            return RedirectResponse("/admin/machines?status=support_area_map_not_found", status_code=303)
    
        row_key = f"{_clean_text(row.support_area)} -> {_clean_text(row.machine)}"
        db.delete(row)
        _add_master_audit(db, me.username, "DELETE", "SUPPORT_AREA_MAP", row_key)
        db.commit()
        bump_active_version()
        return RedirectResponse("/admin/machines?status=support_area_map_deleted", status_code=303)
    
    @app.post("/admin/machines/delete-support-area")
    def admin_delete_support_area(request: Request, support_area_id: int = Form(...), db: Session = Depends(get_db)):
        me = get_current_user(request, db)
        if not _is_admin_user(me):
            raise HTTPException(status_code=403, detail="Forbidden")
    
        row = db.query(MasterSupportArea).filter(MasterSupportArea.id == support_area_id).first()
        if not row:
            return RedirectResponse("/admin/machines?status=support_area_not_found", status_code=303)
    
        area_val = _clean_text(row.support_area)
        deleted_maps = 0
        if area_val:
            deleted_maps = db.query(MasterSupportAreaMap).filter(MasterSupportAreaMap.support_area == area_val).delete(synchronize_session=False)
        db.delete(row)
        _add_master_audit(
            db,
            me.username,
            "DELETE",
            "SUPPORT_AREA",
            area_val or "-",
            details=f"cascade_mappings={deleted_maps}",
        )
        db.commit()
        bump_active_version()
        return RedirectResponse("/admin/machines?status=support_area_deleted", status_code=303)
    
    @app.post("/admin/machines/delete-line")
    def admin_delete_line(request: Request, line_id: int = Form(...), db: Session = Depends(get_db)):
        me = get_current_user(request, db)
        if not _is_admin_user(me):
            raise HTTPException(status_code=403, detail="Forbidden")
    
        row = db.query(MasterLine).filter(MasterLine.id == line_id).first()
        if not row:
            return RedirectResponse("/admin/machines?status=line_not_found", status_code=303)
    
        line_val = _clean_text(row.line_no)
        db.delete(row)
        _add_master_audit(db, me.username, "DELETE", "LINE", line_val or "-")
        db.commit()
        bump_active_version()
        return RedirectResponse("/admin/machines?status=line_deleted", status_code=303)
    
    @app.post("/admin/machines/delete-machine")
    def admin_delete_machine(request: Request, machine_row_id: int = Form(...), db: Session = Depends(get_db)):
        me = get_current_user(request, db)
        if not _is_admin_user(me):
            raise HTTPException(status_code=403, detail="Forbidden")
    
        row = db.query(MasterMachine).filter(MasterMachine.id == machine_row_id).first()
        if not row:
            return RedirectResponse("/admin/machines?status=machine_not_found", status_code=303)
    
        machine_val = _clean_text(row.machine)
        deleted_map = deleted_ids = deleted_types = deleted_probs = 0
        if machine_val:
            deleted_map = db.query(MasterSupportAreaMap).filter(MasterSupportAreaMap.machine == machine_val).delete(synchronize_session=False)
            deleted_ids = db.query(MasterMachineId).filter(MasterMachineId.machine == machine_val).delete(synchronize_session=False)
            deleted_types = db.query(MasterMachineType).filter(MasterMachineType.machine == machine_val).delete(synchronize_session=False)
            deleted_probs = db.query(MasterProblem).filter(MasterProblem.machine == machine_val).delete(synchronize_session=False)
        db.delete(row)
        _add_master_audit(
            db,
            me.username,
            "DELETE",
            "MACHINE",
            machine_val or "-",
            details=f"cascade_maps={deleted_map},cascade_machine_ids={deleted_ids},cascade_machine_types={deleted_types},cascade_problems={deleted_probs}",
        )
        db.commit()
        bump_active_version()
        return RedirectResponse("/admin/machines?status=machine_deleted", status_code=303)
    
    @app.post("/admin/machines/delete-machine-type")
    def admin_delete_machine_type(request: Request, machine_type_id: int = Form(...), db: Session = Depends(get_db)):
        me = get_current_user(request, db)
        if not _is_admin_user(me):
            raise HTTPException(status_code=403, detail="Forbidden")
    
        row = db.query(MasterMachineType).filter(MasterMachineType.id == machine_type_id).first()
        if not row:
            return RedirectResponse("/admin/machines?status=machine_type_not_found", status_code=303)
    
        machine_val = _clean_text(row.machine)
        machine_type_val = _clean_text(row.machine_type)
        deleted_ids = deleted_probs = 0
        if machine_val and machine_type_val:
            deleted_ids = db.query(MasterMachineId).filter(
                MasterMachineId.machine == machine_val,
                MasterMachineId.machine_type == machine_type_val,
            ).delete(synchronize_session=False)
            deleted_probs = db.query(MasterProblem).filter(
                MasterProblem.machine == machine_val,
                MasterProblem.machine_type == machine_type_val,
            ).delete(synchronize_session=False)
        db.delete(row)
        _add_master_audit(
            db,
            me.username,
            "DELETE",
            "MACHINE_TYPE",
            f"{machine_val} || {machine_type_val}",
            details=f"cascade_machine_ids={deleted_ids},cascade_problems={deleted_probs}",
        )
        db.commit()
        bump_active_version()
        return RedirectResponse("/admin/machines?status=machine_type_deleted", status_code=303)
    
    @app.post("/admin/machines/delete-machine-id")
    def admin_delete_machine_id(request: Request, machine_id_row_id: int = Form(...), db: Session = Depends(get_db)):
        me = get_current_user(request, db)
        if not _is_admin_user(me):
            raise HTTPException(status_code=403, detail="Forbidden")
    
        row = db.query(MasterMachineId).filter(MasterMachineId.id == machine_id_row_id).first()
        if not row:
            return RedirectResponse("/admin/machines?status=machine_id_not_found", status_code=303)
    
        item_key = f"{_clean_text(row.machine)} || {_clean_text(row.machine_type)} || {_clean_text(row.machine_id)}"
        db.delete(row)
        _add_master_audit(db, me.username, "DELETE", "MACHINE_ID", item_key)
        db.commit()
        bump_active_version()
        return RedirectResponse("/admin/machines?status=machine_id_deleted", status_code=303)
    
    @app.post("/admin/machines/delete-problem")
    def admin_delete_problem(request: Request, problem_id: int = Form(...), db: Session = Depends(get_db)):
        me = get_current_user(request, db)
        if not _is_admin_user(me):
            raise HTTPException(status_code=403, detail="Forbidden")
    
        row = db.query(MasterProblem).filter(MasterProblem.id == problem_id).first()
        if not row:
            return RedirectResponse("/admin/machines?status=problem_not_found", status_code=303)
    
        item_key = f"{_clean_text(row.machine)} || {_clean_text(row.machine_type)} || {_clean_text(row.problem)}"
        db.delete(row)
        _add_master_audit(db, me.username, "DELETE", "PROBLEM", item_key)
        db.commit()
        bump_active_version()
        return RedirectResponse("/admin/machines?status=problem_deleted", status_code=303)
    
    @app.post("/admin/machines/add-line")
    def admin_add_line(request: Request, line_no: str = Form(...), db: Session = Depends(get_db)):
        me = get_current_user(request, db)
        if not _is_admin_user(me):
            raise HTTPException(status_code=403, detail="Forbidden")
    
        val = _clean_text(line_no).upper()
        if not val:
            return RedirectResponse("/admin/machines?status=invalid_input", status_code=303)
    
        exists = db.query(MasterLine).filter(MasterLine.line_no == val).first()
        if exists:
            return RedirectResponse("/admin/machines?status=line_exists", status_code=303)
    
        db.add(MasterLine(line_no=val))
        _add_master_audit(db, me.username, "ADD", "LINE", val)
        db.commit()
        bump_active_version()
        return RedirectResponse("/admin/machines?status=line_added", status_code=303)
    
    @app.post("/admin/machines/add-machine")
    def admin_add_machine(request: Request, machine: str = Form(...), db: Session = Depends(get_db)):
        me = get_current_user(request, db)
        if not _is_admin_user(me):
            raise HTTPException(status_code=403, detail="Forbidden")
    
        machine_val = _clean_text(machine)
        if not machine_val:
            return RedirectResponse("/admin/machines?status=invalid_input", status_code=303)
    
        exists = db.query(MasterMachine).filter(MasterMachine.machine == machine_val).first()
        if exists:
            return RedirectResponse("/admin/machines?status=machine_exists", status_code=303)
    
        db.add(MasterMachine(machine=machine_val))
        _add_master_audit(db, me.username, "ADD", "MACHINE", machine_val)
        db.commit()
        bump_active_version()
        return RedirectResponse("/admin/machines?status=machine_added", status_code=303)
    
    @app.post("/admin/machines/add-machine-type")
    def admin_add_machine_type(request: Request,
                               machine: str = Form(...),
                               machine_type: str = Form(...),
                               db: Session = Depends(get_db)):
        me = get_current_user(request, db)
        if not _is_admin_user(me):
            raise HTTPException(status_code=403, detail="Forbidden")
    
        machine_val = _clean_text(machine)
        machine_type_val = _clean_text(machine_type)
        if not machine_val or not machine_type_val:
            return RedirectResponse("/admin/machines?status=invalid_input", status_code=303)
    
        m_exists = db.query(MasterMachine).filter(MasterMachine.machine == machine_val).first()
        if not m_exists:
            db.add(MasterMachine(machine=machine_val))
            _add_master_audit(db, me.username, "ADD", "MACHINE", machine_val, details="auto-created by machine type")
    
        exists = db.query(MasterMachineType).filter(
            MasterMachineType.machine == machine_val,
            MasterMachineType.machine_type == machine_type_val,
        ).first()
        if exists:
            return RedirectResponse("/admin/machines?status=machine_type_exists", status_code=303)
    
        db.add(MasterMachineType(machine=machine_val, machine_type=machine_type_val))
        _add_master_audit(db, me.username, "ADD", "MACHINE_TYPE", f"{machine_val} || {machine_type_val}")
        db.commit()
        bump_active_version()
        return RedirectResponse("/admin/machines?status=machine_type_added", status_code=303)
    
    @app.post("/admin/machines/add-machine-id")
    def admin_add_machine_id(request: Request,
                             machine: str = Form(...),
                             machine_type: str = Form(...),
                             machine_id: str = Form(...),
                             db: Session = Depends(get_db)):
        me = get_current_user(request, db)
        if not _is_admin_user(me):
            raise HTTPException(status_code=403, detail="Forbidden")
    
        machine_val = _clean_text(machine)
        machine_type_val = _clean_text(machine_type)
        machine_id_val = _clean_text(machine_id)
        if not machine_val or not machine_type_val or not machine_id_val:
            return RedirectResponse("/admin/machines?status=invalid_input", status_code=303)
    
        m_exists = db.query(MasterMachine).filter(MasterMachine.machine == machine_val).first()
        if not m_exists:
            db.add(MasterMachine(machine=machine_val))
            _add_master_audit(db, me.username, "ADD", "MACHINE", machine_val, details="auto-created by machine id")
    
        mt_exists = db.query(MasterMachineType).filter(
            MasterMachineType.machine == machine_val,
            MasterMachineType.machine_type == machine_type_val,
        ).first()
        if not mt_exists:
            db.add(MasterMachineType(machine=machine_val, machine_type=machine_type_val))
            _add_master_audit(db, me.username, "ADD", "MACHINE_TYPE", f"{machine_val} || {machine_type_val}", details="auto-created by machine id")
    
        exists = db.query(MasterMachineId).filter(
            MasterMachineId.machine == machine_val,
            MasterMachineId.machine_type == machine_type_val,
            MasterMachineId.machine_id == machine_id_val,
        ).first()
        if exists:
            return RedirectResponse("/admin/machines?status=machine_id_exists", status_code=303)
    
        db.add(MasterMachineId(machine=machine_val, machine_type=machine_type_val, machine_id=machine_id_val))
        _add_master_audit(db, me.username, "ADD", "MACHINE_ID", f"{machine_val} || {machine_type_val} || {machine_id_val}")
        db.commit()
        bump_active_version()
        return RedirectResponse("/admin/machines?status=machine_id_added", status_code=303)
    
    @app.post("/admin/machines/add-problem")
    def admin_add_problem(request: Request,
                          machine: str = Form(...),
                          machine_type: Optional[str] = Form(None),
                          problem: str = Form(...),
                          db: Session = Depends(get_db)):
        me = get_current_user(request, db)
        if not _is_admin_user(me):
            raise HTTPException(status_code=403, detail="Forbidden")
    
        machine_val = _clean_text(machine)
        machine_type_val = _clean_text(machine_type) or None
        problem_val = _clean_text(problem)
        if not machine_val or not problem_val:
            return RedirectResponse("/admin/machines?status=invalid_input", status_code=303)
    
        m_exists = db.query(MasterMachine).filter(MasterMachine.machine == machine_val).first()
        if not m_exists:
            db.add(MasterMachine(machine=machine_val))
            _add_master_audit(db, me.username, "ADD", "MACHINE", machine_val, details="auto-created by problem")
    
        if machine_type_val:
            mt_exists = db.query(MasterMachineType).filter(
                MasterMachineType.machine == machine_val,
                MasterMachineType.machine_type == machine_type_val,
            ).first()
            if not mt_exists:
                db.add(MasterMachineType(machine=machine_val, machine_type=machine_type_val))
                _add_master_audit(db, me.username, "ADD", "MACHINE_TYPE", f"{machine_val} || {machine_type_val}", details="auto-created by problem")
    
        q = db.query(MasterProblem).filter(
            MasterProblem.machine == machine_val,
            MasterProblem.problem == problem_val,
        )
        if machine_type_val:
            q = q.filter(MasterProblem.machine_type == machine_type_val)
        else:
            q = q.filter(MasterProblem.machine_type.is_(None))
    
        if q.first():
            return RedirectResponse("/admin/machines?status=problem_exists", status_code=303)
    
        db.add(MasterProblem(machine=machine_val, machine_type=machine_type_val, problem=problem_val))
        _add_master_audit(db, me.username, "ADD", "PROBLEM", f"{machine_val} || {machine_type_val or '-'} || {problem_val}")
        db.commit()
        bump_active_version()
        return RedirectResponse("/admin/machines?status=problem_added", status_code=303)
    
    # ---------- Current user ----------
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
    
    # ---------- Main / Request / Action ----------
    @app.get("/", response_class=HTMLResponse)
    def index(request: Request, db: Session = Depends(get_db)):
        try:
            user = get_current_user(request, db)
        except HTTPException:
            return RedirectResponse("/login", status_code=302)
    
        master = _build_master_data(db)
    
        tickets = (
            db.query(Ticket)
              .filter(Ticket.status != "DONE", Ticket.status != "CANCELLED")
              .order_by(Ticket.id.desc())
              .all()
        )
        return templates.TemplateResponse("index.html", {
            "request": request,
            "user": user,
            "line_ops": master["line_ops"],
            "equipments": EQUIPMENTS,
            "machine_type_map": master["machine_type_map"],
            "machine_id_map": master["machine_id_map"],
            "support_areas": master["support_areas"],
            "support_area_map": master["support_area_map"],
            "problem_map": master["problem_map"],
            "problem_combo_map": master["problem_combo_map"],
            "tickets": tickets,
            "fmt_th": fmt_th,
        })
    
    @app.post("/request/create")
    def create_request(
        request: Request,
        machine: str = Form(...),               # Line No.
        equipment: Optional[str] = Form(None),  # Machine (type||brand) à¸«à¸£à¸·à¸­ brand à¹€à¸”à¸µà¹ˆà¸¢à¸§
        machine_id: Optional[str] = Form(None),
        problem: Optional[str] = Form(None),
        description: Optional[str] = Form(None),
        db: Session = Depends(get_db),
    ):
        user = get_current_user(request, db)
        t = Ticket(
            requester=user.username,
            machine=machine.strip(),
            equipment=(equipment or "").strip() or None,
            machine_id=(machine_id or "").strip() or None,
            problem=(problem or "").strip() or None,
            description=(description or "").strip() or None,
        )
        db.add(t); db.commit()
        bump_active_version()  # <<<<<< à¸ªà¸³à¸„à¸±à¸: à¸à¸£à¸°à¸•à¸¸à¹‰à¸™à¹ƒà¸«à¹‰à¸«à¸™à¹‰à¸² Active à¸£à¸µà¹‚à¸«à¸¥à¸”
        line_notify(f"[REQUEST] {t.machine} | {t.equipment or '-'} | {t.machine_id or '-'} | {t.problem or '-'} by {t.requester}")
        return RedirectResponse("/", status_code=303)
    
    @app.post("/tickets/{ticket_id}/action")
    def ticket_action(
        ticket_id: int,
        action: str = Form(...),                 # doing|hold|done|cancel|takeover
        password: str = Form(...),
        who: Optional[str] = Form(None),
        reason: Optional[str] = Form(None),      # hold/cancel
        solution: Optional[str] = Form(None),    # done
        request: Request = None,
        db: Session = Depends(get_db),
    ):
        session_user = get_current_user(request, db)
        actor_username = (who or session_user.username).strip()
    
        actor = db.query(User).filter(User.username == actor_username).first()
        if not actor:
            raise HTTPException(status_code=404, detail="à¹„à¸¡à¹ˆà¸žà¸šà¸œà¸¹à¹‰à¹ƒà¸Šà¹‰à¸—à¸µà¹ˆà¸£à¸°à¸šà¸¸")
        if not verify_password(password, actor.password_hash):
            raise HTTPException(status_code=403, detail="à¸£à¸«à¸±à¸ªà¸œà¹ˆà¸²à¸™à¹„à¸¡à¹ˆà¸–à¸¹à¸à¸•à¹‰à¸­à¸‡")
    
        ticket = db.query(Ticket).filter(Ticket.id == ticket_id).first()
        if not ticket:
            raise HTTPException(status_code=404, detail="Ticket not found")
    
        act = action.lower().strip()
    
        if ticket.status in ("DOING", "HOLD") and act == "done":
            if ticket.current_actor and ticket.current_actor != actor.username:
                raise HTTPException(status_code=409, detail=f"Username à¹„à¸¡à¹ˆà¸•à¸£à¸‡à¸à¸±à¸šà¸„à¸™à¸›à¸à¸´à¸šà¸±à¸•à¸´à¸‡à¸²à¸™à¸­à¸¢à¸¹à¹ˆ ({ticket.current_actor})")
    
        if act == "takeover":
            if ticket.status not in ("DOING", "HOLD"):
                raise HTTPException(status_code=409, detail="Takeover à¹„à¸”à¹‰à¹€à¸‰à¸žà¸²à¸°à¸ªà¸–à¸²à¸™à¸° DOING à¸«à¸£à¸·à¸­ HOLD")
            if ticket.current_actor and ticket.current_actor == actor.username:
                raise HTTPException(status_code=409, detail="à¸„à¸¸à¸“à¹€à¸›à¹‡à¸™à¸œà¸¹à¹‰à¸›à¸à¸´à¸šà¸±à¸•à¸´à¸‡à¸²à¸™à¸„à¸™à¸›à¸±à¸ˆà¸ˆà¸¸à¸šà¸±à¸™à¸­à¸¢à¸¹à¹ˆà¹à¸¥à¹‰à¸§")
    
        if act == "done" and ticket.status == "PENDING":
            raise HTTPException(status_code=409, detail="à¸•à¹‰à¸­à¸‡à¸à¸” Doing à¸à¹ˆà¸­à¸™ Done")
        if act == "doing" and ticket.status == "DOING":
            raise HTTPException(status_code=409, detail="à¹„à¸¡à¹ˆà¸ªà¸²à¸¡à¸²à¸£à¸–à¸à¸” Doing à¸‹à¹‰à¸³à¹€à¸žà¸·à¹ˆà¸­à¹€à¸£à¸´à¹ˆà¸¡à¸™à¸±à¸šà¹€à¸§à¸¥à¸²à¹ƒà¸«à¸¡à¹ˆà¹„à¸”à¹‰")
        if act == "hold" and ticket.status == "HOLD":
            raise HTTPException(status_code=409, detail="à¹„à¸¡à¹ˆà¸ªà¸²à¸¡à¸²à¸£à¸–à¸à¸” Hold à¸‹à¹‰à¸³à¹€à¸žà¸·à¹ˆà¸­à¹€à¸£à¸´à¹ˆà¸¡à¸™à¸±à¸šà¹€à¸§à¸¥à¸²à¹ƒà¸«à¸¡à¹ˆà¹„à¸”à¹‰")
    
        if act == "doing":
            ticket.start_doing()
            ticket.current_actor = actor.username
            ticket.last_action = "doing"
        elif act == "hold":
            if not (reason and reason.strip()):
                raise HTTPException(status_code=400, detail="à¸à¸£à¸­à¸à¹€à¸«à¸•à¸¸à¸œà¸¥ Hold")
            ticket.start_hold(reason.strip())
            ticket.current_actor = actor.username
            ticket.last_action = "hold"
        elif act == "done":
            if not (solution and solution.strip()):
                raise HTTPException(status_code=400, detail="à¸à¸£à¸­à¸ Solution à¸à¹ˆà¸­à¸™ Done")
            ticket.done(solution.strip(), by=actor.username)
            ticket.current_actor = None
            ticket.last_action = "done"
        elif act == "cancel":
            if not (reason and reason.strip()):
                raise HTTPException(status_code=400, detail="à¸à¸£à¸­à¸à¹€à¸«à¸•à¸¸à¸œà¸¥ Cancel")
            ticket.cancel(reason.strip(), by=actor.username)
            ticket.current_actor = None
            ticket.last_action = "cancel"
        elif act == "takeover":
            prev_actor = _clean_text(ticket.current_actor) or None
            db.add(TicketTakeoverLog(
                ticket_id=ticket.id,
                from_actor=prev_actor,
                to_actor=actor.username,
                status=ticket.status,
            ))
            ticket.current_actor = actor.username
            ticket.last_action = "takeover"
        else:
            raise HTTPException(status_code=400, detail="invalid action")
    
        db.add(ticket); db.commit()
        bump_active_version()  # <<<<<< à¸ªà¸³à¸„à¸±à¸: à¸à¸£à¸°à¸•à¸¸à¹‰à¸™à¹ƒà¸«à¹‰à¸«à¸™à¹‰à¸² Active à¸£à¸µà¹‚à¸«à¸¥à¸”
        return {
            "ok": True,
            "id": ticket.id,
            "status": ticket.status,
            "doing_secs": ticket.doing_secs,
            "hold_secs": ticket.hold_secs,
            "current_actor": ticket.current_actor,
            "last_action": ticket.last_action,
            "solution": ticket.solution,
            "done_by": ticket.done_by,
            "cancel_reason": ticket.cancel_reason,
            "canceled_by": ticket.canceled_by,
            "doing_started_at": ticket.doing_started_at.isoformat() if ticket.doing_started_at else None,
            "hold_started_at": ticket.hold_started_at.isoformat() if ticket.hold_started_at else None,
        }
    
    # ---------- History + Export ----------
    def _query_done_or_cancel(db: Session,
                              line_op: Optional[str] = None,
                              equipment: Optional[str] = None,
                              start_utc: Optional[datetime] = None,
                              end_utc: Optional[datetime] = None) -> List[Ticket]:
        q = db.query(Ticket).filter(Ticket.status.in_(["DONE","CANCELLED"]))
        if line_op: q = q.filter(Ticket.machine == line_op)
        if equipment: q = q.filter(Ticket.equipment == equipment)
        if start_utc: q = q.filter(Ticket.created_at >= start_utc)
        if end_utc: q = q.filter(Ticket.created_at <= end_utc)
        return q.order_by(Ticket.closed_at.desc().nullslast()).all()
    
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
    
    def _build_takeover_logs_map(db: Session, ticket_ids: List[int]) -> Dict[int, List[TicketTakeoverLog]]:
        out: Dict[int, List[TicketTakeoverLog]] = {}
        ids = [int(i) for i in ticket_ids if i]
        if not ids:
            return out
    
        rows = (
            db.query(TicketTakeoverLog)
            .filter(TicketTakeoverLog.ticket_id.in_(ids))
            .order_by(TicketTakeoverLog.ticket_id.asc(), TicketTakeoverLog.created_at.asc(), TicketTakeoverLog.id.asc())
            .all()
        )
        for row in rows:
            out.setdefault(row.ticket_id, []).append(row)
        return out
    
    @app.get("/history", response_class=HTMLResponse)
    def history(request: Request,
                line_op: Optional[str] = Query(None),
                machine_type: Optional[str] = Query(None),
                machine_brand: Optional[str] = Query(None),
                equipment: Optional[str] = Query(None),  # backward-compatible query param
                start_date: Optional[str] = Query(None),
                end_date: Optional[str] = Query(None),
                db: Session = Depends(get_db)):
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
    
        rows = _query_done_or_cancel(db, line_op, None, start_utc, end_utc)
        rows = _apply_history_machine_filters(rows, machine_type_val, machine_brand_val, master["machine_type_map"])
        takeover_logs_map = _build_takeover_logs_map(db, [t.id for t in rows])
        total_doing = sum((t.doing_secs or 0) for t in rows)
        total_hold  = sum((t.hold_secs  or 0) for t in rows)
        summary = {"doing": _fmt_hms(total_doing), "hold": _fmt_hms(total_hold)}
    
        return templates.TemplateResponse("history.html", {
            "request": request,
            "user": user,
            "rows": rows,
            "summary": summary,
            "line_ops": master["line_ops"],
            "machine_type_map": master["machine_type_map"],
            "line_op": line_op or "",
            "machine_type": machine_type_val,
            "machine_brand": machine_brand_val,
            "takeover_logs_map": takeover_logs_map,
            "start_date": start_date or "",
            "end_date": end_date or "",
            "fmt_th": fmt_th,
        })
    
    @app.get("/export/excel")
    def export_excel(request: Request,
                     line_op: Optional[str] = Query(None),
                     machine_type: Optional[str] = Query(None),
                     machine_brand: Optional[str] = Query(None),
                     equipment: Optional[str] = Query(None),  # backward-compatible query param
                     start_date: Optional[str] = Query(None),
                     end_date: Optional[str] = Query(None),
                     db: Session = Depends(get_db)):
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
        master = _build_master_data(db)
        rows = _query_done_or_cancel(db, line_op, None, start_utc, end_utc)
        rows = _apply_history_machine_filters(rows, machine_type_val, machine_brand_val, master["machine_type_map"])
        takeover_logs_map = _build_takeover_logs_map(db, [t.id for t in rows])
        type_by_key, brand_to_type = _build_history_type_lookup(master["machine_type_map"])
    
        buf = io.BytesIO()
        wb = xlsxwriter.Workbook(buf, {'in_memory': True})
        ws = wb.add_worksheet('History (TH)')
    
        ws.freeze_panes(1, 0)
        ws.autofilter(0, 0, 0, 19)
        ws.set_landscape()
        ws.fit_to_pages(1, 0)
    
        hdr   = wb.add_format({'bold': True, 'bg_color': '#EEF2FF', 'border': 1})
        cell  = wb.add_format({'border': 1})
        center= wb.add_format({'border': 1, 'align': 'center'})
        wrap  = wb.add_format({'border': 1, 'text_wrap': True})
    
        headers = [
            "ID", "Status", "Created (TH)", "Closed (TH)",
            "Request by", "Line No.", "Machine", "Machine Type",
            "Machine ID", "Problem", "Description", "Doing", "Hold",
            "Hold Reason", "Waiting Time", "Downtime",
            "Solution", "Cancel Reason", "Takeover Log", "Done By",
        ]
        for c, h in enumerate(headers):
            ws.write(0, c, h, hdr)
    
        def hms(sec: int) -> str:
            s = int(sec or 0); h, m, ss = s // 3600, (s % 3600) // 60, s % 60
            return f"{h:02d}:{m:02d}:{ss:02d}"
    
        def nz(v: Optional[str]) -> str:
            v = (v or "").strip()
            return v if v else "-"
    
        r = 1
        for t in rows:
            mtype, brand = _parse_ticket_machine_and_brand(t.equipment, type_by_key, brand_to_type)
            takeover_logs = takeover_logs_map.get(t.id, [])
            takeover_text = "\n".join(
                f"{fmt_th(log.created_at)} | {log.from_actor or '-'} -> {log.to_actor}"
                for log in takeover_logs
            ) if takeover_logs else "-"
    
            sum_secs = int((t.closed_at - t.created_at).total_seconds()) if (t.closed_at and t.created_at) else 0
            doing = int(t.doing_secs or 0)
            hold  = int(t.hold_secs or 0)
            waiting = max(0, sum_secs - doing - hold)
    
            ws.write(r,  0, t.id, center)
            ws.write(r,  1, nz(t.status), center)
            ws.write(r,  2, nz(fmt_th(t.created_at)), cell)
            ws.write(r,  3, nz(fmt_th(t.closed_at)), cell)
            ws.write(r,  4, nz(t.requester), cell)
            ws.write(r,  5, nz(t.machine), cell)
            ws.write(r,  6, nz(mtype), cell)
            ws.write(r,  7, nz(brand), cell)
            ws.write(r,  8, nz(t.machine_id), cell)
            ws.write(r,  9, nz(t.problem), cell)
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
    
        wb.close(); buf.seek(0)
    
        filename = "history"
        if line_op: filename += f"_{line_op}"
        if machine_type_val: filename += f"_{machine_type_val}"
        if machine_brand_val: filename += f"_{machine_brand_val}"
        if start_date or end_date: filename += f"_{start_date or ''}-{end_date or ''}"
        filename += ".xlsx"
    
        return StreamingResponse(
            buf,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'}
        )
    
    
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
        db: Session = Depends(get_db),
    ):
        try:
            user = get_current_user(request, db)
        except HTTPException:
            return RedirectResponse("/login", status_code=302)
    
        master = _build_master_data(db)
        machine_type_val, machine_brand_val = _normalize_history_filters(machine_type, machine_brand, equipment)
        applied = (apply or "").strip() == "1"
    
        rows: List[Ticket] = []
        metrics = None
        filtered_count = 0
    
        start_utc = end_utc = None
        try:
            start_utc, end_utc = parse_th_date_range(start_date, end_date)
        except Exception:
            start_utc = end_utc = None
    
        if applied:
            rows = _query_done_or_cancel(db, line_op, None, start_utc, end_utc)
            rows = _apply_history_machine_filters(rows, machine_type_val, machine_brand_val, master["machine_type_map"])
            filtered_count = len(rows)
            metrics = build_monitoring_metrics(rows, start_utc, end_utc)
    
        return templates.TemplateResponse("OEE/monitoring.html", {
            "request": request,
            "user": user,
            "line_ops": master["line_ops"],
            "machine_type_map": master["machine_type_map"],
            "line_op": line_op or "",
            "machine_type": machine_type_val,
            "machine_brand": machine_brand_val,
            "start_date": start_date or "",
            "end_date": end_date or "",
            "applied": applied,
            "metrics": metrics,
            "filtered_count": filtered_count,
        })
    
    
    @app.get("/iot-monitor", response_class=HTMLResponse)
    def iot_monitor_page(request: Request, db: Session = Depends(get_db)):
        try:
            user = get_current_user(request, db)
        except HTTPException:
            return RedirectResponse("/login", status_code=302)
        return templates.TemplateResponse("IoT/iot_monitor.html", {
            "request": request,
            "user": user,
        })
    
    
    @app.get("/api/iot-monitor/status")
    def api_iot_monitor_status(request: Request, db: Session = Depends(get_db)):
        _ = get_current_user(request, db)
        return iot_monitor.snapshot()
