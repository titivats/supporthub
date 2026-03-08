import hashlib
import hmac
import os
import re
import secrets

from itsdangerous import BadSignature, TimestampSigner

APP_ENV = (os.getenv("SUPPORTHUB_ENV") or "local").strip().lower()
SECRET = (os.getenv("SUPPORTHUB_SECRET") or "").strip() or secrets.token_urlsafe(48)
SESSION_AGE = int(os.getenv("SUPPORTHUB_SESSION_AGE", str(60 * 60 * 24 * 7)))
default_secure_cookies = "false" if APP_ENV in ("local", "dev", "development") else "true"
SECURE_COOKIES = os.getenv("SUPPORTHUB_SECURE_COOKIES", default_secure_cookies).lower() in ("1", "true", "yes", "on")
HEX64 = re.compile(r"^[0-9a-f]{64}$", re.I)


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
