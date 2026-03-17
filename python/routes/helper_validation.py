from __future__ import annotations

from typing import Optional
import re

LINE_MACHINE_ITEM_SEPARATOR = "|||"
USERNAME_NUMERIC_PATTERN = re.compile(r"^\d{6}$")
ALLOWED_ROLES = ("Operator", "Engineer", "Technician", "Admin")
PUBLIC_SIGNUP_ROLES = ("Operator", "Engineer", "Technician")


def default_clean_text(v: Optional[str]) -> str:
    return (v or "").strip()


def is_valid_manage_username(username: str) -> bool:
    return bool(USERNAME_NUMERIC_PATTERN.fullmatch((username or "").strip()))


def is_valid_manage_password(password: str) -> bool:
    return 1 <= len((password or "")) <= 12


def normalize_role(role: Optional[str], allow_admin: bool) -> str:
    raw = (role or "").strip()
    allowed = ALLOWED_ROLES if allow_admin else PUBLIC_SIGNUP_ROLES
    return raw if raw in allowed else ""
