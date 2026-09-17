# 订单配货与库存同步修复发布说明

## 发布范围

本次修复要求 Python API、Go 排产服务和前端使用同一提交版本：

- 订单创建或合同编辑不再自动占用具体机台。
- 只有显式配货接口可以写入机台订单占用关系。
- 已实际入库的机台按库存现货处理，不再被活动批次覆盖为在产机台。
- 合同/订单关系作为附加绑定状态，生命周期仍使用待入库、库存中、待发货等状态。
- 自动完成批次同时检查入库历史和当前库存状态，历史误记录不再单独触发完工。
- 沙盘调货不能移动已被订单占用的机台。

## 正式库清洗

清洗工具为 `ops/repair_order_inventory_sync.py`。它不会读取项目默认数据库配置，必须显式提供正式库 URL。

PowerShell 预览：

```powershell
$env:V8_REPAIR_DATABASE_URL = 'mysql+pymysql://USER:PASSWORD@HOST:3306/rjfinshed?charset=utf8mb4'
.\.venv\Scripts\python.exe ops\repair_order_inventory_sync.py
```

核对输出中的逐台明细及两个数量：

- `unlogged_binding_count`：待发货、库存订单为空、机台表有订单，但没有人工配货日志或审计的历史自动误绑。
- `mirror_mismatch_count`：活动生产卡片和待入库库存镜像的合同/订单关系不一致。

执行时必须回填本次预览数量。例如预览为 25 和 35：

```powershell
.\.venv\Scripts\python.exe ops\repair_order_inventory_sync.py `
  --apply `
  --confirm-unlogged-count 25 `
  --confirm-mirror-count 35
```

脚本先创建三张带时间编号的备份表，再在一个数据事务中逐台更新、写入 `sys_operation_log` 并复核。任何确认数量变化都会拒绝执行；复核失败会回滚数据更新和本次审计记录，备份表仍保留。

## 回滚

从执行结果取得 `run_id`，在应用回滚后执行：

```powershell
.\.venv\Scripts\python.exe ops\repair_order_inventory_sync.py --rollback 20260917_182837
```

回滚恢复脚本修改过的关系及库存状态字段，备份表和审计日志保留。若正式环境在清洗后又发生业务操作，应先比较备份表与当前数据，不应直接回滚覆盖新业务数据。

## 发布顺序

1. 备份正式 MySQL，并验证备份可读取。
2. 运行清洗脚本预览并保存输出。
3. 部署同一 Git 提交，构建 Go 服务和前端。
4. 停止旧 Go/FastAPI，切换新版本后启动服务。
5. 执行清洗脚本 `--apply`。
6. 验证库存查询、订单配货、生产看板和目标批次状态。

## 上线验收

- `待发货`且订单号为空的数量为 0。
- 活动机台与已有库存镜像的合同号、订单号差异为 0。
- 已入库有库位的机台只显示为库存现货。
- 订单创建、合同编辑不会自动写入 `units.sales_id`。
- 有历史自动入库记录但当前仍为待入库的机台，不计入批次完工。
- Go、FastAPI、前端版本均来自同一个提交。
