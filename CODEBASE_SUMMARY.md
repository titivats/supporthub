# SupportHub — Codebase Summary

**SupportHub** (UI brand: "ME SupportHub") is a manufacturing-engineering support
ticket system for production lines. Technicians create and manage equipment problem
tickets, admins maintain master data (lines, machines, problems), and the app provides
history export, OEE monitoring metrics, and live MQTT power telemetry.

---

## Tech Stack

- **Backend:** Python 3, FastAPI, Uvicorn (ASGI)
- **Templating:** Jinja2 (server-rendered HTML)
- **Database:** PostgreSQL via SQLAlchemy 2 + psycopg 3
- **Config:** python-dotenv (`.env` → `python/settings.py`)
- **IoT:** paho-mqtt (background telemetry subscriber)
- **Export:** xlsxwriter (Excel)
- **Auth:** itsdangerous signed session cookies, SHA-256 passwords
- **Notifications:** LINE Notify (optional)
- **Deployment:** Windows + IIS reverse proxy (optional)

No frontend build step or JS framework — plain HTML/CSS/JS in templates.

---

## Project Structure

| Path | Purpose |
|------|---------|
| `python/` | FastAPI app, routes, auth, database, IoT, OEE |
| `python/settings.py` | All config read from `.env` |
| `python/load_env.py` | Loads `.env` on import |
| `html/` | Jinja2 HTML templates |
| `db/` | PostgreSQL DDL (`01_*.sql`) + `apply.bat` |
| `python/master_data.py` | Default master data + manual seed CLI |
| `.env` | Local config (not in git) — copy from `.env.example` |
| `web.config` | IIS reverse proxy only (no secrets) |
| `requirements.txt` | Python dependencies |
| `service/` | Windows service install scripts (NSSM) |

---

## Entry Points

| File | Role |
|------|------|
| `python/server_app.py` | Uvicorn entry — loads `.env`, imports `app` |
| `python/app.py` | FastAPI app, routes, IoT lifecycle, master-data helpers |
| `python/master_data.py` | Default master data constants + **manual** DB seed CLI |

**App startup (`python/app.py`):**

1. `init_db()` — tables, PostgreSQL views/triggers, optional ADMIN bootstrap
2. `register_web_routes(...)` — HTTP routes
3. `startup` / `shutdown` — MQTT IoT background thread

Master data is **not** seeded on app startup. Run once manually (see below).

---

## Configuration

All app settings are in **`.env`**. See `.env.example` for the full list.

| Variable | Purpose |
|----------|---------|
| `SUPPORTHUB_DATABASE_URL` | PostgreSQL URL (required) |
| `SUPPORTHUB_BOOTSTRAP_ADMIN_PASSWORD` | Create `ADMIN` user on first `init_db()` |
| `SUPPORTHUB_ENV` | `local` / `dev` / production |
| `SUPPORTHUB_SECRET` | Session signing (auto-generated if empty) |
| `SUPPORTHUB_SESSION_AGE` | Cookie lifetime in seconds (default 604800 = 7 days) |
| `SUPPORTHUB_SECURE_COOKIES` | `true` / `false` |
| `SUPPORTHUB_HOST` | Uvicorn bind host (default `127.0.0.1`) |
| `SUPPORTHUB_PORT` | Uvicorn bind port (default `8888`) |
| `SUPPORTHUB_BASE_URL` | URL prefix for all routes (default `/supporthub`) |
| `SUPPORTHUB_LINE_MACHINE_MAP_FILE` | Path to line→monitoring JSON (empty = default under `database/`) |
| `LINE_NOTIFY_TOKEN` | LINE Notify bearer token (optional) |
| `SUPPORTHUB_MQTT_HOST` | MQTT broker host |
| `SUPPORTHUB_MQTT_PORT` | MQTT broker port |
| `SUPPORTHUB_MQTT_TOPIC` | MQTT subscribe topic |
| `SUPPORTHUB_MQTT_CLIENT_ID` | MQTT client id |
| `SUPPORTHUB_IOT_SAMPLE_LIMIT` | In-memory trend samples per metric |

**Load order:** `import python.load_env` → reads `.env` → `python/settings.py` exposes values.

`web.config` is for IIS proxy to Uvicorn only.

---

## Database

### Schema (manual / optional)

```bat
cd db
apply.bat
```

SQL files: `01_core_tables.sql`, `02_iot_tables.sql`, `03_history_view.sql`.  
Details: `db/README.md`.

### App layer

```
python/load_env.py      → loads .env
python/settings.py      → DATABASE_URL, MQTT, auth, etc.
python/db.py            → re-exports database.core
python/database/
  core.py               → SQLAlchemy models, init_db(), triggers/views
  __init__.py
```

- **Connection:** `SUPPORTHUB_DATABASE_URL` in `.env` (PostgreSQL only).
- **Session:** `get_db()` per request.

### Core tables

