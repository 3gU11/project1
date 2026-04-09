@echo off
setlocal

REM Example only: adjust paths before use.
set NSSM_EXE=C:\tools\nssm\nssm.exe
set SERVICE_NAME=V7exBackend
set APP_DIR=D:\trae_projects\V7改\V7ex
set PYTHON_EXE=C:\Python310\python.exe

REM Install service
"%NSSM_EXE%" install "%SERVICE_NAME%" "%PYTHON_EXE%" "run_api.py"
"%NSSM_EXE%" set "%SERVICE_NAME%" AppDirectory "%APP_DIR%"
"%NSSM_EXE%" set "%SERVICE_NAME%" AppEnvironmentExtra UVICORN_HOST=0.0.0.0
"%NSSM_EXE%" set "%SERVICE_NAME%" AppEnvironmentExtra UVICORN_PORT=8000
"%NSSM_EXE%" set "%SERVICE_NAME%" AppEnvironmentExtra UVICORN_RELOAD=false
"%NSSM_EXE%" set "%SERVICE_NAME%" AppEnvironmentExtra UVICORN_LOG_LEVEL=info
"%NSSM_EXE%" set "%SERVICE_NAME%" AppEnvironmentExtra UVICORN_WORKERS=2

REM Optional logs
"%NSSM_EXE%" set "%SERVICE_NAME%" AppStdout "%APP_DIR%\logs\backend.out.log"
"%NSSM_EXE%" set "%SERVICE_NAME%" AppStderr "%APP_DIR%\logs\backend.err.log"

REM Start service
"%NSSM_EXE%" start "%SERVICE_NAME%"

echo NSSM example commands executed. Verify service status in services.msc.
endlocal
