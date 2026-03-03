from datetime import datetime, time
from typing import Optional

from python.time_utils import TH_OFFSET, fmt_hms as _fmt_hms, fmt_th


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


def build_monitoring_metrics(rows, start_utc: Optional[datetime], end_utc: Optional[datetime]):
    downtime_secs = 0
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
            d = int((row.closed_at - row.created_at).total_seconds())
            if d > 0:
                downtime_secs += d
                incident_count += 1

    monitored_start = start_utc
    monitored_end = end_utc
    if not (monitored_start and monitored_end):
        points_start = [r.created_at for r in rows if r.created_at]
        points_end = [(r.closed_at or r.created_at) for r in rows if r.created_at]
        if points_start and points_end:
            monitored_start = min(points_start)
            monitored_end = max(points_end)
        else:
            now_th = datetime.utcnow() + TH_OFFSET
            local_start = datetime.combine(now_th.date(), time.min)
            local_end = datetime.combine(now_th.date(), time.max)
            monitored_start = local_start - TH_OFFSET
            monitored_end = local_end - TH_OFFSET

    monitored_secs = 0
    if monitored_start and monitored_end:
        monitored_secs = max(int((monitored_end - monitored_start).total_seconds()), 0)
    monitored_secs = max(monitored_secs, downtime_secs)

    uptime_secs = max(monitored_secs - downtime_secs, 0)
    mttr_secs = int(total_doing_secs / incident_count) if incident_count > 0 else 0
    mtbf_secs = int((21 * 3600) / incident_count) if incident_count > 0 else 0

    denominator = uptime_secs + downtime_secs
    oee_percent = (uptime_secs * 100.0 / denominator) if denominator > 0 else 0.0
    target_percent = 85.0

    return {
        "downtime_secs": downtime_secs,
        "downtime_hms": _fmt_hms(downtime_secs),
        "total_doing_hms": _fmt_hms(total_doing_secs),
        "incident_count": incident_count,
        "mttr_hms": _fmt_hms(mttr_secs),
        "mtbf_hms": _fmt_hms(mtbf_secs),
        "uptime_hms": _fmt_hms(uptime_secs),
        "monitored_hms": _fmt_hms(monitored_secs),
        "oee_percent": round(oee_percent, 2),
        "target_percent": target_percent,
        "is_on_target": oee_percent >= target_percent,
        "done_count": done_count,
        "cancelled_count": cancelled_count,
        "start_th": fmt_th(monitored_start),
        "end_th": fmt_th(monitored_end),
    }