| Model | Table | Purpose |
|-------|-------|---------|
| `User` | `users` | Auth |
| `Ticket` | `tickets` | Support tickets + workflow |
| `TicketTakeoverLog` | `ticket_takeover_logs` | Handoff audit |
| `MasterLine` | `master_lines` | Line numbers |
| `MasterMachine` | `master_machines` | Machine categories |
| `MasterMachineType` | `master_machine_types` | Machine types |
| `MasterMachineId` | `master_machine_ids` | Machine IDs |
| `MasterProblem` | `master_problems` | Problems |
| `MasterSupportArea` | `master_support_areas` | Support areas |
| `MasterSupportAreaMap` | `master_support_area_maps` | Area ↔ machine |
| `AppSetting` | `app_settings` | Key-value (e.g. seed flag) |
| `MasterAuditLog` | `master_audit_logs` | Admin audit |

**Ticket workflow:** `PENDING → DOING → HOLD → DONE / CANCELLED`

**PostgreSQL extras (from `init_db()`):** `v_history_log`, reporting tables + triggers, IoT tables.

**File-based:** `database/monitoring_line_map.json` (gitignored) for line→monitoring mapping.

---

## Master data (manual seed)

Defaults live in `python/master_data.py` (lines, machines, types, problems, support areas).

**First-time seed** (after DB schema exists):

```powershell
cd d:\project\supporthub
.\venv\Scripts\Activate.ps1
python -m python.master_data
```

- Runs once; sets `app_settings.master_seed_v1 = 1`.
- To seed again: `DELETE FROM app_settings WHERE key = 'master_seed_v1';` then re-run.

Edit defaults in `python/master_data.py` before seeding.

---

## How to Run

### Prerequisites

- **Python 3.10+** with `venv`
- **PostgreSQL** running (e.g. Docker on `127.0.0.1:5432`)
- Project root: `d:\project\supporthub` (all commands below run from here)

---

### First-time setup

**1. Config**

```powershell
cd d:\project\supporthub
copy .env.example .env
notepad .env
```

Edit at least:

| Variable | Example |
|----------|---------|
| `SUPPORTHUB_DATABASE_URL` | `postgresql+psycopg://postgres:medeveloper@127.0.0.1:5432/supporthub` |
| `SUPPORTHUB_BOOTSTRAP_ADMIN_PASSWORD` | your ADMIN password (used once on first app start) |
| `SUPPORTHUB_HOST` / `SUPPORTHUB_PORT` | `127.0.0.1` / `8888` |

**2. Python environment**

```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

**3. Database schema** (pick one)

```bat
cd db
apply.bat
cd ..
```

Or skip — `init_db()` creates tables when the app starts.

**4. Master data** (once)

```powershell
python -m python.master_data
```

**5. Start app** (creates `ADMIN` user if missing, using `SUPPORTHUB_BOOTSTRAP_ADMIN_PASSWORD`)

```powershell
cd d:\project\supporthub
.\venv\Scripts\Activate.ps1
python -m uvicorn python.server_app:app --host 127.0.0.1 --port 8888
```

**6. Open browser**

- App: http://127.0.0.1:8888/supporthub
- Login: http://127.0.0.1:8888/supporthub/login  
  - Username: `ADMIN`  
  - Password: value of `SUPPORTHUB_BOOTSTRAP_ADMIN_PASSWORD` in `.env`

---

### Every day (after setup)

```powershell
cd d:\project\supporthub
.\venv\Scripts\Activate.ps1

