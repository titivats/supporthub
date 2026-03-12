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

engine = create_engine(DATABASE_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)
Base = declarative_base()
ENABLE_POSTGRES_DISPLAY_TABLES = (
    (os.getenv("SUPPORTHUB_ENABLE_POSTGRES_DISPLAY_TABLES") or "").strip().lower()
    in {"1", "true", "yes", "on"}
)

