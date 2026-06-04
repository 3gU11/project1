@echo off
cd /d D:\CURSORpj\V8BetaV1.1
echo Testing Excel export with category summary...
python test_excel_full.py
echo.
echo Check if test_completion_report.xlsx was created
pause
