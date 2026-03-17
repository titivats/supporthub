from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session


def query_done_or_cancel(
    db: Session,
    Ticket: Any,
    line_op: Optional[str] = None,
    equipment: Optional[str] = None,
    start_utc: Optional[datetime] = None,
    end_utc: Optional[datetime] = None,
) -> List[Any]:
    q = db.query(Ticket).filter(Ticket.status.in_(["DONE", "CANCELLED"]))
    if line_op:
        q = q.filter(Ticket.machine == line_op)
    if equipment:
        q = q.filter(Ticket.equipment == equipment)
    if start_utc:
        q = q.filter(Ticket.created_at >= start_utc)
    if end_utc:
        q = q.filter(Ticket.created_at <= end_utc)
    return q.order_by(Ticket.closed_at.desc().nullslast()).all()


def build_takeover_logs_map(db: Session, TicketTakeoverLog: Any, ticket_ids: List[int]) -> Dict[int, List[Any]]:
    out: Dict[int, List[Any]] = {}
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
