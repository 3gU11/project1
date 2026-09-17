# 超计划合同卡片清洗

`ops/cleanup_excess_contract_bindings.py` 用于清理由旧订单同步逻辑写入的超计划合同绑定。脚本默认只预览，不会修改数据库，也不会读取项目的默认数据库配置。

## 判定边界

脚本按“合同号 + 机型”汇总，仅在同时满足以下条件时列入清洗：

- 卡片总数超过 `factory_plan` 的排产数量；
- 排产数量已被有订单占用、配货日志、锁定或受保护库存状态的卡片完全覆盖；
- 剩余超量卡片都有真实批次和流水号，库存状态不受保护，且没有订单占用、锁定、固定或配货证据；
- 超量数量与可清理卡片数量完全一致。

任何无法分类的卡片都会使整个合同机型组被排除。脚本不会处理无计划合同、无批次特殊卡、库存中、待发货、已出库、已发货或报废卡片。

## 预览与执行

PowerShell：

```powershell
$env:V8_REPAIR_DATABASE_URL = 'mysql+pymysql://USER:PASSWORD@HOST:3306/rjfinshed?charset=utf8mb4'
py -3 ops/cleanup_excess_contract_bindings.py
```

核对输出中的 `candidate_count`、`fingerprint`、逐组汇总和逐台明细。执行时必须同时回填数量与指纹：

```powershell
py -3 ops/cleanup_excess_contract_bindings.py `
  --apply `
  --confirm-count 35 `
  --confirm-fingerprint PREVIEW_SHA256
```

执行前会备份 `units`、`finished_goods_data` 和 `production_history_ledger` 中的候选记录。数据更新、库存镜像清理和审计日志写入位于同一事务；候选集合变化、任一逐行保护条件失败或执行后仍有候选时都会回滚。

脚本只清除合同及订单关系字段，不改变卡片所在批次、机型、流水号和库存生命周期状态。

## 回滚

从执行结果取得 `run_id`：

```powershell
py -3 ops/cleanup_excess_contract_bindings.py --rollback 20260917_190000
```

回滚会恢复三张备份表中的关系字段，备份表和清洗审计记录会保留。正式库在清洗后若已有新业务操作，应先比较备份与当前数据，不应直接回滚覆盖新数据。
