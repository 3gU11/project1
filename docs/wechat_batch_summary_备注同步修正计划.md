# wechat_batch_summary 与云端备注同步修正计划

## Summary

修正两条规则：`wechat_batch_summary` 只能由 `finished_goods_data` 重建，不能因为经销商订单审核通过而扣减；小程序云端改备注后，V7 新增“附加备注”字段接收，并在配货前参与后续转合同/沙盘备注，配货后不再自动覆盖生产或库存备注。

## Key Changes

- 库存汇总规则：
  - 保持 `wechat_batch_summary` 作为 `finished_goods_data` 的只读汇总结果。
  - 经销商订单 `pending -> approved` 只改变 `dealer_orders` 状态和占用计算，不直接更新、删除、扣减 `wechat_batch_summary`。
  - 云端 V8 的 `/dealer-orders/{order_no}/review` 也不应改云端 `wechat_batch_summary`；库存云端同步只走 `/wechat-batch-summary/sync` 的整表 replace。

- V7 本地订单备注：
  - 给 `dealer_orders` 增加 `cloud_extra_remark TEXT`，用于保存小程序云端修改/追加的备注。
  - `sync_cloud_dealer_orders()` 拉取云端订单时，不再用云端 `remark` 覆盖 V7 原 `remark`；而是写入 `cloud_extra_remark`。
  - 列表、预览、经销商带入合同页面展示“原备注 + 附加备注”，但保留字段来源，避免混淆。

- 备注传播边界：
  - 状态在 `pending / approved / contracted` 且尚未配货时，`cloud_extra_remark` 可参与转合同、生成沙盘卡片、急单备注。
  - 状态进入 `partial_allocated / allocated / completed` 后，云端备注只继续记录到 `dealer_orders.cloud_extra_remark`，不自动覆盖 `factory_plan`、沙盘、`finished_goods_data.合同备注`。
  - 如果用户需要配货后修改库存备注，仍走 V7 的库存/机台备注编辑流程，避免云端小程序改动影响已执行库存。

- 同步入口：
  - “同步云端订单”不只拉 `pending`，应覆盖 `pending / approved / contracted`，这样配货前云端附加备注能回到 V7。
  - 云端备注变更不触发 `wechat_batch_summary_sync`；只有 `finished_goods_data` 变化、入库、配货写库存、发货等实际库存变化才触发汇总刷新和云端 replace。

## Test Plan

- 审核通过经销商订单后，检查 `wechat_batch_summary.quantity` 不变；订单预览可用量通过 `dealer_orders` 占用计算减少。
- 修改 `finished_goods_data` 状态/机型/批次后，刷新 `wechat_batch_summary`，数量跟随实际库存变化。
- 云端小程序改订单备注后，同步到 V7，`dealer_orders.cloud_extra_remark` 更新，`remark` 不被覆盖。
- 订单未配货前转合同，合同/沙盘备注包含附加备注。
- 订单配货后再改云端备注，只更新 `cloud_extra_remark`，不改 `finished_goods_data.合同备注` 和库存汇总。
- 重复同步同一云端备注不会重复拼接显示内容。

## Assumptions

- 新字段命名为 `cloud_extra_remark`，含义是“小程序云端附加备注”。
- “直到配货之前”定义为状态未进入 `partial_allocated / allocated / completed`。
- 第一阶段只改 V7 本地和现有 V8 接口行为约束，不新增复杂双向事件总线。
