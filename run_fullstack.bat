@echo off
setlocal EnableExtensions
chcp 65001 >nul

cd /d "%~dp0"
if not exist ".\run_fullstack.ps1" (
  echo [ERROR] Missing .\run_fullstack.ps1
  pause
  exit /b 1
)

powershell -NoProfile -ExecutionPolicy Bypass -File ".\run_fullstack.ps1" %*
set "CODE=%ERRORLEVEL%"
if not "%CODE%"=="0" pause
exit /b %CODE%
