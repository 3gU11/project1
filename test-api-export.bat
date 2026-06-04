@echo off
cd /d D:\CURSORpj\V8BetaV1.1
echo Testing completion report API...
python test_api_export.py
echo.
echo Check if test_api_export.xlsx was created
pause
