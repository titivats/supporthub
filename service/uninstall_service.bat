@echo off
setlocal
REM Remove SupportHub Windows service (requires Administrator + NSSM)

set "SERVICE_NAME=SupportHub"
set "NSSM=nssm"
where nssm >nul 2>&1
if errorlevel 1 (
  if exist "%~dp0nssm.exe" (
    set "NSSM=%~dp0nssm.exe"
  ) else (
    echo [ERROR] nssm.exe not found.
    goto :END
  )
)

echo Stopping and removing "%SERVICE_NAME%" ...
"%NSSM%" stop "%SERVICE_NAME%"
"%NSSM%" remove "%SERVICE_NAME%" confirm
echo [OK] Done.

:END
pause
endlocal
