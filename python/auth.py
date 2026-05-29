import hashlib
import hmac
import re

from itsdangerous import BadSignature, TimestampSigner

from python.settings import APP_ENV, SECURE_COOKIES, SECRET, SESSION_AGE

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
