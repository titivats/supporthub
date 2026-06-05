"""
Migrate users table from SQLite to PostgreSQL.

Usage:
    python db_supporthub/migrate_users_to_postgres.py

Set SUPPORTHUB_DATABASE_URL env var or edit the .env file.
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
POSTGRES_DSN = _db_url.replace("postgresql+psycopg://", "postgresql://")

CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS users (
    id              SERIAL PRIMARY KEY,
    username        VARCHAR(50)  NOT NULL,
    password_hash   VARCHAR(128) NOT NULL,
    role            VARCHAR(20)  NOT NULL,
    created_at      TIMESTAMP,
    CONSTRAINT uq_username UNIQUE (username)
);
"""

COLUMNS = ("id", "username", "password_hash", "role", "created_at")

INSERT_SQL = f"""
INSERT INTO users ({', '.join(COLUMNS)})
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
            cur.execute("TRUNCATE TABLE users RESTART IDENTITY CASCADE;")
        dst.commit()
        print("Table ensured and truncated in PostgreSQL.")

        cur_src = src.cursor()
        cur_src.execute("SELECT COUNT(*) FROM users")
        total = cur_src.fetchone()[0]
        print(f"Total rows to migrate: {total:,}")

        cur_src.execute(f"SELECT {', '.join(COLUMNS)} FROM users ORDER BY id")

        migrated = 0
        with dst.cursor() as cur_dst:
            while True:
                rows = cur_src.fetchmany(BATCH_SIZE)
                if not rows:
                    break
                batch = [
                    tuple(
                        parse_dt(row[c]) if c == "created_at" else row[c]
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
