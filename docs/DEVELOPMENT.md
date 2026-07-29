# 开发与启动

## 环境要求

- Windows 11 或 Linux；Python 3.12+（建议使用虚拟环境）。
- Node.js 20+、npm；Go 1.22（`server/Dockerfile` 使用 Go 1.22）。
- MySQL 8.0，数据库名默认 `rjfinshed`。

## 安装依赖

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt

cd frontend
npm ci
cd ..

cd frontend-mobile
npm ci
cd ..

cd server
go mod download
cd ..
```

## 环境变量

复制 `.env.backend.example` 为本地 `.env`，填写 MySQL、管理员密码和可选云端配置。不要把真实 `.env` 提交到 Git。

| 变量 | 默认/示例 | 说明 |
| --- | --- | --- |
| `MYSQL_HOST`、`MYSQL_PORT` | `localhost`、`3306` | MySQL 地址 |
| `MYSQL_USER`、`MYSQL_PASSWORD`、`MYSQL_DB` | `root`、自定义、`rjfinshed` | 数据库连接 |
| `ADMIN_PASSWORD` | 必填生产密码 | 首次管理员初始化 |
| `GO_SANDBOX_URL` | `http://127.0.0.1:3001` | Go 服务地址 |
| `GO_INTERNAL_TOKEN` | 随机长字符串 | Python/Go 内部鉴权 |
| `WECHAT_CLOUD_API_BASE`、`V7_API_KEY` | 可选 | 微信云托管同步 |
| `REPAIR_SYNC_*` | 可选 | 维修系统快照同步 |
| `UVICORN_HOST`、`UVICORN_PORT` | `0.0.0.0`、`8000` | FastAPI 监听 |
| `VITE_PROXY_TARGET` | `http://localhost:8000` | PC 开发代理 |
| `VITE_PHOTO_API_TARGET` | `http://localhost:3001` | Go/照片代理 |

## 启动服务

### 分别启动

```powershell
# 终端 1：FastAPI
python -m uvicorn api.main:app --host 0.0.0.0 --port 8000 --reload

# 终端 2：Go 服务
cd server
go run ./cmd/main.go

# 终端 3：PC 前端
cd frontend
npm run dev

# 终端 4：移动端（可选）
cd frontend-mobile
npm run dev
```

访问 `http://localhost:3000`，健康检查为 `http://localhost:8000/health`，OpenAPI 为 `http://localhost:8000/docs`。

### Windows 一键启动

在项目根目录运行 `run_fullstack.bat`，脚本会调用 `run_fullstack.ps1`。旧的 `start-*.bat` 可能包含历史绝对路径，若路径不一致请优先使用一键脚本或手动启动。

## 初始化与数据导入

1. 创建空数据库并授予应用账号最小权限。
2. 按需导入 `rjfinshed.sql`；生产导入前必须确认备份和字符集。
3. 启动 FastAPI，让 schema 版本检查完成。
4. 使用登录接口确认管理员，再导入机型字典、合同和库存数据。

## 代码约定

- Python API 放在 `api/routes`，数据库读写放在 `crud`，共享配置在 `config.py`。
- Vue 页面放在 `frontend/src/views`，通用组件放在 `frontend/src/components`。
- Go handler、service、repo 和 engine 按 `server/internal` 分层。
- 业务状态变更必须有测试或可复现的手工验证记录。
