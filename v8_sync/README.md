# V8 数据同步（v8_sync）

只出站的后台同步工具，把工厂端机台档案推送到云端售后系统（8798 的 `machine_index`）。
不依赖前端页面，也不需要 Windows 计划任务——FastAPI 启动钩子会生成当天快照并加入 outbox，
由已有的 cloud sync worker 负责发送和重试。

## 同步什么

售后系统判定保修只依赖两个字段：

| 字段 | 来源 | 说明 |
|---|---|---|
| `serial` | `finished_goods_data.流水号` | 机台唯一编号 |
| `shipping_date` | `shipping_history` 中「已出库」记录的 `更新时间` | **保修起算依据** |

`customer`（客户）与 `model`（机型）为辅助字段。
出厂日期不参与保修计算，已从快照中移除。

## 常用命令

```powershell
python -m v8_sync snapshot --date 2026-07-16 --dry-run
python -m v8_sync daily
python -m v8_sync send-pending
python -m v8_sync status
python -m v8_sync verify-config
```

## 配置

服务器 API 地址只需填 `V8_SYNC_BASE_URL`。正式联调时再填 `V8_SYNC_KEY_ID`、
`V8_SYNC_HMAC_SECRET` 和 mTLS 证书变量；不要复用订单同步的 API Key，也不要把密钥提交到 Git。

> 兼容说明：所有配置键同时识别旧前缀 `REPAIR_SYNC_*`。新键 `V8_SYNC_*` 优先，
> 旧部署的 `.env` 无需修改即可继续运行。

```dotenv
V8_SYNC_ENABLED=true
V8_SYNC_BASE_URL=https://aftercare.example.com
V8_SYNC_SNAPSHOT_PATH=/api/integrations/v8/snapshots
V8_SYNC_CLIENT_ID=v8-factory-01
V8_SYNC_KEY_ID=<key id>
V8_SYNC_HMAC_SECRET=<32 字节以上随机值>
V8_SYNC_TIME=02:30
V8_SYNC_TIMEZONE=Asia/Shanghai
```

## 数据源

- 机台主来源：`finished_goods_data`（有 `machine_component_bindings` 时合并去重）
- 发货日期：`shipping_history` 中状态以「已出库」开头的记录
- 机型目录：`model_dictionary`
- 绑定、物料、拍照配置表若尚未部署，会以空集合进入快照并保留来源水印，表结构补齐后无需改前端

## 注意

`shipping_history` 由发货复核确认时归档（`crud/inventory.py: archive_shipped_data`）。
若该表为空，本同步不会报错，但云端 `shipping_date` 会全部为空，导致售后无法判定保修。
排查顺序：先确认 `shipping_history` 有数据，再看快照。
