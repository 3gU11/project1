# 部署指南

## 生产拓扑

```text
HTTPS 443 -> Nginx -> frontend/dist
                    -> /api/      FastAPI:8000
                    -> /api/v1/photo-* /api/v1/sandbox/  Go:3001
                    -> /ws         FastAPI WebSocket
```

MySQL 只允许应用服务器内网访问。Go 和 FastAPI 使用同一时区（默认 `Asia/Shanghai`）。

## 构建

```powershell
cd frontend
npm ci
npm run build

cd ..\frontend-mobile
npm ci
npm run build

cd ..\server
go build -o server.exe ./cmd/main.go
```

FastAPI 可使用进程管理器运行：

```powershell
python -m uvicorn api.main:app --host 0.0.0.0 --port 8000 --workers 2
```

Go 容器构建：

```powershell
cd server
docker build -t v7-scheduling-server:local .
docker run --rm -p 3001:3001 --env-file .env v7-scheduling-server:local
```

## 发布顺序

1. 备份 MySQL、`data/contracts` 和 `machine_archives`。
2. 在预发布环境安装依赖并完成测试。
3. 构建前端和 Go 服务，核对 API 代理目标。
4. 停止旧进程，执行数据库迁移，再启动 Go 和 FastAPI。
5. 检查 `/health`、登录、库存查询、排产页面和 WebSocket。
6. 切换 Nginx 流量，观察错误日志和 Outbox 状态。

## 回滚

应用回滚必须同时考虑代码、数据库 schema 和归档文件。优先切回上一版本应用，再根据备份恢复数据库；不要只替换前端静态文件而忽略后端接口版本。
