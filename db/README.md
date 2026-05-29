# SupportHub Database

PostgreSQL DDL and default master-data seed for SupportHub.

## SQL files (apply in order)

| File | Contents |
|------|----------|
| `01_core_tables.sql` | `users`, `tickets`, `master_*`, `app_settings`, etc. |
| `02_iot_tables.sql` | `iot_monitor_measurements`, `iot_monitor_status_logs` |
| `03_history_view.sql` | View `v_history_log` (Thai time UTC+7) |

## Apply schema

```bat
cd db
apply.bat
```

Edit connection settings at the top of `apply.bat` if needed.

Or use Docker / manual `psql` against your host.

## App connection

Set in project root `.env` (see `.env.example`):

```
SUPPORTHUB_DATABASE_URL=postgresql+psycopg://postgres:medeveloper@127.0.0.1:5432/supporthub
```

The app also runs `init_db()` on startup to create missing objects.

## Master data seed (manual, once)

Default lines, machines, problems, etc. are in `python/master_data.py`.

From project root (with venv active and `.env` configured):

```bat
python -m python.master_data
```

- Skips if already seeded (`app_settings.key = master_seed_v1`).
- To re-run: `DELETE FROM app_settings WHERE key = 'master_seed_v1';`

## Notes

- SQL scripts are idempotent (`IF NOT EXISTS`).
- Reporting tables and triggers are created by the app in `init_db()`, not in these SQL files.
- `ADMIN` user is created by the app when `SUPPORTHUB_BOOTSTRAP_ADMIN_PASSWORD` is set in `.env`.
