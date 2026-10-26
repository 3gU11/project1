# V8 与订货小程序 Bridge

## 数据边界

V8 是订货库存与机型目录的来源。桥接仅同步：

- V8 从 `finished_goods_data` 汇总出的 `wechat_batch_summary`（含批次、预计入库、机型、数量、加高标记）。
- 启用/停用状态、排序与系列字段来自 `model_dictionary`。

不复制 `finished_goods_data` 的逐台流水或 `factory_plan` 的客户、合同信息。小程序订单仍写入订货端 `dealer_orders`，V8 定时拉取并镜像订单；工厂审核、转合同、配货和完成状态由 V8 通过回调写回订货端。两端数据库不直接共享业务表。

## 接口与频率

- V8 每 300 秒（`V8_ORDERING_SNAPSHOT_INTERVAL_SECONDS`）入队一次全量快照，库存变化时也会触发快照；outbox 负责重试。
- `POST /api/v8/bridge/snapshot`：校验快照内容摘要、HMAC、时间戳及 nonce 后，在单个 InnoDB 事务中替换库存和机型读模型。
- `GET /api/v8/bridge/orders?status=...&page=...&page_size=...`：V8 以 HMAC 分页读取小程序订单。
- `POST /api/dealer/orders/{orderNo}/v8-status`：V8 以 HMAC 回写工厂审核/合同/配货状态，继续使用 `Idempotency-Key` 去重业务事件。

HMAC 消息为：

```text
timestamp\nnonce\nHTTP_METHOD\nrequest_path\nsha256(raw_request_body)
```

POST 请求的规范串还包含 `Idempotency-Key`，位于 `request_path` 与请求体摘要之间；GET 请求该字段为空。签名为该消息的 HMAC-SHA256 十六进制摘要，头为 `X-V8-Signature: sha256=<摘要>`。服务端拒绝超出 5 分钟的请求，并在事务中持久化 nonce；快照还按 `generatedAt` 拒绝覆盖较新的版本。需保证两台服务时钟同步。

空库存快照默认拒绝；只有在确实需要将云端库存清空时，才在 V8 `.env` 中显式设 `V8_BRIDGE_ALLOW_EMPTY_INVENTORY=1`。机型目录始终不能为空。

## 部署配置

在 V8 与小程序 API 的 `.env` 中配置同一个至少 32 字节的高熵 `V8_SYNC_SECRET`，V8 的 `WECHAT_CLOUD_API_BASE` 指向部署后的小程序 API 根地址。不要把真实密钥提交到版本库。未配置密钥或密钥长度不足时，签名桥接请求会失败关闭。

部署完成后，检查 Node `/api/dealer/health`、V8 outbox 的快照事件状态，并分别验证快照接收、订单分页拉取和状态回写。协议单测不能替代真实数据库和云端联调。
