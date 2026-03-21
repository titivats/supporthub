from datetime import datetime, time
from typing import Dict, List, Optional, Tuple

from python.time_utils import TH_OFFSET, fmt_hms as _fmt_hms, fmt_th

PLANNED_PRODUCTION_HOURS_PER_DAY = 21.5
PLANNED_PRODUCTION_SECS_PER_DAY = int(PLANNED_PRODUCTION_HOURS_PER_DAY * 3600)


def parse_th_date_range(start_date: Optional[str], end_date: Optional[str]) -> tuple[Optional[datetime], Optional[datetime]]:
    start_utc = None
    end_utc = None
    if start_date:
        start_utc = datetime.combine(datetime.strptime(start_date, "%Y-%m-%d").date(), time.min) - TH_OFFSET
    if end_date:
        end_utc = datetime.combine(datetime.strptime(end_date, "%Y-%m-%d").date(), time.max) - TH_OFFSET
    if start_utc and not end_utc:
        end_utc = datetime.combine((start_utc + TH_OFFSET).date(), time.max) - TH_OFFSET
    if end_utc and not start_utc:
        start_utc = datetime.combine((end_utc + TH_OFFSET).date(), time.min) - TH_OFFSET
    return start_utc, end_utc


def _resolve_monitored_window(rows, start_utc: Optional[datetime], end_utc: Optional[datetime]) -> Tuple[datetime, datetime]:
    if start_utc and end_utc:
        return start_utc, end_utc

    points_start = [r.created_at for r in rows if r.created_at]
    points_end = [(r.closed_at or r.created_at) for r in rows if r.created_at]
    if points_start and points_end:
        return min(points_start), max(points_end)

    now_th = datetime.utcnow() + TH_OFFSET
    local_start = datetime.combine(now_th.date(), time.min)
    local_end = datetime.combine(now_th.date(), time.max)
    return local_start - TH_OFFSET, local_end - TH_OFFSET


def _count_planned_days(monitored_start: datetime, monitored_end: datetime) -> int:
    start_local = (monitored_start + TH_OFFSET).date()
    end_local = (monitored_end + TH_OFFSET).date()
    if end_local < start_local:
        return 1
    return max((end_local - start_local).days + 1, 1)


def _round_secs(value: float | int) -> int:
    return int(round(float(value or 0)))


def _clip_interval_seconds(
    start_at: Optional[datetime],
    end_at: Optional[datetime],
    window_start: datetime,
    window_end: datetime,
) -> float:
    if not start_at or not end_at:
        return 0.0
    clipped_start = max(start_at, window_start)
    clipped_end = min(end_at, window_end)
    if clipped_end <= clipped_start:
        return 0.0
    return float((clipped_end - clipped_start).total_seconds())


def _compute_raw_metrics(rows, monitored_start: datetime, monitored_end: datetime) -> Dict[str, object]:
    downtime_secs = 0.0
    total_doing_secs = 0
    done_count = 0
    cancelled_count = 0
    incident_count = 0

    for row in rows:
        if row.status == "DONE":
            done_count += 1
        elif row.status == "CANCELLED":
            cancelled_count += 1

        total_doing_secs += int(row.doing_secs or 0)

        if row.created_at and row.closed_at:
            d = _clip_interval_seconds(
                row.created_at,
                row.closed_at,
                monitored_start,
                monitored_end,
            )
            if d > 0:
                downtime_secs += d
                incident_count += 1

    planned_days = _count_planned_days(monitored_start, monitored_end)
    planned_secs = planned_days * PLANNED_PRODUCTION_SECS_PER_DAY

    uptime_secs = max(float(planned_secs) - downtime_secs, 0.0)
    mttr_secs = (float(total_doing_secs) / incident_count) if incident_count > 0 else 0.0
    mtbf_secs = (uptime_secs / incident_count) if incident_count > 0 else 0.0

    denominator = uptime_secs + downtime_secs
    availability_percent = (uptime_secs * 100.0 / denominator) if denominator > 0 else 0.0
    downtime_percent = (downtime_secs * 100.0 / denominator) if denominator > 0 else 0.0

    return {
        "downtime_secs": downtime_secs,
        "total_doing_secs": total_doing_secs,
        "incident_count": incident_count,
        "mttr_secs": mttr_secs,
        "mtbf_secs": mtbf_secs,
        "uptime_secs": uptime_secs,
        "planned_days": planned_days,
        "planned_secs": planned_secs,
        "monitored_secs": planned_secs,
        "availability_percent": availability_percent,
        "downtime_percent": downtime_percent,
        "done_count": done_count,
        "cancelled_count": cancelled_count,
        "start_th": fmt_th(monitored_start),
        "end_th": fmt_th(monitored_end),
    }


