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

## 前端发布包与版本校验

反复出现"本地是新的、公司机器上还是旧的"，多半是发布包来源不对或浏览器缓存。发布时按下述方式做，可当场确认线上跑的是哪一版：

```powershell
cd frontend
npx vite build --outDir dist_release_<日期>   # 每次用新目录，避免旧 chunk 堆积
```

1. 发布包必须是**整目录替换**，不要只覆盖 `index.html` 或只拷 `assets` 里的新文件。旧 chunk 残留不会报错，但会让"到底加载了哪一版"无法判断。
2. 构建完成后写入版本标记 `dist_release_<日期>/version.json`（构建时间、git commit、入口 chunk、本期要点），随包一起发布。
3. 上线后访问 `https://<站点>/version.json`，核对 `build_time` 和 `entry_chunk` 与发布包一致。
4. 页面仍显示旧内容时，先在浏览器 F12 → Network 确认 `index-*.js` 的哈希是否为新值；不一致就是 Nginx 指向了旧目录或浏览器/代理缓存，与代码无关。
5. `frontend/dist` 是本地默认输出目录，多次构建会累积历史 chunk（可能膨胀到数百个文件）。对外发布建议用独立的 `dist_release_*` 目录，`dist` 只作为本地调试产物。

## 回滚

应用回滚必须同时考虑代码、数据库 schema 和归档文件。优先切回上一版本应用，再根据备份恢复数据库；不要只替换前端静态文件而忽略后端接口版本。
