@echo off
setlocal
cd /d "%~dp0.."
if exist ".venv\Scripts\python.exe" (
  ".venv\Scripts\python.exe" -m repair_sync daily %*
) else (
  python -m repair_sync daily %*
)
exit /b %ERRORLEVEL%