def build_monitoring_metrics(rows, start_utc: Optional[datetime], end_utc: Optional[datetime]):
    monitored_start, monitored_end = _resolve_monitored_window(rows, start_utc, end_utc)
    raw = _compute_raw_metrics(rows, monitored_start, monitored_end)
    target_percent = 85.0

    return {
        "downtime_secs": _round_secs(raw["downtime_secs"]),
        "downtime_hms": _fmt_hms(_round_secs(raw["downtime_secs"])),
        "total_doing_hms": _fmt_hms(_round_secs(raw["total_doing_secs"])),
        "incident_count": int(raw["incident_count"]),
        "mttr_hms": _fmt_hms(_round_secs(raw["mttr_secs"])),
        "mtbf_hms": _fmt_hms(_round_secs(raw["mtbf_secs"])),
        "uptime_hms": _fmt_hms(_round_secs(raw["uptime_secs"])),
        "planned_hms": _fmt_hms(_round_secs(raw["planned_secs"])),
        "monitored_hms": _fmt_hms(_round_secs(raw["monitored_secs"])),
        "availability_percent": round(float(raw["availability_percent"]), 2),
        "downtime_percent": round(float(raw["downtime_percent"]), 2),
        "target_percent": target_percent,
        "is_on_target": float(raw["availability_percent"]) >= target_percent,
        "done_count": int(raw["done_count"]),
        "cancelled_count": int(raw["cancelled_count"]),
        "planned_days": int(raw["planned_days"]),
        "planned_hours_per_day": PLANNED_PRODUCTION_HOURS_PER_DAY,
        "start_th": fmt_th(monitored_start),
        "end_th": fmt_th(monitored_end),
    }


def build_monitoring_line_metrics(rows, start_utc: Optional[datetime], end_utc: Optional[datetime]) -> List[Dict[str, object]]:
    grouped: Dict[str, List[object]] = {}
    for row in rows:
        line_op = ((getattr(row, "machine", None) or "").strip()) or "-"
        grouped.setdefault(line_op, []).append(row)

    out: List[Dict[str, object]] = []
    for line_op in sorted(grouped.keys(), key=lambda s: s.lower()):
        line_rows = grouped[line_op]
        monitored_start, monitored_end = _resolve_monitored_window(line_rows, start_utc, end_utc)
        raw = _compute_raw_metrics(line_rows, monitored_start, monitored_end)
        mtbf_secs = int(raw["mtbf_secs"])
        mttr_secs = int(raw["mttr_secs"])

        out.append({
            "line_op": line_op,
            "ticket_count": len(line_rows),
            "incident_count": int(raw["incident_count"]),
            "downtime_percent": round(float(raw["downtime_percent"]), 2),
            "downtime_hours": round(float(raw["downtime_secs"]) / 3600.0, 2),
            "availability_percent": round(float(raw["availability_percent"]), 2),
            "uptime_hours": round(float(raw["uptime_secs"]) / 3600.0, 2),
            "planned_hours": round(float(raw["planned_secs"]) / 3600.0, 2),
            "mtbf_hours": round(mtbf_secs / 3600.0, 2),
            "mttr_hours": round(mttr_secs / 3600.0, 2),
            "downtime_hms": _fmt_hms(_round_secs(raw["downtime_secs"])),
            "mtbf_hms": _fmt_hms(_round_secs(mtbf_secs)),
            "mttr_hms": _fmt_hms(_round_secs(mttr_secs)),
            "start_th": fmt_th(monitored_start),
            "end_th": fmt_th(monitored_end),
        })

    return out
