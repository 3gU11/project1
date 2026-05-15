@echo off
title Batch Sync Tool Launcher
echo Starting the tool...
cd /d %~dp0

if exist .venv\Scripts\python.exe (
    echo Using Virtual Environment...
    .venv\Scripts\python.exe -m streamlit run scripts/sync_batch_app.py
) else (
    echo Using System Python...
    python -m streamlit run scripts/sync_batch_app.py
)

if %ERRORLEVEL% neq 0 (
    echo.
    echo [ERROR] Failed to start. 
    echo Please ensure streamlit and pymysql are installed.
)

pause
