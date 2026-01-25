# reset_admin_flexible.py
# Purpose: Ensure ADMIN user exists and set its password to 259487123,
# adapting to whatever column names your current "users" table uses.
#
# Usage:
#   cd C:\supporthub
#   venv\Scripts\python reset_admin_flexible.py
# or:
#   python reset_admin_flexible.py
import os, sqlite3, hashlib, sys

DB_PATH = os.path.join(os.path.dirname(__file__), "supporthub.db")
USERNAME = "ADMIN"
PASSWORD_PLAIN = "259487123"
PASSWORD_HASH  = hashlib.sha256(PASSWORD_PLAIN.encode("utf-8")).hexdigest()

if not os.path.exists(DB_PATH):
    print("Database not found:", DB_PATH)
    sys.exit(1)

con = sqlite3.connect(DB_PATH)
con.row_factory = sqlite3.Row
cur = con.cursor()

# --- Discover schema ---
def table_exists(name):
    cur.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?;", (name,))
    return cur.fetchone() is not None

if not table_exists("users"):
    # Create a safe baseline if missing
    cur.execute("""
    CREATE TABLE users(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE,
        passhash TEXT,
        role TEXT
    );
    """)
    con.commit()
    print("Created table users with columns: username, passhash, role")

# Read columns
cur.execute("PRAGMA table_info(users);")
cols_info = cur.fetchall()
cols = [c["name"] for c in cols_info]
cols_lower = [c.lower() for c in cols]

# Determine column names
user_col = "username" if "username" in cols_lower else ( "user" if "user" in cols_lower else cols[0] )
role_col = "role" if "role" in cols_lower else None

# Pick a password column (prefer hashed names)
pw_candidates = ["passhash","password_hash","pwdhash","hash","password","pass","pwd"]
pw_col = None
for c in pw_candidates:
    if c in cols_lower:
        pw_col = cols[cols_lower.index(c)]
        break

# Add missing columns (best-effort)
def ensure_column(name, decl):
    cur.execute("PRAGMA table_info(users);")
    if name.lower() not in [r["name"].lower() for r in cur.fetchall()]:
        cur.execute(f"ALTER TABLE users ADD COLUMN {name} {decl};")
        print(f"Added column {name} {decl}")

if role_col is None:
    ensure_column("role", "TEXT")
    role_col = "role"

if pw_col is None:
    # default to passhash (hashed)
    ensure_column("passhash", "TEXT")
    pw_col = "passhash"

# --- Upsert ADMIN ---
def row_exists():
    cur.execute(f"SELECT rowid FROM users WHERE UPPER({user_col})=?", (USERNAME.upper(),))
    r = cur.fetchone()
    return r[0] if r else None

admin_id = row_exists()
if admin_id:
    # Update primary password column
    cur.execute(f"UPDATE users SET {pw_col}=?, {role_col}=? WHERE rowid=?", (PASSWORD_HASH, "Admin", admin_id))
    # If there is ALSO a plain column, fill it too
    for plain_col in ["password_plain","pwd_plain","plainpass"]:
        if plain_col in cols_lower:
            true_name = cols[cols_lower.index(plain_col)]
            cur.execute(f"UPDATE users SET {true_name}=? WHERE rowid=?", (PASSWORD_PLAIN, admin_id))
    print(f"Updated ADMIN → {user_col}='{USERNAME}', {pw_col}=<sha256>, role='Admin'")
else:
    # Build insert column list based on what exists
    insert_cols = [user_col, pw_col]
    insert_vals = [USERNAME, PASSWORD_HASH]
    if role_col: insert_cols.append(role_col); insert_vals.append("Admin")
    # If there's a plain column, include it as well
    for plain_col in ["password_plain","pwd_plain","plainpass"]:
        if plain_col in cols_lower:
            true_name = cols[cols_lower.index(plain_col)]
            insert_cols.append(true_name); insert_vals.append(PASSWORD_PLAIN)
    qmarks = ",".join("?" for _ in insert_cols)
    cur.execute(f"INSERT INTO users({','.join(insert_cols)}) VALUES({qmarks})", insert_vals)
    print(f"Inserted ADMIN with columns {insert_cols}")

con.commit()

# Print final state for verification
cur.execute(f"SELECT {user_col} as user, {pw_col} as pwcol, {role_col} as role FROM users WHERE UPPER({user_col})=?", (USERNAME.upper(),))
print("Row:", dict(cur.fetchone()))
print("OK → Username=ADMIN  Password=259487123  (stored sha256 in column:", pw_col, ")")

con.close()