# 1) Start PostgreSQL (Docker container, etc.)
# 2) Start app
python -m uvicorn python.server_app:app --host 127.0.0.1 --port 8888
```

Use host/port from `.env` if you changed them.

**Dev mode** (auto-reload on code change):

```powershell
python -m uvicorn python.server_app:app --host 127.0.0.1 --port 8888 --reload
```

---

### Production (Windows + IIS)

1. Run Uvicorn bound to `127.0.0.1:8888` (same command as above).
2. Deploy `web.config` in IIS — reverse proxy to Uvicorn (no secrets in `web.config`; use `.env` on the server).

---

### Troubleshooting

| Problem | What to check |
|---------|----------------|
| `SUPPORTHUB_DATABASE_URL is required` | `.env` exists in project root; restart terminal after editing |
| DB connection error | PostgreSQL running; URL/user/password/database name in `.env` |
| Login fails for `ADMIN` | User created on first start — delete `ADMIN` in `users` table and restart app, or fix password in DB |
| Empty dropdowns (Line/Machine) | Run `python -m python.master_data` |
| Template error after upgrade | Restart app (uses `_TemplatesCompat` for Starlette 1.x) |

---

## Major Modules

| Module | Path | Responsibility |
|--------|------|----------------|
| Settings | `python/settings.py` | Config from `.env` |
| App | `python/app.py` | FastAPI, line-machine map, route deps |
| Routes | `python/routes/web_routes.py` + `sections/*` | HTTP handlers |
| Auth | `python/auth.py` | Sessions, passwords |
| DB | `python/database/core.py` | ORM, `init_db()` |
| Master seed | `python/master_data.py` | Default master data + CLI |
| OEE | `python/OEE/oee_metrics.py` | Downtime, MTTR, MTBF, OEE % |
| IoT | `python/IoT/iot_monitor_service.py` | MQTT → PostgreSQL + live API |
| Notify | `python/notify.py` | LINE Notify |

### UI templates (`html/`)

| Template | Page |
|----------|------|
| `index.html` | Active tickets + create request |
| `login.html`, `add_user.html` | Login / signup |
| `history.html` | Ticket history |
| `OEE/monitoring.html` | OEE dashboard |
| `IoT/iot_monitor.html` | Live MQTT telemetry |
| `add_machine.html` | Admin master data |
| `manage_users.html` | Admin users |

---

## Routes (summary)

All routes are prefixed with `SUPPORTHUB_BASE_URL` (default `/supporthub`).

| Area | Examples |
|------|----------|
| Auth | `GET/POST /supporthub/login`, `/supporthub/logout`, `/supporthub/signup` |
| Tickets | `GET /supporthub/`, `POST /supporthub/request/create`, `POST /supporthub/tickets/{id}/action` |
| History | `GET /supporthub/history?page=1&page_size=50&...filters`, `GET /supporthub/export/excel` |
| History API | `GET /supporthub/api/history?page=1&page_size=50&...filters` → JSON `{total, page, page_size, total_pages, items[]}` |
| OEE / IoT | `/supporthub/monitoring`, `/supporthub/iot-monitor`, `/supporthub/api/iot-monitor/status` |
| Polling | `GET /supporthub/api/active/version` |
| Admin | `/supporthub/admin/users`, `/supporthub/admin/machines` (+ CRUD POST routes) |

---

## Architecture

```mermaid
flowchart TB
    subgraph config [Config]
        ENV[".env"]
        LOAD["load_env.py"]
        SET["settings.py"]
        ENV --> LOAD --> SET
    end

    subgraph entry [App entry]
        SRV["server_app.py"]
        APP["app.py"]
        DBINIT["init_db()"]
        SRV --> APP --> DBINIT
        SET --> APP
    end

    subgraph client [Client]
        Browser["Browser"]
        IIS["IIS web.config optional"]
        UV["Uvicorn SUPPORTHUB_HOST:PORT"]
        Browser --> IIS --> UV
        Browser -.->|dev direct| UV
        UV --> SRV
    end

    subgraph http [HTTP layer]
        WR["web_routes.py"]
        SEC["sections: auth | tickets | admin | history-oee-iot"]
        HTML["html/ templates"]
        APP --> WR --> SEC --> HTML
    end

    subgraph storage [Storage]
        PG[(PostgreSQL)]
        JSON["monitoring_line_map.json"]
        SEC --> PG
        DBINIT --> PG
        APP --> JSON
        DBINIT -. sync .-> PG
    end

    subgraph iot [IoT]
        MQTT["MQTT broker"]
        IOT["iot_monitor_service"]
        APP -->|startup thread| IOT
        MQTT --> IOT
        IOT --> PG
    end

    subgraph optional [Optional]
        LINE["LINE Notify API"]
        SEC --> LINE
    end

    subgraph setup [One-time setup]
        SQL["db/apply.bat + *.sql"]
        SEED["python -m python.master_data"]
        SQL --> PG
        SEED --> PG
    end

    subgraph winsvc [Windows Service optional]
        NSSM["NSSM install_service.bat"]
        SVC["SupportHub service"]
        NSSM --> SVC --> UV
    end
```

---

## Design notes

1. Monolithic FastAPI; routes registered via a shared `deps` dict.
2. PostgreSQL only — invalid/missing `SUPPORTHUB_DATABASE_URL` fails at import.
3. Config centralized in `.env` + `settings.py` (not `web.config`).
4. Master data seed is manual (`python -m python.master_data`), not on every app start.
5. Line monitoring map stored in JSON file, synced to a PG table for reporting.
6. Real-time ticket list: `ACTIVE_VERSION` + poll `/api/active/version`.
7. Display times use Thailand UTC+7 (`python/time_utils.py`).
8. Roles: Operator, Engineer, Technician, Admin. Public signup allows non-admin roles only; non-admin usernames must be exactly 6 digits.
9. Base URL prefix (`SUPPORTHUB_BASE_URL`, default `/supporthub`) applied via `APIRouter(prefix=BASE_URL)` in `app.py`; Jinja2 global `base_url` makes it available in all templates; all `RedirectResponse` calls in routes use it too.
10. History page is server-side paginated (`page`, `page_size` query params, default 50 rows/page). `GET /supporthub/api/history` is a JSON API with the same filters and pagination returning `{total, page, page_size, total_pages, items[]}`.

---

## Tests

No automated test suite in the repo.
