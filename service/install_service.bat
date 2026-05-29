@echo off
setlocal
REM Install SupportHub as Windows service (Administrator + NSSM)

set "SERVICE_NAME=SupportHub"
set "ROOT=%~dp0.."
if "%ROOT:~-1%"=="\" set "ROOT=%ROOT:~0,-1%"
set "PY=%ROOT%\venv\Scripts\python.exe"
set "LOGDIR=%ROOT%\logs"
set "APP_PARAMS=-m uvicorn python.server_app:app --host 127.0.0.1 --port 8888"

set "NSSM=nssm"
where nssm >nul 2>&1
if errorlevel 1 (
  if exist "%~dp0nssm.exe" (
    set "NSSM=%~dp0nssm.exe"
  ) else (
    echo [ERROR] nssm.exe not found. Copy to: %~dp0nssm.exe
    goto :END
  )
)

if not exist "%ROOT%\.env" (
  echo [ERROR] .env not found: %ROOT%\.env
  goto :END
)
if not exist "%PY%" (
  echo [ERROR] venv not found: %PY%
  goto :END
)
if not exist "%LOGDIR%" mkdir "%LOGDIR%"

echo Installing "%SERVICE_NAME%" ...
echo Python  : %PY%
echo Work dir: %ROOT%

"%NSSM%" stop "%SERVICE_NAME%" >nul 2>&1
"%NSSM%" remove "%SERVICE_NAME%" confirm >nul 2>&1

"%NSSM%" install "%SERVICE_NAME%" "%PY%" %APP_PARAMS%
if errorlevel 1 goto :FAIL

"%NSSM%" set "%SERVICE_NAME%" AppDirectory "%ROOT%"
"%NSSM%" set "%SERVICE_NAME%" DisplayName "SupportHub"
"%NSSM%" set "%SERVICE_NAME%" Description "ME SupportHub - FastAPI"
"%NSSM%" set "%SERVICE_NAME%" Start SERVICE_AUTO_START
"%NSSM%" set "%SERVICE_NAME%" AppStdout "%LOGDIR%\service_stdout.log"
"%NSSM%" set "%SERVICE_NAME%" AppStderr "%LOGDIR%\service_stderr.log"
"%NSSM%" set "%SERVICE_NAME%" AppRotateFiles 1
"%NSSM%" set "%SERVICE_NAME%" AppRotateBytes 10485760

"%NSSM%" start "%SERVICE_NAME%"
echo [OK] Service started. Logs: %LOGDIR%
sc query "%SERVICE_NAME%"
goto :END

:FAIL
echo [ERROR] Install failed. Run as Administrator.

:END
pause
endlocal
