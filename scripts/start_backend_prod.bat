@echo off
setlocal

cd /d "%~dp0\.."

echo ========================================
echo V7ex Backend Starter (Production Mode)
echo Root: %CD%
echo ========================================

if exist ".env" (
  echo Loading variables from .env ...
  for /f "usebackq tokens=1,* delims==" %%A in (`findstr /R "^[A-Za-z_][A-Za-z0-9_]*=" ".env"`) do (
    set "%%A=%%B"
  )
) else (
  echo .env not found, using default runtime values.
)

if "%UVICORN_HOST%"=="" set "UVICORN_HOST=0.0.0.0"
if "%UVICORN_PORT%"=="" set "UVICORN_PORT=8000"
if "%UVICORN_RELOAD%"=="" set "UVICORN_RELOAD=false"

echo Starting backend at http://%UVICORN_HOST%:%UVICORN_PORT% (reload=%UVICORN_RELOAD%)
echo Press Ctrl+C to stop.
python run_api.py

endlocal
