@echo off

setlocal

chcp 65001 >nul



cd /d "%~dp0"



echo ========================================

echo V7ex Fullstack Starter - Auto IP

echo Root: %CD%

echo ========================================



set "BACKEND_PORT=8000"

set "PC_FRONTEND_PORT=3000"

set "MOBILE_FRONTEND_PORT=5174"



set /p BACKEND_PORT_INPUT=请输入后端端口，直接回车默认 %BACKEND_PORT%: 
if not "%BACKEND_PORT_INPUT%"=="" set "BACKEND_PORT=%BACKEND_PORT_INPUT%"

set /p PC_FRONTEND_PORT_INPUT=请输入 PC 前端端口，直接回车默认 %PC_FRONTEND_PORT%: 

if not "%PC_FRONTEND_PORT_INPUT%"=="" set "PC_FRONTEND_PORT=%PC_FRONTEND_PORT_INPUT%"

set /p MOBILE_FRONTEND_PORT_INPUT=请输入移动端前端端口，直接回车默认 %MOBILE_FRONTEND_PORT%: 

if not "%MOBILE_FRONTEND_PORT_INPUT%"=="" set "MOBILE_FRONTEND_PORT=%MOBILE_FRONTEND_PORT_INPUT%"



set "LAN_IP=127.0.0.1"

for /f "tokens=2 delims=:" %%A in ('ipconfig ^| findstr /C:"IPv4"') do (

  for /f "tokens=*" %%B in ("%%A") do (

    set "LAN_IP=%%B"

    goto :got_ip

  )

)

:got_ip



if not exist "%CD%\frontend" (

  echo [错误] 找不到 frontend 目录，请确认脚本位于 V7STD 根目录。

  pause

  exit /b 1

)



echo.

echo [依赖] 检查后端 Python 依赖...
py -3 -c "import fastapi, uvicorn, aiofiles, pandas, pymysql, jose" >nul 2>nul
if errorlevel 1 (
  echo 检测到后端依赖缺失，正在安装 requirements.txt...
  py -3 -m pip install -r "%CD%\requirements.txt"
  if errorlevel 1 (
    echo [错误] 后端依赖安装失败，请检查 Python/pip 或网络。
    pause
    exit /b 1
  )
)

echo 当前端口配置：

echo 后端端口:        %BACKEND_PORT%

echo PC 前端端口:     %PC_FRONTEND_PORT%

echo 移动端前端端口:  %MOBILE_FRONTEND_PORT%

echo.



echo [1/3] Starting backend on http://0.0.0.0:%BACKEND_PORT% ...

start "V7ex Backend (%BACKEND_PORT%)" cmd /k "cd /d %CD% && py -3 -m uvicorn api.main:app --reload --host 0.0.0.0 --port %BACKEND_PORT%"



echo [2/3] Starting frontend on http://0.0.0.0:%PC_FRONTEND_PORT% ...

start "V7ex Frontend (%PC_FRONTEND_PORT%)" cmd /k "cd /d %CD%\frontend && set VITE_API_BASE_URL=/api/v1&& set VITE_PROXY_TARGET=http://localhost:%BACKEND_PORT%&& npm run dev -- --host 0.0.0.0 --port %PC_FRONTEND_PORT%"



if exist "%CD%\frontend-mobile" (

  echo [3/3] Starting mobile frontend on http://0.0.0.0:%MOBILE_FRONTEND_PORT% ...

  start "V7ex Mobile Frontend (%MOBILE_FRONTEND_PORT%)" cmd /k "cd /d %CD%\frontend-mobile && npm run dev -- --host 0.0.0.0 --port %MOBILE_FRONTEND_PORT%"

) else (

  echo [3/3] frontend-mobile 不存在，跳过移动端启动。

)



echo.

echo Startup commands dispatched.

echo Local Frontend: http://127.0.0.1:%PC_FRONTEND_PORT%

echo Local Mobile  : http://127.0.0.1:%MOBILE_FRONTEND_PORT%

echo Local Backend : http://127.0.0.1:%BACKEND_PORT%

echo LAN Frontend  : http://%LAN_IP%:%PC_FRONTEND_PORT%

echo LAN Mobile    : http://%LAN_IP%:%MOBILE_FRONTEND_PORT%

echo LAN Backend   : http://%LAN_IP%:%BACKEND_PORT%

echo API Docs      : http://%LAN_IP%:%BACKEND_PORT%/docs

echo.

echo 说明：前端 API 使用 /api/v1 相对路径，并由 Vite 代理到 localhost:%BACKEND_PORT%。

echo 机器 IP 变化后，只需要重新运行本脚本即可。

echo PC 或移动端端口变化时，在本脚本启动提示中输入即可。

echo.

echo Press any key to exit this launcher window.

pause >nul



endlocal

