@echo off
REM Apply SupportHub schema to PostgreSQL.
REM Edit values below if your connection changes.

setlocal
set PGHOST=192.168.1.19
set PGPORT=5432
set PGUSER=postgres
set PGPASSWORD=medeveloper
set PGDATABASE=supporthub

set SCRIPT_DIR=%~dp0

echo Creating database "%PGDATABASE%" (ignored if it already exists)...
psql -h %PGHOST% -p %PGPORT% -U %PGUSER% -d postgres -tc "SELECT 1 FROM pg_database WHERE datname='%PGDATABASE%'" | findstr "1" >nul
if errorlevel 1 (
    psql -h %PGHOST% -p %PGPORT% -U %PGUSER% -d postgres -c "CREATE DATABASE %PGDATABASE%"
)

echo Applying schema files...
psql -h %PGHOST% -p %PGPORT% -U %PGUSER% -d %PGDATABASE% -v ON_ERROR_STOP=1 -f "%SCRIPT_DIR%01_core_tables.sql"
if errorlevel 1 goto :error
psql -h %PGHOST% -p %PGPORT% -U %PGUSER% -d %PGDATABASE% -v ON_ERROR_STOP=1 -f "%SCRIPT_DIR%02_iot_tables.sql"
if errorlevel 1 goto :error
psql -h %PGHOST% -p %PGPORT% -U %PGUSER% -d %PGDATABASE% -v ON_ERROR_STOP=1 -f "%SCRIPT_DIR%03_history_view.sql"
if errorlevel 1 goto :error

echo Done.
endlocal
exit /b 0

:error
echo Schema apply failed.
endlocal
exit /b 1
