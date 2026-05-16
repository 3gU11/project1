# WeChat Batch Summary

This module is independent from the V7 runtime. It creates one MySQL table for
`C:\RJ_Wechat_App` to read:

```sql
SELECT `批次号`, `预计入库时间`, `机型`, `数量`
FROM `wechat_batch_summary`
ORDER BY `预计入库时间` DESC, `批次号` DESC, `机型` ASC;
```

It also exposes English alias columns for the existing
`C:\RJ_Wechat_App\server` adapter:

```sql
SELECT batch_no, expected_inbound_time, model, quantity
FROM wechat_batch_summary;
```

The table is grouped from `finished_goods_data` by:

- `批次号`
- `预计入库时间`
- `机型`

Rows with an empty `批次号` or empty `机型` are ignored.

## Install

From the V7 project root:

```powershell
python -m wechat_sync.batch_summary install
```

If that Python environment does not have `PyMySQL`, use the Node installer:

```powershell
node wechat_sync/install_batch_summary.js
```

The command creates:

- `wechat_batch_summary`
- `refresh_wechat_batch_summary_group`
- `refresh_wechat_batch_summary_all`
- triggers on `finished_goods_data` for insert, update, and delete

## Manual Refresh

```powershell
python -m wechat_sync.batch_summary refresh
```

## Check Data

```powershell
python -m wechat_sync.batch_summary list --limit 20
```

The module reads MySQL connection settings from environment variables first, then
from the project `.env`, then falls back to V7 defaults.

For `C:\RJ_Wechat_App\server`, set:

```text
FINISHED_GOODS_TABLE=wechat_batch_summary
```
