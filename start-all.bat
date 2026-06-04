@echo off
echo Starting Backend and Frontend...
echo.

echo [1/2] Starting Backend Server...
start "Backend Server" cmd /k "cd /d D:\CURSORpj\V8BetaV1.1 && python -m uvicorn api.main:app --host 0.0.0.0 --port 8000 --reload"

timeout /t 3 /nobreak >nul

echo [2/2] Starting Frontend Server...
start "Frontend Server" cmd /k "cd /d D:\CURSORpj\V8BetaV1.1\frontend && npm run dev"

echo.
echo Both servers are starting...
echo Backend: http://localhost:8000
echo Frontend: http://localhost:3000
echo.
pause
