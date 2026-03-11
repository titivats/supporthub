@echo off
setlocal

rem ============================================================
rem  backup_postgres.bat
rem    - Read SUPPORTHUB_DATABASE_URL from web.config
rem    - Dump current PostgreSQL database (schema + data) to backup\postgres\*.backup
rem    - Keep backup files for KEEP_DAYS
rem ============================================================

set "PROJ=E:\Data\Web\supporthub"
set "WEB_CONFIG=%PROJ%\web.config"
set "BACKUP_DIR=%PROJ%\backup\postgres"
set "KEEP_DAYS=14"

if not exist "%BACKUP_DIR%" mkdir "%BACKUP_DIR%"

for /f "usebackq delims=" %%A in (`powershell -NoProfile -ExecutionPolicy Bypass -Command "$cfg=[xml](Get-Content -Raw '%WEB_CONFIG%'); $n=$cfg.SelectSingleNode('/configuration/appSettings/add[@key=''SUPPORTHUB_DATABASE_URL'']'); if($n -and $n.value){$n.value}"`) do (
  set "SUPPORTHUB_DATABASE_URL=%%A"
)

if not defined SUPPORTHUB_DATABASE_URL (
  echo [ERROR] SUPPORTHUB_DATABASE_URL was not found in web.config
  goto :END
)

set "URL_HEAD_A=%SUPPORTHUB_DATABASE_URL:~0,13%"
set "URL_HEAD_B=%SUPPORTHUB_DATABASE_URL:~0,21%"
if /I not "%URL_HEAD_A%"=="postgresql://" (
  if /I not "%URL_HEAD_B%"=="postgresql+psycopg://" (
    echo [ERROR] SUPPORTHUB_DATABASE_URL must start with postgresql:// or postgresql+psycopg://
    goto :END
  )
)

echo %SUPPORTHUB_DATABASE_URL% | find /I "CHANGE_ME_PASSWORD" >nul
if not errorlevel 1 (
  echo [ERROR] SUPPORTHUB_DATABASE_URL still contains CHANGE_ME_PASSWORD.
  echo [ERROR] Update database password in web.config before backup.
  goto :END
)

set "PG_DUMP_URL=%SUPPORTHUB_DATABASE_URL:postgresql+psycopg://=postgresql://%"
set "PG_BIN_DEFAULT=C:\Program Files\PostgreSQL\18\bin"

pg_dump --version >nul 2>&1
if errorlevel 1 (
  if exist "%PG_BIN_DEFAULT%\pg_dump.exe" (
    set "PATH=%PG_BIN_DEFAULT%;%PATH%"
  )
)

pg_dump --version >nul 2>&1
if errorlevel 1 (
  echo [ERROR] pg_dump was not found in PATH.
  echo [HINT] Add PostgreSQL bin folder to PATH, e.g. C:\Program Files\PostgreSQL\18\bin
  goto :END
)

for /f %%A in ('powershell -NoProfile -Command "(Get-Date).ToString('dd_MM_yyyy')"') do set "TS=%%A"
set "OUT_FILE=%BACKUP_DIR%\%TS%-db.backup"

echo [RUN] Backing up PostgreSQL to:
echo       %OUT_FILE%

pg_dump --dbname="%PG_DUMP_URL%" --format=custom --blobs --encoding=UTF8 --no-owner --no-privileges --file="%OUT_FILE%"
if errorlevel 1 (
  echo [ERROR] Backup failed.
  goto :END
)

echo [OK] Backup created.

powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "Get-ChildItem -Path '%BACKUP_DIR%' -Filter '*.backup' | Where-Object { $_.LastWriteTime -lt (Get-Date).AddDays(-%KEEP_DAYS%) } | Remove-Item -Force -ErrorAction SilentlyContinue"

echo [OK] Cleanup old backups older than %KEEP_DAYS% days completed.

:END
echo.
echo Press any key to close...
pause >nul
endlocal
