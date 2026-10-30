# 第一阶段正向流程验收清单

## 统一验收项

每个流程必须验证：成功提交、前置状态校验、重复提交幂等、异常回滚、流程实例、自动通过任务、审计日志、派生动作和提交后通知。

## 流程清单

| 流程 Key | 页面/入口 | 核心对象 | 幂等单位 | 主要派生动作 | 当前状态 |
|---|---|---|---|---|---|
| `contract-create` | 合同管理 / `POST /api/v1/planning/contracts/batch-create` | 合同 | 合同号 | factory_plan、合同通知 | 已接入 |
| `order-create` | 销售下单 / `POST /api/v1/planning/orders` | 销售订单 | 订单号 | 订单关联合同 | 已接入 |
| `allocation-create` | 订单配货 / `POST /api/v1/planning/orders/{order_id}/allocate` | 销售订单 | 订单号 | 配货及库存关联 | 已接入 |
| `stock-inbound` | 成品入库 / `POST /api/v1/inventory/inbound-to-slot` | 机台 | 流水号+库位 | 库位、库存状态 | 已接入 |
| `stock-transfer` | 库位转移 / `POST /api/v1/inventory/inbound-to-slot` | 机台 | 流水号+库位 | 库位、转移历史 | 已接入 |
| `shipment-confirm` | 发货确认 / `POST /api/v1/inventory/shipping/confirm` | 发货机台 | 流水号+订单号 | 库存、订单状态 | 已接入 |
| `customer-machine-plan` | 客户成品规划 / `POST /api/v1/inventory/customer-machine-plans` | 客户机台 | 流水号+规划时间 | 规划记录 | 已接入 |
| `customer-order-shipped` | 客户成品订单 / `POST /api/v1/inventory/customer-order-actions/execute` | 客户成品订单 | 订单号+机台集合 | 发货确认、客户仓状态 | 已接入；与发货同事务 |

## 逐项状态和审计定义

| 流程 Key | 前置原始状态/条件 | 成功目标原始状态 | 审计与派生记录 | 失败/重复结果 |
|---|---|---|---|---|
| `contract-create` | 合同号不存在；机型有效；交期和客户必填 | 合同写入 `factory_plan`，状态由保存模式决定 | 合同新增审计、合同通知、流程实例和自动任务 | 单合同失败回滚；相同合同号跳过或拒绝 |
| `order-create` | 订单明细有效；机型存在；关联合同可用 | `sales_orders.status=active` | 销售下单新增审计、合同关联和流程实例 | 相同订单动作幂等；校验失败不写入 |
| `allocation-create` | 订单存在且允许配货；库存机台满足配货条件 | 配货记录及订单配货状态更新 | 配货审计、库存关联、流程实例和自动任务 | 状态不符整次回滚；重复配货不重复实例 |
| `stock-inbound` | 机台存在且允许入库；目标库位有效 | 机台进入入库目标状态并写入库位 | 入库审计、库存/库位更新、流程实例 | 校验失败不改变库存 |
| `stock-transfer` | 机台存在；原库位和目标库位有效且不同 | `Location_Code` 更新为目标库位 | 转移审计、`machine_transfer_history`、流程实例 | 重复目标库位幂等；失败回滚 |
| `shipment-confirm` | 机台为待发货；订单状态为 `ready/allocated/packed` | 普通机台为 `已出库`；客户仓机台为 `库存中（DG-WH）` | 发货审计、订单状态更新、流程实例和自动任务 | 机台/订单/流程同事务回滚 |
| `customer-machine-plan` | 流水号存在；机台可规划 | `customer_machine_plans` 写入或更新规划 | 客户成品规划审计、规划表、流程实例 | 相同流水号更新规划，不重复实例 |
| `customer-order-shipped` | 客户订单；机台待发货；订单已完成配货 | 客户机台发货状态更新，订单按数量规则完成 | 与 `shipment-confirm` 同事务；客户订单审计、两个流程任务 | 任一流程失败全部回滚；订单+机台集合幂等 |

## 已完成核验

- 8 个入口均已在后端代码中定位。
- 8 个流程模型均已发布并纳入正式启用白名单。
- `shipment-confirm` 与 `customer-order-shipped` 已共用同一数据库事务。
- 自动通过任务使用系统账号，实际操作人保存在流程实例和审计记录中。
- 完整回归测试：`107 passed, 2 skipped`。

## 验收结论规则

- 业务数据和成功流程记录必须同事务提交。
- 任一核心写入失败不得留下成功实例或自动任务。
- 提交后的缓存刷新、通知和外部同步不得阻断已提交业务。
- 逆向操作不纳入本清单的正向自动通过验收。
