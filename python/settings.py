"""App configuration from .env (loaded via python.load_env)."""

import os
import secrets

import python.load_env  # noqa: F401


def _get(key: str, default: str = "") -> str:
    return (os.getenv(key) or default).strip()


def _get_int(key: str, default: int) -> int:
    raw = os.getenv(key)
    if raw is None or not str(raw).strip():
        return default
    return int(raw)


def _get_bool(key: str, default: bool) -> bool:
    raw = os.getenv(key)
    if raw is None or not str(raw).strip():
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on")


# Database (required)
DATABASE_URL = _get("SUPPORTHUB_DATABASE_URL")
if not DATABASE_URL:
    raise RuntimeError("SUPPORTHUB_DATABASE_URL is required. Set it in .env")
if not (
    DATABASE_URL.lower().startswith("postgresql://")
    or DATABASE_URL.lower().startswith("postgresql+psycopg://")
):
    raise RuntimeError(
        "Invalid SUPPORTHUB_DATABASE_URL. Use postgresql:// or postgresql+psycopg://"
    )

BOOTSTRAP_ADMIN_PASSWORD = _get("SUPPORTHUB_BOOTSTRAP_ADMIN_PASSWORD")
LINE_MACHINE_MAP_FILE = _get("SUPPORTHUB_LINE_MACHINE_MAP_FILE")

# Auth / session
APP_ENV = _get("SUPPORTHUB_ENV", "local").lower()
SECRET = _get("SUPPORTHUB_SECRET") or secrets.token_urlsafe(48)
SESSION_AGE = _get_int("SUPPORTHUB_SESSION_AGE", 60 * 60 * 24 * 7)
SECURE_COOKIES = _get_bool(
    "SUPPORTHUB_SECURE_COOKIES",
    APP_ENV not in ("local", "dev", "development"),
)

# Server (uvicorn)
HOST = _get("SUPPORTHUB_HOST", "127.0.0.1")
PORT = _get_int("SUPPORTHUB_PORT", 8888)
BASE_URL = _get("SUPPORTHUB_BASE_URL", "/supporthub")

# LINE Notify (optional)
LINE_NOTIFY_TOKEN = _get("LINE_NOTIFY_TOKEN")

# MQTT / IoT (set SUPPORTHUB_MQTT_ENABLED=false if broker is unreachable)
MQTT_ENABLED = _get_bool("SUPPORTHUB_MQTT_ENABLED", True)
MQTT_HOST = _get("SUPPORTHUB_MQTT_HOST", "192.168.1.109")
MQTT_PORT = _get_int("SUPPORTHUB_MQTT_PORT", 1883)
MQTT_TOPIC = _get("SUPPORTHUB_MQTT_TOPIC", "power/pzem")
MQTT_CLIENT_ID = _get("SUPPORTHUB_MQTT_CLIENT_ID", "SUPPORTHUB-IOT-MONITOR")
IOT_SAMPLE_LIMIT = _get_int("SUPPORTHUB_IOT_SAMPLE_LIMIT", 180)
