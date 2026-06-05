@echo off
setlocal

set "SCRIPT_DIR=%~dp0"
set "REQ_FILE=%SCRIPT_DIR%requirements.txt"
set "WHEEL_DIR=%SCRIPT_DIR%wheels"

if not exist "%REQ_FILE%" (
  echo [ERROR] requirements.txt not found at "%REQ_FILE%"
  exit /b 1
)

if not exist "%WHEEL_DIR%" (
  echo [ERROR] wheels folder not found at "%WHEEL_DIR%"
  echo Build wheels first, for example:
  echo   python -m pip wheel -r requirements.txt -w wheels
  exit /b 1
)

if "%~1"=="" (
  set "PYTHON_CMD=python"
) else (
  set "PYTHON_CMD=%~1"
)

echo Installing from local wheels in "%WHEEL_DIR%"...
"%PYTHON_CMD%" -m pip install --no-index --find-links "%WHEEL_DIR%" -r "%REQ_FILE%"
if errorlevel 1 (
  echo [ERROR] Installation failed.
  exit /b 1
)

echo [OK] Installation completed from local wheels.
endlocal
