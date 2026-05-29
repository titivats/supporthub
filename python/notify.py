import requests

from python.settings import LINE_NOTIFY_TOKEN


def line_notify(message: str) -> None:
    if not LINE_NOTIFY_TOKEN:
        return
    try:
        requests.post(
            "https://notify-api.line.me/api/notify",
            headers={"Authorization": f"Bearer {LINE_NOTIFY_TOKEN}"},
            data={"message": message},
            timeout=5,
        )
    except Exception as exc:
        print("[LINE] notify failed:", exc)
