@echo off
setlocal

cd /d "%~dp0\.."
python scripts/preflight_release.py %*

endlocal
