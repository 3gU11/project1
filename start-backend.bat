@echo off
cd /d D:\CURSORpj\V8BetaV1.1
python -m uvicorn api.main:app --host 0.0.0.0 --port 8000 --reload
