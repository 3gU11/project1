@echo off
cd /d "%~dp0"
".venv\Scripts\python.exe" scripts\run_demo.py --lan
pause
