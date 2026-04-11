@echo off
setlocal

cd /d "%~dp0"

echo ========================================
echo V7ex Fullstack Starter
echo Root: %CD%
echo ========================================

set LAN_IP=172.21.8.43

echo [1/3] Starting backend on http://0.0.0.0:8000 ...
start "V7ex Backend (8000)" cmd /k "cd /d %CD% && py -3 -m uvicorn api.main:app --reload --host 0.0.0.0 --port 8000"

echo [2/3] Starting frontend on http://0.0.0.0:3000 ...
start "V7ex Frontend (3000)" cmd /k "cd /d %CD%\frontend && npm run dev -- --host 0.0.0.0 --port 3000"

echo [3/3] Starting mobile frontend on http://0.0.0.0:5174 ...
start "V7ex Mobile Frontend (5174)" cmd /k "cd /d %CD%\frontend-mobile && npm run dev -- --host 0.0.0.0 --port 5174"

echo.
echo Startup commands dispatched.
echo Local Frontend: http://127.0.0.1:3000
echo Local Mobile  : http://127.0.0.1:5174
echo Local Backend : http://127.0.0.1:8000
echo LAN Frontend  : http://%LAN_IP%:3000
echo LAN Mobile    : http://%LAN_IP%:5174
echo LAN Backend   : http://%LAN_IP%:8000
echo API Docs      : http://%LAN_IP%:8000/docs
echo.
echo Press any key to exit this launcher window.
pause >nul

endlocal
