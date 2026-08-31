# 数据与备份

## 数据组成

| 数据 | 位置/表 | 说明 |
| --- | --- | --- |
| 业务主数据 | MySQL `rjfinshed` | 合同、订单、库存、用户和权限 |
| 入库历史 | `inbound_history` | 不可变入库事件，用于报表和追溯 |
| 云端同步队列 | `cloud_sync_outbox` | 待发送事件、重试次数和错误信息 |
| 合同文件 | `data/contracts` | 合同原件及附件 |
| 机台档案 | `machine_archives` | 照片、缩略图和检测文件 |

## 备份策略

- 每日备份 MySQL，并保留至少一个异地副本。
- 每次发布和数据库修复前，备份数据库、`data/contracts`、`machine_archives`。
- 备份文件加密并限制访问；不要提交 `backups/`、`artifacts/` 或生产 SQL。
- 定期执行恢复演练，验证备份不只是“文件存在”。

## MySQL 示例

```bash
mysqldump --single-transaction --routines --triggers \
  -h "$MYSQL_HOST" -P "$MYSQL_PORT" -u "$MYSQL_USER" -p \
  "$MYSQL_DB" > backup-YYYYMMDD-HHMMSS.sql

mysql -h "$MYSQL_HOST" -P "$MYSQL_PORT" -u "$MYSQL_USER" -p \
  "$MYSQL_DB" < backup-YYYYMMDD-HHMMSS.sql
```

Windows 可使用同名 MySQL 客户端命令；密码建议交互输入，不要写进命令历史。

## 数据修复原则

1. 先停止相关写入或切换维护页。
2. 导出受影响记录并记录 SQL、操作者和时间。
3. 在事务中执行最小范围修复。
4. 重建报表或同步数据后，再恢复服务。
