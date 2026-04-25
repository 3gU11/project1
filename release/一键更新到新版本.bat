@echo off
setlocal
chcp 65001 >nul

set "ROOT=D:\CURSORpj"
set "DEFAULT_OLD_DIR=%ROOT%\V7OLD"
set "DEFAULT_NEW_DIR=%ROOT%\V7STD"
set "DEFAULT_BACKUP_ROOT=%ROOT%\backup"
set "OLD_DIR=%DEFAULT_OLD_DIR%"
set "NEW_DIR=%DEFAULT_NEW_DIR%"
set "BACKUP_ROOT=%DEFAULT_BACKUP_ROOT%"
set "STAMP=%DATE:~0,4%%DATE:~5,2%%DATE:~8,2%_%TIME:~0,2%%TIME:~3,2%%TIME:~6,2%"
set "STAMP=%STAMP: =0%"

echo ========================================
echo V7OLD -^> V7STD 一键更新
echo ========================================
set /p OLD_DIR_INPUT=请输入老系统目录，直接回车默认 %DEFAULT_OLD_DIR%: 
if not "%OLD_DIR_INPUT%"=="" set "OLD_DIR=%OLD_DIR_INPUT%"
set /p NEW_DIR_INPUT=请输入新系统目录，直接回车默认 %DEFAULT_NEW_DIR%: 
if not "%NEW_DIR_INPUT%"=="" set "NEW_DIR=%NEW_DIR_INPUT%"
set /p BACKUP_ROOT_INPUT=请输入备份目录，直接回车默认 %DEFAULT_BACKUP_ROOT%: 
if not "%BACKUP_ROOT_INPUT%"=="" set "BACKUP_ROOT=%BACKUP_ROOT_INPUT%"
set "BACKUP_DIR=%BACKUP_ROOT%\V7OLD_before_update_%STAMP%"
echo.
echo 老版本目录: %OLD_DIR%
echo 新版本目录: %NEW_DIR%
echo 备份目录:   %BACKUP_DIR%
echo.
set /p MYSQL_DB_INPUT=请输入正式机数据库名，直接回车默认 rjfinshed: 
if "%MYSQL_DB_INPUT%"=="" set "MYSQL_DB_INPUT=rjfinshed"
echo 当前数据库: %MYSQL_DB_INPUT%
echo.

if not exist "%OLD_DIR%" (
  echo [错误] 找不到老版本目录: %OLD_DIR%
  pause
  exit /b 1
)

if not exist "%NEW_DIR%" (
  echo [错误] 找不到新版本目录: %NEW_DIR%
  pause
  exit /b 1
)

echo [1/8] 停止可能正在运行的旧/新服务...
for %%P in (8502 8000 3000 5174) do (
  for /f "tokens=5" %%A in ('netstat -ano ^| findstr ":%%P" ^| findstr "LISTENING"') do (
    echo 结束端口 %%P 进程 %%A
    taskkill /F /PID %%A >nul 2>nul
  )
)

echo [2/8] 备份老版本目录...
if not exist "%BACKUP_ROOT%" mkdir "%BACKUP_ROOT%"
robocopy "%OLD_DIR%" "%BACKUP_DIR%" /E /XD node_modules .git __pycache__ .venv venv >nul
if errorlevel 8 (
  echo [错误] 备份失败
  pause
  exit /b 1
)

echo [3/8] 备份数据库，如 mysqldump 不存在则跳过...
where mysqldump >nul 2>nul
if %errorlevel%==0 (
  mysqldump -h localhost -P 3306 -u root -p123456 --single-transaction --routines --triggers "%MYSQL_DB_INPUT%" > "%BACKUP_ROOT%\%MYSQL_DB_INPUT%_before_update_%STAMP%.sql" 2>nul
  if errorlevel 1 (
    echo root/123456 备份失败，尝试 root/030705...
    mysqldump -h localhost -P 3306 -u root -p030705 --single-transaction --routines --triggers "%MYSQL_DB_INPUT%" > "%BACKUP_ROOT%\%MYSQL_DB_INPUT%_before_update_%STAMP%.sql" 2>nul
  )
  if errorlevel 1 (
    echo [警告] 数据库自动备份失败，已继续执行。请确认你已有数据库备份。
  ) else (
    echo 数据库备份完成: %BACKUP_ROOT%\%MYSQL_DB_INPUT%_before_update_%STAMP%.sql
  )
) else (
  echo [警告] 未找到 mysqldump，跳过数据库备份。
)

