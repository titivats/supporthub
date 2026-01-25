@echo off
REM --- Start SupportHub behind IIS reverse proxy ---
REM โฟลเดอร์โปรเจ็กต์ = ตำแหน่งของไฟล์ .bat นี้
set "APPDIR=%~dp0"
cd /d "%APPDIR%"

REM ใช้ venv ในโฟลเดอร์โปรเจ็กต์
set "VENV=%APPDIR%venv"
set "PY=%VENV%\Scripts\python.exe"

IF NOT EXIST "%PY%" (
  echo [!] Python venv not found. Creating one...
  python -m venv "%VENV%"
  "%VENV%\Scripts\python.exe" -m pip install --upgrade pip
  "%VENV%\Scripts\pip.exe" install -r "%APPDIR%requirements.txt"
)

echo Starting Uvicorn...
"%PY%" -m uvicorn server_app:app --host 127.0.0.1 --port 8000 --workers 1 --proxy-headers --forwarded-allow-ips="*"
