from __future__ import annotations

from typing import Optional

from fastapi import Depends, Form, Request
from sqlalchemy.orm import Session


def register_admin_machine_add_routes(app, templates, ctx):
    get_db = ctx["get_db"]
    MasterLine = ctx["MasterLine"]
    MasterMachine = ctx["MasterMachine"]
    MasterMachineType = ctx["MasterMachineType"]
    MasterMachineId = ctx["MasterMachineId"]
    MasterProblem = ctx["MasterProblem"]
    MasterSupportArea = ctx["MasterSupportArea"]
    MasterSupportAreaMap = ctx["MasterSupportAreaMap"]
    _clean_text = ctx["_clean_text"]
    get_line_machine_map = ctx["get_line_machine_map"]
    save_line_machine_map = ctx["save_line_machine_map"]
    _add_master_audit = ctx["_add_master_audit"]
    _normalize_line_monitoring_item = ctx["_normalize_line_monitoring_item"]
    _split_line_monitoring_item = ctx["_split_line_monitoring_item"]
    _require_admin_user = ctx["_require_admin_user"]
    _commit_master_change = ctx["_commit_master_change"]
    _ensure_master_machine = ctx["_ensure_master_machine"]
    _ensure_master_machine_type = ctx["_ensure_master_machine_type"]
    _redirect_admin_machines = ctx["_redirect_admin_machines"]

    @app.post("/admin/machines/add-support-area")
    def admin_add_support_area(request: Request, support_area: str = Form(...), db: Session = Depends(get_db)):
        me = _require_admin_user(request, db)

        area_val = _clean_text(support_area)
        if not area_val:
            return _redirect_admin_machines("invalid_input")

        exists = db.query(MasterSupportArea).filter(MasterSupportArea.support_area == area_val).first()
        if exists:
            return _redirect_admin_machines("support_area_exists")

        db.add(MasterSupportArea(support_area=area_val))
        _add_master_audit(db, me.username, "ADD", "SUPPORT_AREA", area_val)
        _commit_master_change(db)
        return _redirect_admin_machines("support_area_added")

    @app.post("/admin/machines/add-support-area-machine")
    def admin_add_support_area_machine(
        request: Request,
        support_area: str = Form(...),
        machine: str = Form(...),
        db: Session = Depends(get_db),
    ):
        me = _require_admin_user(request, db)

        area_val = _clean_text(support_area)
        machine_val = _clean_text(machine)
        if not area_val or not machine_val:
            return _redirect_admin_machines("invalid_input")

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
            return _redirect_admin_machines("support_area_map_exists")

        db.add(MasterSupportAreaMap(support_area=area_val, machine=machine_val))
        _add_master_audit(db, me.username, "ADD", "SUPPORT_AREA_MAP", f"{area_val} -> {machine_val}")
        _commit_master_change(db)
        return _redirect_admin_machines("support_area_map_added")

    @app.post("/admin/machines/add-line-machine")
    def admin_add_line_machine(
        request: Request,
        line_no: str = Form(...),
        monitoring_item: str = Form(...),
        db: Session = Depends(get_db),
    ):
        me = _require_admin_user(request, db)

        line_val = _clean_text(line_no).upper()
        item_val = _normalize_line_monitoring_item(monitoring_item)
        if not line_val or not item_val:
            return _redirect_admin_machines("invalid_input")

        line_exists = db.query(MasterLine).filter(MasterLine.line_no == line_val).first()
        if not line_exists:
            return _redirect_admin_machines("line_not_found")

        line_machine_map = get_line_machine_map(db)
        items = [_normalize_line_monitoring_item(v) for v in line_machine_map.get(line_val, [])]
        if any(v.lower() == item_val.lower() for v in items if v):
            return _redirect_admin_machines("line_machine_map_exists")

        item_type, machine_id = _split_line_monitoring_item(item_val)
        if machine_id:
            target_machine_id = machine_id.lower()
            for mapped_items in (line_machine_map or {}).values():
                for mapped_item in mapped_items or []:
                    _, mapped_machine_id = _split_line_monitoring_item(mapped_item)
                    if mapped_machine_id and mapped_machine_id.lower() == target_machine_id:
                        return _redirect_admin_machines("line_machine_map_exists")

        items.append(item_val)
        line_machine_map[line_val] = sorted({value for value in items if value}, key=lambda s: s.lower())
        save_line_machine_map(db, line_machine_map)
        item_display = f"{item_type} ({machine_id})" if machine_id else item_type
        _add_master_audit(db, me.username, "ADD", "LINE_MACHINE_MAP", f"{line_val} -> {item_display}")
        _commit_master_change(db)
        return _redirect_admin_machines("line_machine_map_added")

    @app.post("/admin/machines/add-line")
    def admin_add_line(request: Request, line_no: str = Form(...), db: Session = Depends(get_db)):
        me = _require_admin_user(request, db)

        val = _clean_text(line_no).upper()
        if not val:
            return _redirect_admin_machines("invalid_input")

        exists = db.query(MasterLine).filter(MasterLine.line_no == val).first()
        if exists:
            return _redirect_admin_machines("line_exists")

        db.add(MasterLine(line_no=val))
        _add_master_audit(db, me.username, "ADD", "LINE", val)
        _commit_master_change(db)
        return _redirect_admin_machines("line_added")

    @app.post("/admin/machines/add-machine")
    def admin_add_machine(request: Request, machine: str = Form(...), db: Session = Depends(get_db)):
        me = _require_admin_user(request, db)

        machine_val = _clean_text(machine)
        if not machine_val:
            return _redirect_admin_machines("invalid_input")

        exists = db.query(MasterMachine).filter(MasterMachine.machine == machine_val).first()
        if exists:
            return _redirect_admin_machines("machine_exists")

        db.add(MasterMachine(machine=machine_val))
        _add_master_audit(db, me.username, "ADD", "MACHINE", machine_val)
        _commit_master_change(db)
        return _redirect_admin_machines("machine_added")

    @app.post("/admin/machines/add-machine-type")
    def admin_add_machine_type(
        request: Request,
        machine: str = Form(...),
        machine_type: str = Form(...),
        db: Session = Depends(get_db),
    ):
        me = _require_admin_user(request, db)

        machine_val = _clean_text(machine)
        machine_type_val = _clean_text(machine_type)
        if not machine_val or not machine_type_val:
            return _redirect_admin_machines("invalid_input")

        _ensure_master_machine(db, me.username, machine_val, details="auto-created by machine type")

        exists = db.query(MasterMachineType).filter(
            MasterMachineType.machine == machine_val,
            MasterMachineType.machine_type == machine_type_val,
        ).first()
        if exists:
            return _redirect_admin_machines("machine_type_exists")

        db.add(MasterMachineType(machine=machine_val, machine_type=machine_type_val))
        _add_master_audit(db, me.username, "ADD", "MACHINE_TYPE", f"{machine_val} || {machine_type_val}")
        _commit_master_change(db)
        return _redirect_admin_machines("machine_type_added")

    @app.post("/admin/machines/add-machine-id")
    def admin_add_machine_id(
        request: Request,
        machine: str = Form(...),
        machine_type: str = Form(...),
        machine_id: str = Form(...),
        db: Session = Depends(get_db),
    ):
        me = _require_admin_user(request, db)

        machine_val = _clean_text(machine)
        machine_type_val = _clean_text(machine_type)
        machine_id_val = _clean_text(machine_id)
        if not machine_val or not machine_type_val or not machine_id_val:
            return _redirect_admin_machines("invalid_input")

        _ensure_master_machine(db, me.username, machine_val, details="auto-created by machine id")
        _ensure_master_machine_type(
            db,
            me.username,
            machine_val,
            machine_type_val,
            details="auto-created by machine id",
        )

        exists = db.query(MasterMachineId).filter(
            MasterMachineId.machine == machine_val,
            MasterMachineId.machine_type == machine_type_val,
            MasterMachineId.machine_id == machine_id_val,
        ).first()
        if exists:
            return _redirect_admin_machines("machine_id_exists")

        db.add(MasterMachineId(machine=machine_val, machine_type=machine_type_val, machine_id=machine_id_val))
        _add_master_audit(db, me.username, "ADD", "MACHINE_ID", f"{machine_val} || {machine_type_val} || {machine_id_val}")
        _commit_master_change(db)
        return _redirect_admin_machines("machine_id_added")

    @app.post("/admin/machines/add-problem")
    def admin_add_problem(
        request: Request,
        machine: str = Form(...),
        machine_type: Optional[str] = Form(None),
        problem: str = Form(...),
        db: Session = Depends(get_db),
    ):
        me = _require_admin_user(request, db)

        machine_val = _clean_text(machine)
        machine_type_val = _clean_text(machine_type) or None
        problem_val = _clean_text(problem)
        if not machine_val or not problem_val:
            return _redirect_admin_machines("invalid_input")

        _ensure_master_machine(db, me.username, machine_val, details="auto-created by problem")

        if machine_type_val:
            _ensure_master_machine_type(
                db,
                me.username,
                machine_val,
                machine_type_val,
                details="auto-created by problem",
            )

        q = db.query(MasterProblem).filter(
            MasterProblem.machine == machine_val,
            MasterProblem.problem == problem_val,
        )
        if machine_type_val:
            q = q.filter(MasterProblem.machine_type == machine_type_val)
        else:
            q = q.filter(MasterProblem.machine_type.is_(None))

        if q.first():
            return _redirect_admin_machines("problem_exists")

        db.add(MasterProblem(machine=machine_val, machine_type=machine_type_val, problem=problem_val))
        _add_master_audit(db, me.username, "ADD", "PROBLEM", f"{machine_val} || {machine_type_val or '-'} || {problem_val}")
        _commit_master_change(db)
        return _redirect_admin_machines("problem_added")