echo [4/8] 合并老版本附件到新版本...
if exist "%OLD_DIR%\data\contracts" robocopy "%OLD_DIR%\data\contracts" "%NEW_DIR%\data\contracts" /E >nul
if exist "%OLD_DIR%\machine_archives" robocopy "%OLD_DIR%\machine_archives" "%NEW_DIR%\machine_archives" /E >nul
if exist "%OLD_DIR%\shipping_history" robocopy "%OLD_DIR%\shipping_history" "%NEW_DIR%\shipping_history" /E >nul

echo [5/8] 写入新版本环境配置...
(
  echo UVICORN_HOST=0.0.0.0
  echo UVICORN_PORT=8000
  echo UVICORN_RELOAD=true
  echo UVICORN_LOG_LEVEL=info
  echo UVICORN_WORKERS=1
  echo ADMIN_PASSWORD=888
  echo MYSQL_HOST=localhost
  echo MYSQL_PORT=3306
  echo MYSQL_USER=root
  echo MYSQL_PASSWORD=030705
  echo MYSQL_DB=%MYSQL_DB_INPUT%
  echo PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK=True
) > "%NEW_DIR%\.env"

echo [6/8] 初始化/升级数据库表...
cd /d "%NEW_DIR%"
set MYSQL_HOST=localhost
set MYSQL_PORT=3306
set MYSQL_USER=root
set MYSQL_PASSWORD=030705
set MYSQL_DB=%MYSQL_DB_INPUT%
py -3 -c "from database import init_mysql_tables; init_mysql_tables(); print('database ok')"
if errorlevel 1 (
  echo [警告] 使用 MYSQL_PASSWORD=030705 初始化失败，尝试 MYSQL_PASSWORD=123456...
  powershell -NoProfile -ExecutionPolicy Bypass -Command "(Get-Content '%NEW_DIR%\.env') -replace 'MYSQL_PASSWORD=030705','MYSQL_PASSWORD=123456' | Set-Content '%NEW_DIR%\.env' -Encoding UTF8"
  set MYSQL_PASSWORD=123456
  py -3 -c "from database import init_mysql_tables; init_mysql_tables(); print('database ok')"
  if errorlevel 1 (
    echo [错误] 数据库初始化失败，请检查 MySQL 密码。
    pause
    exit /b 1
  )
)

echo [7/8] 安装/检查前端依赖...
cd /d "%NEW_DIR%\frontend"
if not exist node_modules (
  npm install
  if errorlevel 1 (
    echo [错误] npm install 失败
    pause
    exit /b 1
  )
)

echo [8/8] 启动新版本...
cd /d "%NEW_DIR%"
start "V7STD Backend 8000" cmd /k "cd /d %NEW_DIR% && py -3 -m uvicorn api.main:app --reload --host 0.0.0.0 --port 8000"
start "V7STD Frontend 3000" cmd /k "cd /d %NEW_DIR%\frontend && npm run dev -- --host 0.0.0.0 --port 3000"
if exist "%NEW_DIR%\frontend-mobile" start "V7STD Mobile 5174" cmd /k "cd /d %NEW_DIR%\frontend-mobile && npm run dev -- --host 0.0.0.0 --port 5174"

echo.
echo ========================================
echo 更新完成
echo ========================================
echo 老版本已备份到: %BACKUP_DIR%
echo 新版电脑访问:   http://127.0.0.1:3000
echo 新版局域网访问: http://172.21.8.43:3000
echo 后端文档:       http://172.21.8.43:8000/docs
echo.
echo 如果要回滚：关闭新版本窗口，然后运行老版本备份目录中的 run_app.bat
echo %BACKUP_DIR%\run_app.bat
echo.
pause
endlocal
