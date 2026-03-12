from typing import Optional

from fastapi import Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session


def register_ticket_action_routes(app, templates, ctx):
    get_db = ctx["get_db"]
    User = ctx["User"]
    Ticket = ctx["Ticket"]
    TicketTakeoverLog = ctx["TicketTakeoverLog"]
    verify_password = ctx["verify_password"]
    fmt_th = ctx["fmt_th"]
    _clean_text = ctx["_clean_text"]
    _build_master_data = ctx["_build_master_data"]
    bump_active_version = ctx["bump_active_version"]
    EQUIPMENTS = ctx["EQUIPMENTS"]
    get_current_user = ctx["get_current_user"]

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
            "line_machine_map": master.get("line_machine_map", {}),
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
        equipment: Optional[str] = Form(None),  # Machine (type||brand) or brand only
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
        db.add(t)
        db.commit()
        bump_active_version()  # important: notify Active Tickets page to refresh quickly
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
            raise HTTPException(
                status_code=404,
                detail="\u0e44\u0e21\u0e48\u0e1e\u0e1a\u0e1c\u0e39\u0e49\u0e43\u0e0a\u0e49\u0e17\u0e35\u0e48\u0e23\u0e30\u0e1a\u0e38",
            )
        if not verify_password(password, actor.password_hash):
            raise HTTPException(
                status_code=403,
                detail="\u0e23\u0e2b\u0e31\u0e2a\u0e1c\u0e48\u0e32\u0e19\u0e44\u0e21\u0e48\u0e16\u0e39\u0e01\u0e15\u0e49\u0e2d\u0e07",
            )

        ticket = db.query(Ticket).filter(Ticket.id == ticket_id).first()
        if not ticket:
            raise HTTPException(status_code=404, detail="Ticket not found")

        act = action.lower().strip()

        if ticket.status in ("DOING", "HOLD") and act == "done":
            if ticket.current_actor and ticket.current_actor != actor.username:
                raise HTTPException(
                    status_code=409,
                    detail=f"Username does not match current actor ({ticket.current_actor})",
                )

        if act == "takeover":
            if ticket.status not in ("DOING", "HOLD"):
                raise HTTPException(status_code=409, detail="Takeover is allowed only in DOING or HOLD status")
            if ticket.current_actor and ticket.current_actor == actor.username:
                raise HTTPException(status_code=409, detail="You are already the current actor")

        if act == "done" and ticket.status == "PENDING":
            raise HTTPException(status_code=409, detail="Press Doing before Done")
        if act == "doing" and ticket.status == "DOING":
            raise HTTPException(status_code=409, detail="Cannot press Doing again while already DOING")
        if act == "hold" and ticket.status == "HOLD":
            raise HTTPException(status_code=409, detail="Cannot press Hold again while already HOLD")

        if act == "doing":
            ticket.start_doing()
            ticket.current_actor = actor.username
            ticket.last_action = "doing"
        elif act == "hold":
            if not (reason and reason.strip()):
                raise HTTPException(status_code=400, detail="Please provide Hold reason")
            ticket.start_hold(reason.strip())
            ticket.current_actor = actor.username
            ticket.last_action = "hold"
        elif act == "done":
            if not (solution and solution.strip()):
                raise HTTPException(status_code=400, detail="Please provide Solution before Done")
            ticket.done(solution.strip(), by=actor.username)
            ticket.current_actor = None
            ticket.last_action = "done"
        elif act == "cancel":
            if not (reason and reason.strip()):
                raise HTTPException(status_code=400, detail="Please provide Cancel reason")
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

        db.add(ticket)
        db.commit()
        bump_active_version()  # important: notify Active Tickets page to refresh quickly
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
