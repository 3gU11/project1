# V8 维修系统快照同步

这是一个只出站的后台工具，不依赖前端页面。开发环境默认 `REPAIR_SYNC_ENABLED=false`，`snapshot --dry-run` 和 `daily --dry-run` 只读取本地数据库并校验/输出快照，不会访问公网。

## 常用命令

```powershell
python -m repair_sync snapshot --date 2026-07-16 --dry-run
python -m repair_sync daily
python -m repair_sync send-pending
python -m repair_sync status
python -m repair_sync verify-config
```

服务器 API 地址只需要填写 `REPAIR_SYNC_BASE_URL`。正式联调时再填写独立的 `REPAIR_SYNC_KEY_ID`、`REPAIR_SYNC_HMAC_SECRET` 和 mTLS 证书变量；不要复用订单同步的 API Key，也不要把密钥提交到 Git。

快照优先读取说明约定的规范表；当前 V8 已有的 `finished_goods_data` 和 `model_dictionary` 会自动作为机台/机型来源。绑定、物料和拍照配置表如果尚未部署，会以空集合进入本地快照，并保留来源水印，待表结构补齐后无需改前端。

物料实例使用 `(material_code, serial_no)` 作为复合身份。同一个编号如果确实代表不同物料，可以在不同物料编码下重复出现；同一物料编码下的重复编号仍会被拒绝。
