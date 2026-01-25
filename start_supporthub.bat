@echo off
setlocal ENABLEDELAYEDEXPANSION

rem =====================================================================
rem  start_supporthub.bat  (OFFLINE / WHEELS-ONLY / STICKY CONSOLE)
rem    - Installs strictly from local wheels: E:\Data\Web\supporthub\wheels\wheels
rem    - Creates/activates venv
rem    - Runs Uvicorn in foreground
rem    - Always PAUSE at the end (window won't auto-close)
rem    - Writes simple rolling log to logs\start_supporthub.log
rem =====================================================================

set "PROJ=E:\Data\Web\supporthub"
set "REQ=%PROJ%\requirements.txt"
set "WHEELS=E:\Data\Web\supporthub\wheels\wheels"
set "VENV=%PROJ%\venv"
set "HOST=127.0.0.1"
set "PORT=8888"
set "LOGDIR=%PROJ%\logs"
set "LOGFILE=%LOGDIR%\start_supporthub.log"

if not exist "%LOGDIR%" mkdir "%LOGDIR%"

echo.>> "%LOGFILE%"
echo ================== %DATE% %TIME% ================== >> "%LOGFILE%"
echo [INFO] Launcher started >> "%LOGFILE%"

echo.
echo === SupportHub OFFLINE start (wheels only) ===
echo Project : %PROJ%
echo Wheels  : %WHEELS%
echo Venv    : %VENV%
echo Req     : %REQ%
echo Host:Port -> %HOST%:%PORT%
echo.

if not exist "%PROJ%" (
  echo [ERROR] Project folder not found: %PROJ%
  echo [ERROR] Project folder not found: %PROJ% >> "%LOGFILE%"
  goto :END
)
if not exist "%REQ%" (
  echo [ERROR] requirements.txt not found: %REQ%
  echo [ERROR] requirements.txt not found: %REQ% >> "%LOGFILE%"
  goto :END
)
if not exist "%WHEELS%" (
  echo [ERROR] Wheels folder not found: %WHEELS%
  echo [ERROR] Wheels folder not found: %WHEELS% >> "%LOGFILE%"
  goto :END
)

if not exist "%VENV%" (
  echo [INFO] Creating virtual environment...
  echo [INFO] Creating virtual environment... >> "%LOGFILE%"
  python -m venv "%VENV%" >> "%LOGFILE%" 2>&1
  if errorlevel 1 (
    echo [ERROR] Failed to create venv. Is Python installed / on PATH?
    echo [ERROR] Failed to create venv. >> "%LOGFILE%"
    goto :END
  )
)

echo [INFO] Activating venv...
echo [INFO] Activating venv... >> "%LOGFILE%"
call "%VENV%\Scripts\activate.bat"
if errorlevel 1 (
  echo [ERROR] Failed to activate venv at: %VENV%
  echo [ERROR] Failed to activate venv at: %VENV% >> "%LOGFILE%"
  goto :END
)

echo.
echo [INSTALL] Offline install from wheels ...
echo [INSTALL] pip install --no-index --find-links "%WHEELS%" -r "%REQ%"
echo [INSTALL] Offline install from wheels ... >> "%LOGFILE%"
python -m pip install --no-index --find-links "%WHEELS%" -r "%REQ%" >> "%LOGFILE%" 2>&1
if errorlevel 1 (
  echo [WARN] Some packages may have failed to install. See log:
  echo        %LOGFILE%
  echo [WARN] pip install returned non-zero. >> "%LOGFILE%"
)

if not exist "%PROJ%\server_app.py" (
  echo [ERROR] server_app.py not found in %PROJ%
  echo [ERROR] server_app.py not found in %PROJ% >> "%LOGFILE%"
  goto :END
)

echo.
echo [RUN] Uvicorn starting at http://%HOST%:%PORT% ...
echo [RUN] uvicorn server_app:app --host %HOST% --port %PORT% >> "%LOGFILE%"
python -m uvicorn server_app:app --host %HOST% --port %PORT% >> "%LOGFILE%" 2>&1
set "RC=%ERRORLEVEL%"
echo [INFO] Uvicorn exited with code %RC% >> "%LOGFILE%"

echo.
if "%RC%" NEQ "0" (
  echo [WARN] Uvicorn exited with code %RC%
  echo [WARN] Check log: %LOGFILE%
) else (
  echo [OK] Uvicorn exited normally.
)

:END
echo.
echo (Window will stay open) Press any key to close...
pause >nul
endlocal
