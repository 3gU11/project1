@echo off
setlocal

cd /d "%~dp0"

REM 默认执行发布前预检 + 连通性闭环检查（严格模式）
py -3 scripts\preflight_release.py --run-connectivity --connectivity-strict %*

endlocal

