"""Load .env from project root before other modules read os.environ."""

import os
import sys
from pathlib import Path

_loaded = False


def project_root() -> Path:
    return Path(__file__).resolve().parent.parent


def ensure_env_loaded() -> None:
    global _loaded
    if _loaded:
        return

    try:
        from dotenv import load_dotenv
    except ImportError:
        _loaded = True
        return

    load_dotenv(project_root() / ".env")
    _loaded = True


def get_env(name: str) -> str:
    """Load .env and return the named variable, or exit with code 1 if missing."""
    ensure_env_loaded()
    value = (os.getenv(name) or "").strip()
    if not value:
        raise SystemExit(1)
    return value


ensure_env_loaded()

if __name__ == "__main__":
    if len(sys.argv) < 2:
        raise SystemExit(2)
    print(get_env(sys.argv[1]))
