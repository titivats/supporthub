from __future__ import annotations

from typing import Optional

from fastapi import Depends, Form, Request
from sqlalchemy.orm import Session


def register_admin_machine_mutation_routes(app, templates, ctx):
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
    _prune_line_machine_map = ctx["_prune_line_machine_map"]
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
            for mapped_line_no, mapped_items in (line_machine_map or {}).items():
                for mapped_item in mapped_items or []:
                    _, mapped_machine_id = _split_line_monitoring_item(mapped_item)
                    if mapped_machine_id and mapped_machine_id.lower() == target_machine_id:
                        return _redirect_admin_machines("line_machine_map_exists")

        items.append(item_val)
        line_machine_map[line_val] = sorted({v for v in items if v}, key=lambda s: s.lower())
        save_line_machine_map(db, line_machine_map)
        item_display = f"{item_type} ({machine_id})" if machine_id else item_type
        _add_master_audit(db, me.username, "ADD", "LINE_MACHINE_MAP", f"{line_val} -> {item_display}")
        _commit_master_change(db)
        return _redirect_admin_machines("line_machine_map_added")

    @app.post("/admin/machines/delete-line-machine")
    def admin_delete_line_machine(
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

        line_machine_map = get_line_machine_map(db)
        items = [_normalize_line_monitoring_item(v) for v in line_machine_map.get(line_val, [])]
        if not items:
            return _redirect_admin_machines("line_machine_map_not_found")

        kept = [v for v in items if v and v.lower() != item_val.lower()]
        if len(kept) == len(items):
            return _redirect_admin_machines("line_machine_map_not_found")

        if kept:
            line_machine_map[line_val] = kept
        else:
            line_machine_map.pop(line_val, None)
        save_line_machine_map(db, line_machine_map)
        item_type, machine_id = _split_line_monitoring_item(item_val)
        item_display = f"{item_type} ({machine_id})" if machine_id else item_type
        _add_master_audit(db, me.username, "DELETE", "LINE_MACHINE_MAP", f"{line_val} -> {item_display}")
        _commit_master_change(db)
        return _redirect_admin_machines("line_machine_map_deleted")

    @app.post("/admin/machines/delete-support-area-machine")
    def admin_delete_support_area_machine(request: Request, map_id: int = Form(...), db: Session = Depends(get_db)):
        me = _require_admin_user(request, db)

        row = db.query(MasterSupportAreaMap).filter(MasterSupportAreaMap.id == map_id).first()
        if not row:
            return _redirect_admin_machines("support_area_map_not_found")

        row_key = f"{_clean_text(row.support_area)} -> {_clean_text(row.machine)}"
        db.delete(row)
        _add_master_audit(db, me.username, "DELETE", "SUPPORT_AREA_MAP", row_key)
        _commit_master_change(db)
        return _redirect_admin_machines("support_area_map_deleted")

    @app.post("/admin/machines/delete-support-area")
    def admin_delete_support_area(request: Request, support_area_id: int = Form(...), db: Session = Depends(get_db)):
        me = _require_admin_user(request, db)

        row = db.query(MasterSupportArea).filter(MasterSupportArea.id == support_area_id).first()
        if not row:
            return _redirect_admin_machines("support_area_not_found")

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
        _commit_master_change(db)
        return _redirect_admin_machines("support_area_deleted")

    @app.post("/admin/machines/delete-line")
    def admin_delete_line(request: Request, line_id: int = Form(...), db: Session = Depends(get_db)):
        me = _require_admin_user(request, db)

        row = db.query(MasterLine).filter(MasterLine.id == line_id).first()
        if not row:
            return _redirect_admin_machines("line_not_found")

        line_val = _clean_text(row.line_no)
        line_machine_map = get_line_machine_map(db)
        had_line_mapping = line_val.upper() in line_machine_map
        if had_line_mapping:
            line_machine_map.pop(line_val.upper(), None)
            save_line_machine_map(db, line_machine_map)
        db.delete(row)
        _add_master_audit(
            db,
            me.username,
            "DELETE",
            "LINE",
            line_val or "-",
            details=f"cascade_line_machine_map={1 if had_line_mapping else 0}",
        )
        _commit_master_change(db)
        return _redirect_admin_machines("line_deleted")

    @app.post("/admin/machines/delete-machine")
    def admin_delete_machine(request: Request, machine_row_id: int = Form(...), db: Session = Depends(get_db)):
        me = _require_admin_user(request, db)

        row = db.query(MasterMachine).filter(MasterMachine.id == machine_row_id).first()
        if not row:
            return _redirect_admin_machines("machine_not_found")

        machine_val = _clean_text(row.machine)
        deleted_map = deleted_ids = deleted_types = deleted_probs = 0
        removed_line_machine_items = 0
        if machine_val:
            removed_keys = {machine_val.lower()}
            machine_type_rows = db.query(MasterMachineType.machine_type).filter(MasterMachineType.machine == machine_val).all()
            for type_row in machine_type_rows:
                type_val = _clean_text(type_row.machine_type)
                if type_val:
                    removed_keys.add(type_val.lower())
            machine_id_rows = db.query(MasterMachineId.machine_id).filter(MasterMachineId.machine == machine_val).all()
            for id_row in machine_id_rows:
                machine_id_val = _clean_text(id_row.machine_id)
                if machine_id_val:
                    removed_keys.add(machine_id_val.lower())

            deleted_map = db.query(MasterSupportAreaMap).filter(MasterSupportAreaMap.machine == machine_val).delete(synchronize_session=False)
            deleted_ids = db.query(MasterMachineId).filter(MasterMachineId.machine == machine_val).delete(synchronize_session=False)
            deleted_types = db.query(MasterMachineType).filter(MasterMachineType.machine == machine_val).delete(synchronize_session=False)
            deleted_probs = db.query(MasterProblem).filter(MasterProblem.machine == machine_val).delete(synchronize_session=False)
            removed_line_machine_items = _prune_line_machine_map(db, removed_keys)
        db.delete(row)
        _add_master_audit(
            db,
            me.username,
            "DELETE",
            "MACHINE",
            machine_val or "-",
            details=f"cascade_maps={deleted_map},cascade_machine_ids={deleted_ids},cascade_machine_types={deleted_types},cascade_problems={deleted_probs},cascade_line_machine_items={removed_line_machine_items}",
        )
        _commit_master_change(db)
        return _redirect_admin_machines("machine_deleted")

    @app.post("/admin/machines/delete-machine-type")
    def admin_delete_machine_type(request: Request, machine_type_id: int = Form(...), db: Session = Depends(get_db)):
        me = _require_admin_user(request, db)

        row = db.query(MasterMachineType).filter(MasterMachineType.id == machine_type_id).first()
        if not row:
            return _redirect_admin_machines("machine_type_not_found")

        machine_val = _clean_text(row.machine)
        machine_type_val = _clean_text(row.machine_type)
        deleted_ids = deleted_probs = 0
        removed_line_machine_items = 0
        if machine_val and machine_type_val:
            target_keys = {machine_type_val.lower()}
            machine_id_rows = db.query(MasterMachineId.machine_id).filter(
                MasterMachineId.machine == machine_val,
                MasterMachineId.machine_type == machine_type_val,
            ).all()
            for id_row in machine_id_rows:
                machine_id_val = _clean_text(id_row.machine_id)
                if machine_id_val:
                    target_keys.add(machine_id_val.lower())
            deleted_ids = db.query(MasterMachineId).filter(
                MasterMachineId.machine == machine_val,
                MasterMachineId.machine_type == machine_type_val,
            ).delete(synchronize_session=False)
            deleted_probs = db.query(MasterProblem).filter(
                MasterProblem.machine == machine_val,
                MasterProblem.machine_type == machine_type_val,
            ).delete(synchronize_session=False)
            removed_line_machine_items = _prune_line_machine_map(db, target_keys)
        db.delete(row)
        _add_master_audit(
            db,
            me.username,
            "DELETE",
            "MACHINE_TYPE",
            f"{machine_val} || {machine_type_val}",
            details=f"cascade_machine_ids={deleted_ids},cascade_problems={deleted_probs},cascade_line_machine_items={removed_line_machine_items}",
        )
        _commit_master_change(db)
        return _redirect_admin_machines("machine_type_deleted")

    @app.post("/admin/machines/delete-machine-id")
    def admin_delete_machine_id(request: Request, machine_id_row_id: int = Form(...), db: Session = Depends(get_db)):
        me = _require_admin_user(request, db)

        row = db.query(MasterMachineId).filter(MasterMachineId.id == machine_id_row_id).first()
        if not row:
            return _redirect_admin_machines("machine_id_not_found")

        machine_id_val = _clean_text(row.machine_id)
        removed_line_machine_items = _prune_line_machine_map(db, {machine_id_val})
        item_key = f"{_clean_text(row.machine)} || {_clean_text(row.machine_type)} || {machine_id_val}"
        db.delete(row)
        _add_master_audit(
            db,
            me.username,
            "DELETE",
            "MACHINE_ID",
            item_key,
            details=f"cascade_line_machine_items={removed_line_machine_items}",
        )
        _commit_master_change(db)
        return _redirect_admin_machines("machine_id_deleted")

    @app.post("/admin/machines/delete-problem")
    def admin_delete_problem(request: Request, problem_id: int = Form(...), db: Session = Depends(get_db)):
        me = _require_admin_user(request, db)

        row = db.query(MasterProblem).filter(MasterProblem.id == problem_id).first()
        if not row:
            return _redirect_admin_machines("problem_not_found")

        item_key = f"{_clean_text(row.machine)} || {_clean_text(row.machine_type)} || {_clean_text(row.problem)}"
        db.delete(row)
        _add_master_audit(db, me.username, "DELETE", "PROBLEM", item_key)
        _commit_master_change(db)
        return _redirect_admin_machines("problem_deleted")

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
