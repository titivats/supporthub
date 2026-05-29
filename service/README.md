# SupportHub Windows Service

Run SupportHub as a Windows service (auto-start on boot) using [NSSM](https://nssm.cc/).

## Before install

1. Complete normal setup: `.env`, `venv`, `pip install -r requirements.txt`
2. PostgreSQL must be running (or start Docker Postgres before/at boot)
3. Optional: `python -m python.master_data` (master data seed)

## Install NSSM

1. Download from https://nssm.cc/download (64-bit)
2. Copy `nssm.exe` to this folder: `service\nssm.exe`  
   Or install NSSM to PATH (`choco install nssm`)

## Install service

**Right-click → Run as administrator:**

```bat
service\install_service.bat
```

- Service name: `SupportHub`
- Start type: Automatic
- Logs: `logs\service_stdout.log`, `logs\service_stderr.log`
- Listens on `127.0.0.1:8888` (edit `install_service.bat` / `run_app.bat` to change)
- MQTT: set `SUPPORTHUB_MQTT_ENABLED=false` in `.env` if the broker is offline (avoids `getaddrinfo failed`)

## Manage service

```bat
nssm start SupportHub
nssm stop SupportHub
nssm restart SupportHub
```

Or use **services.msc** → find **SupportHub**.

## Uninstall

**Run as administrator:**

```bat
service\uninstall_service.bat
```

## Test without service

```bat
service\run_app.bat
```

Same command the service uses (foreground).
