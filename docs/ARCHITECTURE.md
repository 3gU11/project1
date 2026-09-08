# 系统架构

## 组件关系

```text
浏览器 / PDA
   |  HTTP + WebSocket
   v
Vue PC (3000) / Vue Mobile (Vite)
   | /api 代理
   v
FastAPI (8000) ---- MySQL 8.0
   | 内部 HTTP + X-Internal-Token
   v
Go 调度与照片服务 (3001)
   |
   +---- 微信云托管 API（可选）
   +---- 维修系统快照 API（可选）
```

## 后端职责

### FastAPI

入口为 `api.main:app`。它负责认证、权限、业务事务、数据库读写、文件归档、报表导出、WebSocket 广播和云端 Outbox 同步。启动时会检查数据库 schema 版本，当前代码中的 `CURRENT_SCHEMA_VERSION` 为 14。

### Go 服务

`server/cmd/main.go` 是 Go 服务入口，默认监听 3001。服务承担高并发排产重算、沙盘预测、急单插入、机台交换、照片相关接口和 WebSocket 实时能力。FastAPI 调用内部接口时必须配置同一份 `GO_INTERNAL_TOKEN`。

## 前端代理

PC 前端默认监听 3000。`frontend/vite.config.ts` 将 `/api` 代理到 `VITE_PROXY_TARGET`（默认 `http://localhost:8000`），照片和 Go 相关路径代理到 `VITE_PHOTO_API_TARGET`（默认 `http://localhost:3001`）。生产环境应由 Nginx 或网关统一转发。

## 主要路由前缀

| 前缀 | 领域 |
| --- | --- |
| `/api/v1/auth` | 登录 |
| `/api/v1/inventory` | 库存、入库、发货、机台档案 |
| `/api/v1/planning` | 合同、排产、配货、导出 |
| `/api/v1/sandbox` | Go 沙盘代理 |
| `/api/v1/dealer-orders` | 经销商订单和云端同步 |
| `/api/v1/reports` | 报表 |
| `/api/v1/traceability` | 追溯 |
| `/api/v1/users`、`/api/v1/roles` | 用户和权限 |
| `/api/v1/logs` | 业务与审计日志 |

## 数据一致性原则

- 配货、撤回配货、发货确认等写操作必须走后端事务和原生 SQL 锁。
- `cloud_sync_outbox` 负责云端状态异步重试和幂等。
- `inbound_history` 是入库历史事件表，不等同于当前库存快照。
- 异常处理必须保留审计日志和数据库备份。
