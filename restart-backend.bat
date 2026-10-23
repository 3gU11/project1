@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo Restarting backend on http://localhost:8000 ...
echo (先结束占用 8000 端口的 python 进程，再启动)
python -m uvicorn api.main:app --host 0.0.0.0 --port 8000
