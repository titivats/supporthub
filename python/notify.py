import os

import requests

LINE_TOKEN = os.getenv("LINE_NOTIFY_TOKEN", "").strip()


def line_notify(message: str) -> None:
    if not LINE_TOKEN:
        return
    try:
        requests.post(
            "https://notify-api.line.me/api/notify",
            headers={"Authorization": f"Bearer {LINE_TOKEN}"},
            data={"message": message},
            timeout=3.0,
        )
    except Exception:
        pass
