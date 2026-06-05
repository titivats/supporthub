"""
Migrate tickets table from SQLite to PostgreSQL.

Usage:
    python db_supporthub/migrate_tickets_to_postgres.py

Set PG_DSN env var or edit POSTGRES_DSN below.
"""

import os
import sqlite3
from datetime import datetime

from pathlib import Path

import psycopg
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")

SQLITE_PATH = r"D:\project\supporthub\db_supporthub\supporthub.db"

_db_url = os.getenv("SUPPORTHUB_DATABASE_URL", "")
# Convert SQLAlchemy URL (postgresql+psycopg://...) to psycopg DSN
POSTGRES_DSN = _db_url.replace("postgresql+psycopg://", "postgresql://")

CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS tickets (
    id              INTEGER PRIMARY KEY,
    created_at      TIMESTAMP,
    closed_at       TIMESTAMP,
    requester       VARCHAR(50)  NOT NULL,
    machine         VARCHAR(50),
    equipment       VARCHAR(200),
    problem         VARCHAR(100),
    description     TEXT,
    status          VARCHAR(12)  NOT NULL,
    doing_started_at TIMESTAMP,
    hold_started_at  TIMESTAMP,
    doing_secs      INTEGER      NOT NULL DEFAULT 0,
    hold_secs       INTEGER      NOT NULL DEFAULT 0,
    current_actor   VARCHAR(50),
    last_action     VARCHAR(10),
    hold_reason     TEXT,
    solution        TEXT,
    done_by         VARCHAR(50),
    cancel_reason   TEXT,
    canceled_by     VARCHAR(50)
);
"""

COLUMNS = (
    "id", "created_at", "closed_at", "requester", "machine", "equipment",
    "problem", "description", "status", "doing_started_at", "hold_started_at",
    "doing_secs", "hold_secs", "current_actor", "last_action", "hold_reason",
    "solution", "done_by", "cancel_reason", "canceled_by",
)

INSERT_SQL = f"""
INSERT INTO tickets ({', '.join(COLUMNS)})
VALUES ({', '.join(['%s'] * len(COLUMNS))});
"""

BATCH_SIZE = 1000


def parse_dt(val):
    if val is None:
        return None
    if isinstance(val, datetime):
        return val
    for fmt in ("%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(val, fmt)
        except ValueError:
            continue
    return val


def migrate():
    print(f"Connecting to SQLite: {SQLITE_PATH}")
    src = sqlite3.connect(SQLITE_PATH)
    src.row_factory = sqlite3.Row

    print(f"Connecting to PostgreSQL: {POSTGRES_DSN}")
    with psycopg.connect(POSTGRES_DSN) as dst:
        with dst.cursor() as cur:
            cur.execute(CREATE_TABLE_SQL)
            cur.execute("TRUNCATE TABLE tickets RESTART IDENTITY;")
        dst.commit()
        print("Table ensured and truncated in PostgreSQL.")

        cur_src = src.cursor()
        cur_src.execute("SELECT COUNT(*) FROM tickets")
        total = cur_src.fetchone()[0]
        print(f"Total rows to migrate: {total:,}")

        cur_src.execute(f"SELECT {', '.join(COLUMNS)} FROM tickets ORDER BY id")

        migrated = 0
        with dst.cursor() as cur_dst:
            while True:
                rows = cur_src.fetchmany(BATCH_SIZE)
                if not rows:
                    break
                batch = [
                    tuple(
                        parse_dt(row[c]) if c.endswith("_at") else row[c]
                        for c in COLUMNS
                    )
                    for row in rows
                ]
                cur_dst.executemany(INSERT_SQL, batch)
                migrated += len(batch)
                print(f"  {migrated:,} / {total:,} rows inserted", end="\r")
            dst.commit()

    print(f"\nDone. {migrated:,} rows migrated.")
    src.close()


if __name__ == "__main__":
    migrate()
