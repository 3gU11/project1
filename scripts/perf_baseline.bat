@echo off
setlocal

cd /d "%~dp0\.."
py -3 scripts/perf_baseline.py %*

endlocal
