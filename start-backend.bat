@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo Starting backend on http://localhost:8000 ...
python -m uvicorn api.main:app --host 0.0.0.0 --port 8000
