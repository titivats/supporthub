from datetime import datetime, timedelta

TH_OFFSET = timedelta(hours=7)


def to_th(dt: datetime | None) -> datetime | None:
    return (dt + TH_OFFSET) if dt else None


def fmt_th(dt: datetime | None) -> str:
    dt_th = to_th(dt)
    return dt_th.strftime("%d-%m-%Y %H:%M:%S") if dt_th else ""


def fmt_hms(sec: int) -> str:
    total = int(sec or 0)
    hours = total // 3600
    minutes = (total % 3600) // 60
    seconds = total % 60
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}"
