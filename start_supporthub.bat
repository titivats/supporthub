@echo off
setlocal

rem =====================================================================
rem  start_supporthub.bat  (OFFLINE / WHEELS-ONLY / STICKY CONSOLE)
rem    - Installs strictly from local wheels: E:\Data\Web\supporthub\wheels
rem    - Creates/activates venv
rem    - Runs Uvicorn in foreground
rem    - Always PAUSE at the end (window won't auto-close)
rem    - Writes daily launcher log to logs\launcher_YYYY-MM-DD.log
rem =====================================================================

set "PROJ=E:\Data\Web\supporthub"
set "REQ=%PROJ%\requirements.txt"
set "WHEELS=E:\Data\Web\supporthub\wheels"
set "VENV=%PROJ%\venv"
set "PYTHON_EXE=%VENV%\Scripts\python.exe"
set "HOST=127.0.0.1"
set "PORT=8888"
set "LOGDIR=%PROJ%\logs"
set "LOGDATE="
set "LOGFILE="
set "WEB_CONFIG=%PROJ%\web.config"

if not exist "%LOGDIR%" mkdir "%LOGDIR%"

for /f "usebackq delims=" %%A in (`powershell -NoProfile -ExecutionPolicy Bypass -Command "Get-Date -Format 'yyyy-MM-dd'"`) do (
  set "LOGDATE=%%A"
)
if not defined LOGDATE set "LOGDATE=%DATE%"
set "LOGFILE=%LOGDIR%\launcher_%LOGDATE%.log"
set "SUPPORTHUB_LOG_DIR=%LOGDIR%"

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

call :LOAD_OPTIONAL_SETTING SUPPORTHUB_MQTT_HOST
call :LOAD_OPTIONAL_SETTING SUPPORTHUB_MQTT_PORT
call :LOAD_OPTIONAL_SETTING SUPPORTHUB_MQTT_TOPIC
call :LOAD_OPTIONAL_SETTING SUPPORTHUB_MQTT_CLIENT_ID
call :LOAD_OPTIONAL_SETTING SUPPORTHUB_SECRET
call :LOAD_OPTIONAL_SETTING SUPPORTHUB_SECRET_FILE
call :LOAD_OPTIONAL_SETTING SUPPORTHUB_INSTALL_ON_START
call :LOAD_OPTIONAL_SETTING SUPPORTHUB_AUTO_RESTART
call :LOAD_OPTIONAL_SETTING SUPPORTHUB_RESTART_DELAY_SECONDS
call :LOAD_OPTIONAL_SETTING SUPPORTHUB_DB_POOL_SIZE
call :LOAD_OPTIONAL_SETTING SUPPORTHUB_DB_MAX_OVERFLOW
call :LOAD_OPTIONAL_SETTING SUPPORTHUB_DB_POOL_TIMEOUT
call :LOAD_OPTIONAL_SETTING SUPPORTHUB_DB_POOL_RECYCLE
call :LOAD_OPTIONAL_SETTING SUPPORTHUB_RUN_DB_MAINTENANCE_ON_STARTUP

if not defined SUPPORTHUB_SECRET_FILE set "SUPPORTHUB_SECRET_FILE=%PROJ%\secret_key"
if not defined SUPPORTHUB_INSTALL_ON_START set "SUPPORTHUB_INSTALL_ON_START=false"
if not defined SUPPORTHUB_AUTO_RESTART set "SUPPORTHUB_AUTO_RESTART=true"
if not defined SUPPORTHUB_RESTART_DELAY_SECONDS set "SUPPORTHUB_RESTART_DELAY_SECONDS=5"

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
if defined SUPPORTHUB_MQTT_HOST echo MQTT    : %SUPPORTHUB_MQTT_HOST%:%SUPPORTHUB_MQTT_PORT% Topic=%SUPPORTHUB_MQTT_TOPIC%
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

cd /d "%PROJ%"
if errorlevel 1 (
  echo [ERROR] Failed to change working directory to %PROJ%
  echo [ERROR] Failed to change working directory to %PROJ% >> "%LOGFILE%"
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

set "NEED_INSTALL=0"
if /I "%SUPPORTHUB_INSTALL_ON_START%"=="1" set "NEED_INSTALL=1"
if /I "%SUPPORTHUB_INSTALL_ON_START%"=="true" set "NEED_INSTALL=1"
if /I "%SUPPORTHUB_INSTALL_ON_START%"=="yes" set "NEED_INSTALL=1"
if /I "%SUPPORTHUB_INSTALL_ON_START%"=="on" set "NEED_INSTALL=1"

if "%NEED_INSTALL%"=="0" (
  "%PYTHON_EXE%" -c "import fastapi, uvicorn, jinja2, sqlalchemy, itsdangerous, multipart, xlsxwriter, psycopg, paho.mqtt.client" >nul 2>&1
  if errorlevel 1 set "NEED_INSTALL=1"
)

if "%NEED_INSTALL%"=="1" (
  call :RUN_PIP_INSTALL
  if errorlevel 1 goto :END
) else (
  echo [INFO] Skipping pip install. Existing venv dependencies look healthy.
  echo [INFO] Skipping pip install. Existing venv dependencies look healthy. >> "%LOGFILE%"
)

if not exist "%PYTHON_EXE%" (
  echo [ERROR] Python executable not found in venv: %PYTHON_EXE%
  echo [ERROR] Python executable not found in venv: %PYTHON_EXE% >> "%LOGFILE%"
  goto :END
)

"%PYTHON_EXE%" -c "import fastapi, uvicorn, jinja2, sqlalchemy, itsdangerous, multipart, xlsxwriter, psycopg, paho.mqtt.client" >nul 2>&1
if errorlevel 1 (
  echo [ERROR] One or more required Python packages are missing after venv setup.
  echo [ERROR] Check offline wheels and %LOGFILE%
  echo [ERROR] One or more required Python packages are missing after venv setup. >> "%LOGFILE%"
  goto :END
)

if not exist "%PROJ%\python\app.py" (
  echo [ERROR] python\app.py not found in %PROJ%
  echo [ERROR] python\app.py not found in %PROJ% >> "%LOGFILE%"
  goto :END
)

"%PYTHON_EXE%" -c "from python.app import app" >> "%LOGFILE%" 2>&1
if errorlevel 1 (
  echo [ERROR] Application import failed. Check log: %LOGFILE%
  echo [ERROR] Application import failed. >> "%LOGFILE%"
  goto :END
)

:RUN_SERVER
echo.
echo [RUN] Uvicorn starting at http://%HOST%:%PORT% ...
echo [RUN] uvicorn python.app:app --host %HOST% --port %PORT% --proxy-headers --no-access-log >> "%LOGFILE%"
"%PYTHON_EXE%" -m uvicorn python.app:app --host %HOST% --port %PORT% --proxy-headers --no-access-log >> "%LOGFILE%" 2>&1
set "RC=%ERRORLEVEL%"
echo [INFO] Uvicorn exited with code %RC% >> "%LOGFILE%"

echo.
if "%RC%" NEQ "0" (
  echo [WARN] Uvicorn exited with code %RC%
  echo [WARN] Check log: %LOGFILE%
  if /I "%SUPPORTHUB_AUTO_RESTART%"=="1" goto :RESTART_SERVER
  if /I "%SUPPORTHUB_AUTO_RESTART%"=="true" goto :RESTART_SERVER
  if /I "%SUPPORTHUB_AUTO_RESTART%"=="yes" goto :RESTART_SERVER
  if /I "%SUPPORTHUB_AUTO_RESTART%"=="on" goto :RESTART_SERVER
) else (
  echo [OK] Uvicorn exited normally.
)

goto :END

:RESTART_SERVER
echo [WARN] Restarting Uvicorn in %SUPPORTHUB_RESTART_DELAY_SECONDS% seconds...
echo [WARN] Restarting Uvicorn in %SUPPORTHUB_RESTART_DELAY_SECONDS% seconds... >> "%LOGFILE%"
timeout /t %SUPPORTHUB_RESTART_DELAY_SECONDS% /nobreak >nul
goto :RUN_SERVER

:END
echo.
echo (Window will stay open) Press any key to close...
pause >nul
endlocal
goto :EOF

:RUN_PIP_INSTALL
echo.
echo [INSTALL] Offline install from wheels ...
echo [INSTALL] pip install --no-index --find-links "%WHEELS%" -r "%REQ%"
echo [INSTALL] Offline install from wheels ... >> "%LOGFILE%"
"%PYTHON_EXE%" -m pip install --no-index --find-links "%WHEELS%" -r "%REQ%" >> "%LOGFILE%" 2>&1
if errorlevel 1 (
  echo [ERROR] Offline pip install failed. Check log: %LOGFILE%
  echo [ERROR] Offline pip install failed. >> "%LOGFILE%"
  exit /b 1
)
exit /b 0

:LOAD_OPTIONAL_SETTING
if defined %~1 goto :EOF
if not exist "%WEB_CONFIG%" goto :EOF
for /f "usebackq delims=" %%A in (`powershell -NoProfile -ExecutionPolicy Bypass -Command "$cfg=[xml](Get-Content -Raw '%WEB_CONFIG%'); $n=$cfg.SelectSingleNode('/configuration/appSettings/add[@key=''%~1'']'); if($n -and $n.value){$n.value}"`) do (
  set "%~1=%%A"
)
goto :EOF
