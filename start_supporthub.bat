@echo off
setlocal

rem =====================================================================
rem  start_supporthub.bat  (OFFLINE / WHEELS-ONLY / STICKY CONSOLE)
rem    - Installs strictly from local wheels: E:\Data\Web\supporthub\wheels
rem    - Creates/activates venv
rem    - Runs Uvicorn in foreground
rem    - Always PAUSE at the end (window won't auto-close)
rem    - Writes simple rolling log to logs\start_supporthub.log
rem =====================================================================

set "PROJ=E:\Data\Web\supporthub"
set "REQ=%PROJ%\requirements.txt"
set "WHEELS=E:\Data\Web\supporthub\wheels"
set "VENV=%PROJ%\venv"
set "HOST=127.0.0.1"
set "PORT=8888"
set "LOGDIR=%PROJ%\logs"
set "LOGFILE=%LOGDIR%\start_supporthub.log"
set "WEB_CONFIG=%PROJ%\web.config"

if not exist "%LOGDIR%" mkdir "%LOGDIR%"

echo.>> "%LOGFILE%"
echo ================== %DATE% %TIME% ================== >> "%LOGFILE%"
echo [INFO] Launcher started >> "%LOGFILE%"

if not defined SUPPORTHUB_DATABASE_URL (
  if exist "%WEB_CONFIG%" (
    for /f "usebackq delims=" %%A in (`powershell -NoProfile -ExecutionPolicy Bypass -Command "$cfg=[xml](Get-Content -Raw '%WEB_CONFIG%'); $n=$cfg.SelectSingleNode('/configuration/appSettings/add[@key=''SUPPORTHUB_DATABASE_URL'']'); if($n -and $n.value){$n.value}"`) do (
      set "SUPPORTHUB_DATABASE_URL=%%A"
    )
    if defined SUPPORTHUB_DATABASE_URL (
      echo [INFO] Loaded SUPPORTHUB_DATABASE_URL from web.config
      echo [INFO] Loaded SUPPORTHUB_DATABASE_URL from web.config >> "%LOGFILE%"
    )
  )
)

if not defined SUPPORTHUB_DATABASE_URL (
  echo [ERROR] SUPPORTHUB_DATABASE_URL was not found.
  echo [ERROR] Configure it in: %WEB_CONFIG%
  echo [ERROR] SUPPORTHUB_DATABASE_URL was not found. >> "%LOGFILE%"
  echo [ERROR] Configure it in: %WEB_CONFIG% >> "%LOGFILE%"
  goto :END
)

set "DB_MODE=PostgreSQL (required)"

set "URL_HEAD_A=%SUPPORTHUB_DATABASE_URL:~0,13%"
set "URL_HEAD_B=%SUPPORTHUB_DATABASE_URL:~0,21%"
if /I not "%URL_HEAD_A%"=="postgresql://" (
  if /I not "%URL_HEAD_B%"=="postgresql+psycopg://" (
    echo [ERROR] SUPPORTHUB_DATABASE_URL must start with postgresql:// or postgresql+psycopg://
    echo [ERROR] Current value is invalid for PostgreSQL-only mode.
    echo [ERROR] SUPPORTHUB_DATABASE_URL must start with postgresql:// or postgresql+psycopg:// >> "%LOGFILE%"
    echo [ERROR] Current value is invalid for PostgreSQL-only mode. >> "%LOGFILE%"
    goto :END
  )
)

echo %SUPPORTHUB_DATABASE_URL% | find /I "CHANGE_ME_PASSWORD" >nul
if not errorlevel 1 (
  echo [ERROR] SUPPORTHUB_DATABASE_URL still contains CHANGE_ME_PASSWORD.
  echo [ERROR] Update database password in: %WEB_CONFIG%
  echo [ERROR] SUPPORTHUB_DATABASE_URL contains CHANGE_ME_PASSWORD. >> "%LOGFILE%"
  goto :END
)

echo.
echo === SupportHub OFFLINE start (wheels only) ===
echo Project : %PROJ%
echo Wheels  : %WHEELS%
echo Venv    : %VENV%
echo Req     : %REQ%
echo Host:Port -> %HOST%:%PORT%
echo Database: %DB_MODE%
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

python -c "import psycopg" >nul 2>&1
if errorlevel 1 (
  echo [ERROR] psycopg is missing for PostgreSQL connection.
  echo [ERROR] Install psycopg or add psycopg wheels into: %WHEELS%
  echo [ERROR] psycopg is missing for PostgreSQL connection. >> "%LOGFILE%"
  goto :END
)

if not exist "%PROJ%\python\server_app.py" (
  echo [ERROR] python\server_app.py not found in %PROJ%
  echo [ERROR] python\server_app.py not found in %PROJ% >> "%LOGFILE%"
  goto :END
)

echo.
echo [RUN] Uvicorn starting at http://%HOST%:%PORT% ...
echo [RUN] uvicorn python.server_app:app --host %HOST% --port %PORT% >> "%LOGFILE%"
python -m uvicorn python.server_app:app --host %HOST% --port %PORT% >> "%LOGFILE%" 2>&1
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
