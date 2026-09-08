# 接口目录

FastAPI 根地址默认为 `http://localhost:8000`。除登录、健康检查和少数公开接口外，路由需要登录令牌；部分写接口还需要角色权限。完整请求/响应模型以运行中的 OpenAPI 为准：`GET /docs` 或 `GET /openapi.json`。

## 鉴权

```http
POST /api/v1/auth/login
Content-Type: application/json

{"username":"admin","password":"<password>"}
```

登录成功后，将 token 放入 `Authorization: Bearer <token>`。服务内部调用 Go 时还需要 `X-Internal-Token`，该令牌不能下发给浏览器。

## 路由分组

| 前缀 | 常用接口 | 说明 |
| --- | --- | --- |
| `/health` | `GET /health` | 服务存活检查 |
| `/api/v1/auth` | `POST /login` | 登录 |
| `/api/v1/inventory` | `GET /`、`POST /`、`POST /shipping/confirm` | 库存、入库、发货 |
| `/api/v1/planning` | `GET /orders`、`POST /orders/{id}/allocate`、`GET /export-production-history` | 合同、排产、配货、报表 |
| `/api/v1/dealer-orders` | `GET /`、`POST /{order_no}/approve`、`POST /{order_no}/convert-to-contract` | 经销商订单闭环 |
| `/api/v1/reports` | `GET /inbound`、`/orders`、`/shipments`、`/completions` | 报表查询 |
| `/api/v1/traceability` | `GET /search`、`GET /{target_id}/timeline` | 追溯和时间线 |
| `/api/v1/model-dictionary` | `GET /`、`POST /save` | 机型字典 |
| `/api/v1/logs` | `GET /transactions`、`GET /audit` | 日志和审计 |
| `/api/v1/sandbox` | 预测、重算、急单和机台操作代理 | Go 沙盘能力 |

## WebSocket

FastAPI 的 WebSocket 用于广播订单审核数量、库存和排产变化。生产环境必须在网关开启 WebSocket Upgrade。

## 写接口注意事项

- 所有数量、状态和订单号由服务端再次校验。
- 配货和发货接口可能返回业务冲突；客户端应刷新详情后再操作。
- 云端同步接口成功只代表本地 Outbox 已接受，最终结果请查询 `/cloud-sync-status`。
