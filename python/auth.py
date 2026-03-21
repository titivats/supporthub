import hashlib
import hmac
import os
import re
import secrets
from pathlib import Path

from itsdangerous import BadSignature, TimestampSigner

APP_ENV = (os.getenv("SUPPORTHUB_ENV") or "local").strip().lower()
SESSION_AGE = int(os.getenv("SUPPORTHUB_SESSION_AGE", str(60 * 60 * 24 * 7)))
default_secure_cookies = "false" if APP_ENV in ("local", "dev", "development") else "true"
SECURE_COOKIES = os.getenv("SUPPORTHUB_SECURE_COOKIES", default_secure_cookies).lower() in ("1", "true", "yes", "on")
HEX64 = re.compile(r"^[0-9a-f]{64}$", re.I)
PROJECT_DIR = Path(__file__).resolve().parent.parent


def _load_secret() -> str:
    env_secret = (os.getenv("SUPPORTHUB_SECRET") or "").strip()
    if env_secret:
        return env_secret

    secret_file = Path(
        (os.getenv("SUPPORTHUB_SECRET_FILE") or "").strip()
        or (PROJECT_DIR / "secret_key")
    )
    try:
        if secret_file.exists():
            file_secret = secret_file.read_text(encoding="utf-8").strip()
            if file_secret:
                return file_secret

        secret_file.parent.mkdir(parents=True, exist_ok=True)
        new_secret = secrets.token_urlsafe(48)
        secret_file.write_text(new_secret, encoding="utf-8")
        return new_secret
    except Exception:
        return secrets.token_urlsafe(48)


SECRET = _load_secret()


def sha256(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def verify_password(plain: str, stored: str) -> bool:
    plain, stored = (plain or "").strip(), (stored or "").strip()
    if HEX64.match(stored):
        return hmac.compare_digest(sha256(plain), stored.lower())
    return hmac.compare_digest(plain, stored)


def make_session_token(username: str) -> str:
    return TimestampSigner(SECRET).sign(username).decode()


def read_session_token(token: str) -> str:
    return TimestampSigner(SECRET).unsign(token, max_age=SESSION_AGE).decode()
