@echo off
setlocal
set "ROOT=%~dp0.."
if "%ROOT:~-1%"=="\" set "ROOT=%ROOT:~0,-1%"
set "PY=%ROOT%\venv\Scripts\python.exe"
set "LOGDIR=%ROOT%\logs"

if not exist "%ROOT%\.env" (
  echo [ERROR] .env not found: %ROOT%\.env
  exit /b 1
)
if not exist "%PY%" (
  echo [ERROR] venv not found: %PY%
  exit /b 1
)
if not exist "%LOGDIR%" mkdir "%LOGDIR%"

cd /d "%ROOT%"
"%PY%" -m uvicorn python.server_app:app --host 127.0.0.1 --port 8888
endlocal
