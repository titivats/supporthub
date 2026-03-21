import os

from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
DATABASE_URL = (os.getenv("SUPPORTHUB_DATABASE_URL") or "").strip()
if not DATABASE_URL:
    raise RuntimeError("SUPPORTHUB_DATABASE_URL is required (PostgreSQL only).")
if not (
    DATABASE_URL.lower().startswith("postgresql://")
    or DATABASE_URL.lower().startswith("postgresql+psycopg://")
):
    raise RuntimeError(
        "Invalid SUPPORTHUB_DATABASE_URL. PostgreSQL URL is required "
        "(postgresql:// or postgresql+psycopg://)."
    )

def _int_env(name: str, default: int) -> int:
    raw = (os.getenv(name) or "").strip()
    if not raw:
        return default
    try:
        return int(raw)
    except Exception:
        return default


DB_POOL_SIZE = max(1, _int_env("SUPPORTHUB_DB_POOL_SIZE", 20))
DB_MAX_OVERFLOW = max(0, _int_env("SUPPORTHUB_DB_MAX_OVERFLOW", 40))
DB_POOL_TIMEOUT = max(5, _int_env("SUPPORTHUB_DB_POOL_TIMEOUT", 30))
DB_POOL_RECYCLE = max(60, _int_env("SUPPORTHUB_DB_POOL_RECYCLE", 1800))
RUN_DB_MAINTENANCE_ON_STARTUP = (
    (os.getenv("SUPPORTHUB_RUN_DB_MAINTENANCE_ON_STARTUP") or "").strip().lower()
    in {"1", "true", "yes", "on"}
)

engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,
    pool_size=DB_POOL_SIZE,
    max_overflow=DB_MAX_OVERFLOW,
    pool_timeout=DB_POOL_TIMEOUT,
    pool_recycle=DB_POOL_RECYCLE,
    pool_use_lifo=True,
)
SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)
Base = declarative_base()
ENABLE_POSTGRES_DISPLAY_TABLES = (
    (os.getenv("SUPPORTHUB_ENABLE_POSTGRES_DISPLAY_TABLES") or "").strip().lower()
    in {"1", "true", "yes", "on"}
)
