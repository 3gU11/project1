@echo off
setlocal

cd /d "%~dp0\.."
py -3 scripts\connectivity_e2e_runner.py %*

endlocal

