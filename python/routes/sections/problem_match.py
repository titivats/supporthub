from typing import Dict, List, Optional

from fastapi import Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session


def register_problem_match_routes(app, templates, ctx):
    get_db = ctx["get_db"]
    MasterMachineType = ctx["MasterMachineType"]
    MasterProblem = ctx["MasterProblem"]
    ProblemClass = ctx["ProblemClass"]
    ProblemMatch = ctx["ProblemMatch"]
    _clean_text = ctx["_clean_text"]
    _build_master_data = ctx["_build_master_data"]
    _add_master_audit = ctx["_add_master_audit"]
    _require_admin_user = ctx["_require_admin_user"]
    _commit_master_change = ctx["_commit_master_change"]
    _ensure_master_machine = ctx["_ensure_master_machine"]
    _ensure_master_machine_type = ctx["_ensure_master_machine_type"]
    fmt_th = ctx["fmt_th"]

    STATUS_TEXT = {
        "class_added": "Created Class successfully.",
        "class_exists": "Class already exists.",
        "class_deleted": "Deleted Class successfully.",
        "class_not_found": "Class not found.",
        "class_in_use": "Cannot delete Class because it is used in mappings.",
        "mapping_saved": "Saved Problem Match successfully.",
        "mapping_deleted": "Deleted Problem Match successfully.",
        "mapping_not_found": "Problem Match not found.",
        "invalid_input": "Please provide all required fields.",
        "problem_added": "Added Problem successfully.",
        "problem_exists": "Problem already exists.",
    }

    def _status_text(status_key: str) -> str:
        return STATUS_TEXT.get(status_key or "", "")

    def _redirect_problem_match(status_key: str) -> RedirectResponse:
        return RedirectResponse(f"/admin/problem-match?status={status_key}", status_code=303)

    def _build_problem_options_by_machine(db: Session) -> Dict[str, List[str]]:
        out: Dict[str, List[str]] = {}
        seen: Dict[str, set] = {}
        rows = (
            db.query(MasterProblem.machine, MasterProblem.problem)
            .order_by(MasterProblem.machine.asc(), MasterProblem.problem.asc(), MasterProblem.id.asc())
            .all()
        )
        for machine_raw, problem_raw in rows:
            machine_val = _clean_text(machine_raw)
            problem_val = _clean_text(problem_raw)
            if not machine_val or not problem_val:
                continue
            out.setdefault(machine_val, [])
            seen.setdefault(machine_val.lower(), set())
            key = problem_val.lower()
            if key in seen[machine_val.lower()]:
                continue
            seen[machine_val.lower()].add(key)
            out[machine_val].append(problem_val)
        return out

    def _find_class_by_name(db: Session, class_name: str):
        class_key = _clean_text(class_name).lower()
        if not class_key:
            return None
        for row in db.query(ProblemClass).all():
            if _clean_text(row.class_name).lower() == class_key:
                return row
        return None

    @app.get("/admin/problem-match", response_class=HTMLResponse)
    def admin_problem_match(
        request: Request,
        filter_machine: Optional[str] = None,
        filter_problem: Optional[str] = None,
        filter_class: Optional[str] = None,
        status: str = "",
        db: Session = Depends(get_db),
    ):
        me = _require_admin_user(request, db)
        master = _build_master_data(db)

        problem_options_by_machine = _build_problem_options_by_machine(db)
        all_problem_options = sorted(
            {problem for values in problem_options_by_machine.values() for problem in values},
            key=lambda s: s.lower(),
        )
        class_rows = db.query(ProblemClass).order_by(ProblemClass.class_name.asc(), ProblemClass.id.asc()).all()
        match_rows = db.query(ProblemMatch).order_by(ProblemMatch.created_at.desc(), ProblemMatch.id.desc()).all()

        f_machine = _clean_text(filter_machine)
        f_problem = _clean_text(filter_problem)
        f_class = _clean_text(filter_class)

        filtered_rows = []
        for row in match_rows:
            machine_val = _clean_text(row.machine)
            problem_val = _clean_text(row.problem)
            class_val = _clean_text(row.class_name)
            if f_machine and machine_val.lower() != f_machine.lower():
                continue
            if f_problem and problem_val.lower() != f_problem.lower():
                continue
            if f_class and class_val.lower() != f_class.lower():
                continue
            filtered_rows.append(row)

        machine_type_map = master.get("machine_type_map", {})
        return templates.TemplateResponse(
            "problem_match.html",
            {
                "request": request,
                "me": me,
                "status_key": status or "",
                "status_text": _status_text(status),
                "machine_options": master.get("machine_list", []),
                "machine_type_map": machine_type_map,
                "problem_options_by_machine": problem_options_by_machine,
                "all_problem_options": all_problem_options,
                "class_rows": class_rows,
                "match_rows": filtered_rows,
                "filter_machine": f_machine,
                "filter_problem": f_problem,
                "filter_class": f_class,
                "fmt_th": fmt_th,
            },
        )

    @app.post("/admin/problem-match/create-class")
    def create_problem_class(
        request: Request,
        class_name: str = Form(...),
        db: Session = Depends(get_db),
    ):
        me = _require_admin_user(request, db)
        class_val = _clean_text(class_name)
        if not class_val:
            return _redirect_problem_match("invalid_input")

        if _find_class_by_name(db, class_val):
            return _redirect_problem_match("class_exists")

        db.add(ProblemClass(class_name=class_val))
        _add_master_audit(db, me.username, "ADD", "PROBLEM_CLASS", class_val)
        _commit_master_change(db)
        return _redirect_problem_match("class_added")

    @app.post("/admin/problem-match/delete-class")
    def delete_problem_class(
        request: Request,
        class_id: int = Form(...),
        db: Session = Depends(get_db),
    ):
        me = _require_admin_user(request, db)
        row = db.query(ProblemClass).filter(ProblemClass.id == class_id).first()
        if not row:
            return _redirect_problem_match("class_not_found")

        class_val = _clean_text(row.class_name)
        in_use = (
            db.query(ProblemMatch.id)
            .filter(ProblemMatch.class_name == class_val)
            .first()
        )
        if in_use:
            return _redirect_problem_match("class_in_use")

        db.delete(row)
        _add_master_audit(db, me.username, "DELETE", "PROBLEM_CLASS", class_val)
        _commit_master_change(db)
        return _redirect_problem_match("class_deleted")

    @app.post("/admin/problem-match/add-problem")
    def add_problem_in_problem_match(
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
            return _redirect_problem_match("invalid_input")

        _ensure_master_machine(db, me.username, machine_val, details="auto-created by problem match")
        if machine_type_val:
            _ensure_master_machine_type(
                db,
                me.username,
                machine_val,
                machine_type_val,
                details="auto-created by problem match",
            )

        q = (
            db.query(MasterProblem)
            .filter(
                MasterProblem.machine == machine_val,
                MasterProblem.problem == problem_val,
            )
        )
        if machine_type_val:
            q = q.filter(MasterProblem.machine_type == machine_type_val)
        else:
            q = q.filter(MasterProblem.machine_type.is_(None))

        if q.first():
            return _redirect_problem_match("problem_exists")

        db.add(MasterProblem(machine=machine_val, machine_type=machine_type_val, problem=problem_val))
        _add_master_audit(
            db,
            me.username,
            "ADD",
            "PROBLEM",
            f"{machine_val} || {machine_type_val or '-'} || {problem_val}",
            details="added from Problem Match",
        )
        _commit_master_change(db)
        return _redirect_problem_match("problem_added")

    @app.post("/admin/problem-match/save")
    def save_problem_match(
        request: Request,
        machine: str = Form(...),
        problem: str = Form(...),
        class_name: str = Form(...),
        db: Session = Depends(get_db),
    ):
        me = _require_admin_user(request, db)

        machine_val = _clean_text(machine)
        problem_val = _clean_text(problem)
        class_val = _clean_text(class_name)
        if not machine_val or not problem_val or not class_val:
            return _redirect_problem_match("invalid_input")

        class_row = _find_class_by_name(db, class_val)
        if not class_row:
            return _redirect_problem_match("class_not_found")
        class_val = _clean_text(class_row.class_name)

        problem_exists = (
            db.query(MasterProblem.id)
            .filter(
                MasterProblem.machine == machine_val,
                MasterProblem.problem == problem_val,
            )
            .first()
        )
        if not problem_exists:
            return _redirect_problem_match("invalid_input")

        existing = (
            db.query(ProblemMatch)
            .filter(
                ProblemMatch.machine == machine_val,
                ProblemMatch.problem == problem_val,
            )
            .first()
        )
        if existing:
            existing.class_name = class_val
            db.add(existing)
        else:
            db.add(ProblemMatch(machine=machine_val, problem=problem_val, class_name=class_val))

        _add_master_audit(
            db,
            me.username,
            "ADD",
            "PROBLEM_MATCH",
            f"{machine_val} || {problem_val} -> {class_val}",
        )
        _commit_master_change(db)
        return _redirect_problem_match("mapping_saved")

    @app.post("/admin/problem-match/delete")
    def delete_problem_match(
        request: Request,
        mapping_id: int = Form(...),
        db: Session = Depends(get_db),
    ):
        me = _require_admin_user(request, db)
        row = db.query(ProblemMatch).filter(ProblemMatch.id == mapping_id).first()
        if not row:
            return _redirect_problem_match("mapping_not_found")

        item_key = f"{_clean_text(row.machine)} || {_clean_text(row.problem)} -> {_clean_text(row.class_name)}"
        db.delete(row)
        _add_master_audit(db, me.username, "DELETE", "PROBLEM_MATCH", item_key)
        _commit_master_change(db)
        return _redirect_problem_match("mapping_deleted")
