# V8 流程模型 / 逆向审批 / 东莞仓 逻辑与风险分析

> 分析对象：`crud/workflows.py`、`api/routes/workflows.py`、`api/routes/inventory.py`、`crud/inventory.py`、`crud/order_progress.py`
> 数据基线：2026-10-24 本地库实测（流程实例 93 条、机台 900+ 台、东莞相关订单 10 个）
> 本文只做分析，未修改任何业务代码。

---

## 一、结论摘要

三条主线各有一个结构性问题，其余问题都是它的衍生：

| # | 结论 | 严重度 |
|---|---|---|
| 1 | **已发货退回这条最高风险的逆向操作，实际不走流程引擎** —— `shipment-recall` 被接口层直接拒绝，前端引导用户去「退换货处理」，而那条路径无审批、无实例、无锁 | 高 |
| 2 | **逆向流程的权限只做到"登录"这一层** —— 发起不限角色、撤回不限归属、实例列表全量可读 | 高 |
| 3 | **东莞仓没有唯一判定口径** —— 同一批机台在不同功能里被算成"已发货"或"未发货"，已经造成一个订单永久挂起 | 高 |

另有 6 项中等问题、8 项低风险问题，见第四、五节。

---

## 二、系统实际结构

### 2.1 三层，但"图"只负责选动作

```
前端画布 (WorkflowModels.vue)
    │  产出 {nodes, edges} JSON，无流程图库，div + svg 手绘
    ▼
模型版本表 (workflow_models / workflow_model_versions)
    │  实例创建时钉住 model_version_id，改模型不影响在途流程
    ▼
运行时 (crud/workflows.py)
    ├─ _approval_config        判断要不要审批、审批角色是谁
    ├─ _advance_approved_graph 沿图走一遍，求值条件、记录经过节点
    └─ workflow_action_for_instance 从"路径推进"日志里解析出唯一动作
    ▼
执行器 (execute_* 硬编码 Python 事务函数)
```

**图的表达能力被刻意收窄**，这一点实现得比较扎实（`validate_workflow_snapshot`）：

- 全图只允许 1 个审批节点，且所有分支必须共用
- 每条路径只允许 1 个执行节点
- 条件字段 3 个（+2 个兼容别名），比较符 3 种
- 不允许循环、不允许不可达节点、非条件节点只能有 1 条出边

所以"流程模型"不是通用 BPM 引擎，而是**带审批外壳的动作选择器**。这个定位本身没问题，问题在于下面的实现细节。

### 2.2 逆向流程的两条并行路径

```
路径 A（流程引擎）
  业务页面 → POST /workflows/reverse/instances → 审批 → 执行器 → 派生重入库任务

路径 B（直连，无引擎）
  发货复核 → 退换货处理 → POST /inventory/shipping/return → 直接改库
```

**同一个业务动作（把已发货机台退回来）有两条路径，且只有一条有审批。** 见第三节 P0-1。

---

## 三、逆向审批的问题

### 3.1 状态机全貌

```
                    ┌───────────── 撤回（任意登录用户）─────────────┐
                    ▼                                              │
发起 ──有审批节点──► 审批中 ──approve──► 已通过 ──自动执行──► 执行中 ──成功──► 待派生处理 ──► 已完成
  │                   │                    │                      │
  │                   └──reject──► 已拒绝   └──执行失败──► 执行异常 ──重试──► 执行中
  │
  └──无审批节点/老板发起──► 已通过（创建即执行）

失败态：执行异常 / 永久失败待处理
孤儿态：已通过（审批过了但执行从未启动）← 当前库里有 4 条
```

### 3.2 P0-1 已发货退回绕过流程引擎（已发生）

> **2026-10-28 已修复**：shipment-recall 重新开放发起（需 Admin/Boss 审批），
> 退换货页改为发起该流程；`/inventory/shipping/return` 已加守卫直接返回 409。
> 本节保留为问题记录，代码现状以提交 `方案A` 之后为准。

`api/routes/workflows.py`：

```python
if payload.workflow_key == 'shipment-recall':
    raise ValueError('已发货的机台不能撤回，请到「发货复核 → 退换货处理」办理退回')
```

`api/routes/inventory.py` 的 `/shipping/return`（1955 行起）：

- 没有任何 `create_reverse_instance` 调用，不产生流程实例
- 没有审批节点、没有审批人、没有对象锁
- 直接 `UPDATE finished_goods_data SET 状态='待入库'`，`cancel_order` 时直接
  `UPDATE sales_orders SET status='deleted'`
- 只写 `shipping_return_history` 和 `append_audit_log`

后果：

1. `shipment-recall` 模型（v3，含 Admin/Boss 审批节点）、执行器 `execute_shipment_recall`、
   `REVERSE_WORKFLOW_RULES['shipment-recall']` 全部成为**死代码**——唯一还在用它的入口是
   `create_and_execute_shipment_recall`（订单删除的子流程），而订单删除本身又禁止已发货机台。
2. 取消订单是**删除订单**级别的高风险操作，在这里不需要任何人二次确认。
3. 退回的机台不生成重入库任务、不发通知（`create_reinbound_tasks` 未被调用），
   入库员只能靠"待入库"列表自己发现。而走流程的撤回配货是**会**生成任务的——两条路径行为不一致。

### 3.3 P0-2 撤回接口没有归属校验（代码缺陷）

`crud/workflows.py:1237`：

```python
task = conn.execute(text("""SELECT * FROM workflow_tasks WHERE instance_id=:id
    AND status='待处理' AND assignee_id=:operator ..."""), ...).mappings().first()
if not task and action != 'withdraw':
    raise ValueError('当前用户不是待处理审批人')
```

`approve` / `reject` 要求"我必须是审批人"，但 `withdraw` 被排除在检查之外，也**没有校验
`initiator_id == operator_id`**。结论：

- 任何登录用户，只要知道实例号，就能撤回任何一条"审批中"的流程；
- 撤回会把实例置为 `已撤回` 并释放对象锁，等于**用一条 API 调用绕过整个审批**；
- 撤回人不是审批人时 `task` 为 `None`，审批任务不会被关闭 → `workflow_tasks` 永久留一条
  `待处理`，而 `/workflows/my-pending-count` 只按任务状态统计，审批人的待办红点永远清不掉。

> 当前库里 `workflow_tasks` 已无 `待处理` 记录（85 条全部已结束），所以这个坑还没被踩出来。

### 3.4 P0-3 发起逆向流程不校验权限

`POST /workflows/reverse/instances` 的依赖只有 `get_current_user_context`（登录即可），
没有任何 permission / role 判断。前端靠菜单权限挡住，接口层没有。

叠加两个事实后影响放大：

- `allocation-recall` 模型 v7 **没有审批节点**，创建即 `已通过` 并自动执行；
- 它的执行器把机台从 `待发货` 直接改回 `待入库`，并清空订单/合同/客户占用。

即：一个只有"库存查询"权限的售后账号，直接调接口就能把某订单的配货全部撤回，没有审批、没有二次确认。
`order-delete` / `contract-cancel` 虽然要审批，但发起这一端同样不限角色。

### 3.5 P1-1 审批通过即执行，失败无法收敛（已发生）

`approve_workflow` 在同一个 HTTP 请求里完成"改状态 + 抢租约 + 执行"。
`mark_execution_failure` 的收敛条件写死为 `status='执行中'`：

```python
instance = ... WHERE instance_no=:no FOR UPDATE
if not instance or instance['status'] != '执行中':
    return False          # ← 已通过 / 已拒绝 阶段的失败被静默丢弃
```

于是出现一类无法自动收敛的状态：**实例停在 `已通过`、锁还占着、没有任何 attempt 记录**。
实测当前库里有 4 条：

| 实例 | 流程 | 业务对象 | 创建时间 | 状态 |
|---|---|---|---|---|
| WF-20261019092408-BFF2F8C9DF | order-delete | SO-20261014-3FFF | 10-19 09:24 | 已通过 |
| WF-20261017171841-FA3FBE14FD | allocation-recall | SO-20261017-78B4 | 10-17 17:18 | 已通过 |
| WF-20261011110605-8ADC0468D2 | shipment-recall | 96-09-232 | 10-11 11:06 | 已通过 |
| WF-20261011110102-4B13AA7D52 | shipment-recall | 96-09-211 | 10-11 11:01 | 已通过 |
| WF-20261019145226-531E531253 | order-delete | SO20260926092140AF7A0D7A | 10-19 14:52 | 执行异常 |

这 5 条实例对应 **5 个被永久占用的业务对象**（`workflow_object_locks` 均为"占用中"），
因为冲突校验把 `已通过 / 执行异常` 也算作"未完成"，这些订单/机台**再也发不起任何新的逆向流程**。
最早的已经挂了 13 天，没人发现——系统没有对这类状态的监控或提醒。

### 3.6 P1-2 没有后台调度

`reclaim_expired_execution_leases`、`claim_outbox_events`、`requeue_outbox_event`
都只有 admin 接口，`api/main.py` 的启动循环只管经销商订单推送和微信快照同步。

后果：进程崩在事务中间 → 实例卡 `执行中` → 租约 60 秒过期后无人回收 → 必须人工发现并点重试。
"执行异常"重试也依赖管理员在审批中心点「重试执行」，没有自动重试上限（`retry_count` 只在 outbox 用）。

### 3.7 P1-3 冲突校验与对象锁口径不一致

两套机制并存，覆盖范围不同：

| 机制 | 粒度 | 判据 |
|---|---|---|
| 冲突校验（`create_reverse_instance`） | 业务对象 | `(business_type, business_id)` 字符串完全相等 |
| 对象锁（`workflow_object_locks`） | 流程明细 items | `(object_type, object_id)` |

问题在于 **同一业务对象在不同流程里 `business_type` 不同**：

| 流程 | business_type | business_id |
|---|---|---|
| order-delete | `订单` | 订单号 |
| allocation-recall | `订单配货` | 订单号 |
| contract-cancel | `合同` | 合同号 |

所以：

- 订单删除（锁 `订单/订单号`）与撤回配货（锁 `机台/流水号`）**互不感知**，可以同时对同一订单发起并审批；
- 两者都通过后，一个把订单置删除、一个把机台置待入库，谁后执行谁报"状态已变化"，留下一条执行异常实例；
- 反过来，机台级流程之间能靠唯一索引互斥，说明锁机制本身是有效的，只是**没有统一到"业务对象"这一层**。

### 3.8 P1-4 策略表只是给前端看的

```python
REVERSE_WORKFLOW_RULES = {
    'contract-cancel': {'approval': 'required', ...},
    'order-delete':    {'approval': 'required', ...},
    'allocation-recall': {'approval': 'automatic', ...},
    ...
}
```

全项目搜索 `REVERSE_WORKFLOW_RULES` 只有两处：定义，和 `GET /workflows/models` 把它原样返回给前端。
`approval` 这个键**服务端从未读取**。真正的判定在 `create_reverse_instance`：

```python
requires_approval = bool(approval_nodes) and not boss_bypass
```

也就是说"要不要审批"完全由**当前发布版本的模型图**决定，策略表里的 `required` 不起作用。
谁把 order-delete 模型的审批节点删掉再发布，订单删除就变成免审批直接执行。

另外 `boss_bypass`：`initiator_role == 'boss'` 时 `requires_approval=False`，同时跳过
"审批人不能与发起人相同"的校验。老板发起删单/取消合同**没有任何二次确认**。

### 3.9 P1-5 派生任务强依赖"存在活跃入库员"

`create_reinbound_tasks`：

```python
if not assignee:
    raise ValueError('系统没有可用的入库员账号，无法创建重入库任务')
```

这个异常发生在执行器的事务里，会**回滚整笔业务变更**。也就是说：入库员账号被停用/改角色，
所有需要重入库的逆向流程（撤回配货、订单删除、合同取消、客户成品撤回）全部执行失败。
用一个"账号是否存在"作为业务流程的硬前提，风险偏高。

### 3.10 P1-6 / P1-7 派生阶段没有兜底

- 10 条实例停在 `待派生处理`，最早 10-23，10 个重入库任务全部 `待处理`；
- 没有超时、没有升级、没有二次提醒，只能等入库员处理；
- 实测这 10 台机台都是 `待入库`，其中 4 台还保留着库位（C01 / E07 / E05 / 老厂四车间一楼400）——
  因为撤回配货的 UPDATE **不清 `Location_Code`**，而发货撤回的 UPDATE **清**，同一个"待入库"有两种语义。

### 3.11 低风险项（P2）

| # | 问题 | 位置 |
|---|---|---|
| 1 | 幂等键由前端 `Date.now()` 生成，重复点击必然产生新实例，幂等只在单次请求内有效 | 各业务页面 `idempotency_key` |
| 2 | 审批转交可指定任意用户名，包括停用账号和非审批角色，等于把审批权转给任何人 | `transfer_reverse_approval` |
| 3 | `GET /workflows/instances`、`/tasks` 不按用户过滤，任何登录用户可读全量流程数据（前端只是自己筛） | `list_instances` / `list_tasks` |
| 4 | 流程表与业务表排序规则不同（`utf8mb4_0900_ai_ci` vs `utf8mb4_general_ci`），所有跨表 JOIN 必须手写 `COLLATE`，新增查询极易踩 1267 | 表结构 |
| 5 | `failure_reason` 直接存 Python 异常字符串（如 `'create_shipment_recall'`），运营无法据此处理 | `mark_execution_failure` |
| 6 | 审批记录 `task_status_snapshot` 写的是操作前状态（`审批中`），字段语义与内容不符 | `transition_reverse_instance` |
| 7 | 审批节点缺失时 `_approval_config` 返回空，流程静默变成免审批，发布环节不提示风险 | `_approval_config` |
| 8 | 条件字段 `bound_machine_count` 的含义随 `workflow_key` 变化（订单看占用订单号、其他看合同号），把条件节点加到别的流程上会静默查错字段 | `_condition_value` |

---

## 四、流程模型的问题

### 4.1 校验严、运行时窄，但两者不完全对齐

发布校验（`validate_workflow_snapshot`）覆盖了结构合法性，运行时（`_advance_approved_graph`）却有几处隐含假设：

- `notify` 节点的通知在**执行成功之后**才发（`dispatch_pending_model_notifications`），
  执行失败则通知永远不发，也不重试（只有 admin 手动接口）；
- 通知节点写在执行节点之后还是之前，运行时并不区分——`_advance_approved_graph` 一次性收集所有
  经过的 notify 节点，等于"路径上出现过的通知节点都会在事后统一发"；
- 审批是**流程级**的，不是路径级：只要图里有 1 个审批节点，所有分支都要审批；
  但审批人只看到"这个流程"，看不到"这次会走哪条分支"（条件在审批之后才求值）。

### 4.2 图与动作脱节（设计如此，但要知道边界）

- 执行节点里的 `action` 只是一个枚举指针，真正的行为在 `execute_*` 函数里；
- `delete_order` 与 `delete_order_reinbound` 走**同一个** `execute_order_delete`，
  区别只在事后是否强制派生重入库任务（`force_reinbound`）；
- 因此"改流程图"能改的只有：要不要审批、审批给谁、走哪个动作、发不发通知。
  改不了动作本身的语义。

### 4.3 死动作

`create_shipment_recall` 挂在 order-delete 模型里，但：

- 订单删除的发起前置校验禁止存在已发货机台；
- 执行时 `execute_order_delete` 再次检查 `已出库/已发货/库存中（DG-WH）` 并报错。

所以这个动作在正常数据下**永远走不到**。它历史上确实被触发过一次（WF-20261019145226），
失败原因 `没有可发起发货撤回的机台`——正好是数据口径不一致导致的。

---

## 五、东莞仓的问题

### 5.1 四套判定口径并存

| 口径 | 写法 | 使用位置 |
|---|---|---|
| A 状态精确串 | `状态 = '库存中（DG-WH）'` | 订单删除前置校验、`execute_order_delete`、`execute_contract_cancel`、`_condition_value.shipped_machine_count`、`create_and_execute_shipment_recall` |
| B 库位三写法 | `Location_Code IN ('DG-WH','DONGGUAN','东莞仓库')` | 库存查询 `actual_only`、退换货候选、取消订单完整性校验、`_shipment_recall_eligible` |
| C 库位单写法 | `Location_Code = 'DG-WH'` | 东莞客户成品查询、东莞订单操作校验、发货后订单完成计数（1703 行） |
| D 客户名子串 | `'东莞' in 客户名` | 发货时判断是否转客户仓（同时看 `finished_goods_data.客户` 和 `sales_orders.客户名`） |

`crud/inventory.py` 里其实已经有统一入口：

```python
def is_customer_warehouse_slot(slot_code, slots=None) -> bool   # 支持 slot_type / customer_name / 三种代码
def slot_counts_as_actual_inventory(slot_code, slots=None) -> bool
```

**全项目零调用**。路由层 12 处手写判定，写法各不相同。

### 5.2 已发生的数据错位（实测）

```
状态 = '库存中（DG-WH）' 但 Location_Code 不是 DG 的机台：12 台
全部属于订单 SO-20260918-53E2，更新时间完全相同（2026-09-30 09:18:00）
machine_transfer_history 中该订单记录 0 条 → 不是应用写出来的
```

同一批机台，两套口径给出相反结论：

| 口径 | 该订单"已发货"台数 |
|---|---|
| 按库位（确认发货 / 订单完成 / 退换货候选 / 取消订单完整性） | **0** |
| 按状态（订单删除 / 发货撤回 / 条件节点） | **12** |

由此产生的完整影响链：

1. **订单永远完不成**：`confirm_shipping` 里 `shipped >= need` 才把订单置 `done`，
   这单 `need=12`、按库位算 `shipped=0` → `status` 至今是 `active`（9-18 下单，已 36 天）。
2. **退不回来**：`/shipping/returned-candidates` 按库位筛，这 12 台不在列表里。
3. **删不掉**：`order-delete` 前置校验按状态筛，命中 12 台 → 直接拒绝发起。
4. **取消订单可以漏掉它们**：`cancel_order` 的"必须退回全部已发货机台"校验也按库位筛，
   这 12 台不算"已发货"，可以不勾选就取消订单，订单置 `deleted` 后机台仍挂着占用订单号。
5. **算进工厂实际库存**：`actual_only` 按库位排除 DG，这 12 台库位是 B07/A06，
   会被计入工厂实际库存，而它们实际在东莞客户仓。

**结论：这 12 台机台目前处于"系统认为已发货、但不能退、不能删、订单不能完结、还占着工厂库位"的死角。**

### 5.3 东莞识别依赖客户名

`confirm_shipping` 判断是否转客户仓：

```python
if "东莞" in customer_name:      # sales_orders.客户名
    dongguan_customer_orders.add(order_id)
...
if "东莞" in row.get("客户"):     # finished_goods_data.客户
```

- 客户名改成"東莞"（繁体）、"东莞分公司"以外的写法，或客户名里没有"东莞"二字，就不转仓；
- 转仓后判断退货/取消，用的却是**库位**，不是客户名——两处判据不同源；
- 目前 12 个东莞订单里，`SO-20260921-64FC` 等按库位能识别，`SO-20260918-53E2` 就不能。

### 5.4 DG 仓容量与库位约束

- `get_slot_capacity('DG-WH')` 返回 500（客户仓上限），DG-WH 不在"无限库位"名单里；
- 但容量校验只在 `inbound_to_slot` 里做，而"发货转客户仓"是直接 UPDATE，
  **不走容量校验**。当前 DG 实际占用 25~37 台，短期无风险，长期会静默超容。
- 东莞客户成品查询用 `Location_Code='DG-WH'` 精确匹配，`DONGGUAN` / `东莞仓库` 变体查不到。

---

## 六、当前存量问题清单

| 对象 | 状态 | 影响 |
|---|---|---|
| 订单 `SO-20260918-53E2` | 12 台状态/库位错位 | 订单永久 active，不能退、不能删、订单不能完结 |
| 订单 `SO20260926092140AF7A0D7A` | 实例执行异常 + 孤儿锁 | 无法发起任何新逆向流程 |
| 订单 `SO-20261014-3FFF` | 实例卡"已通过" + 锁 | 同上，已挂 5 天 |
| 订单 `SO-20261017-78B4` | 实例卡"已通过" + 锁 | 同上，已挂 7 天 |
| 机台 `96-09-211` / `96-09-232` | 实例卡"已通过" + 锁 | 同上，已挂 13 天 |
| 10 条实例 | 待派生处理 | 10 个重入库任务未完成，无超时提醒 |
| 10 台机台 | 待入库但保留库位 | 库位占用与实际状态不一致（4 台） |

---

## 七、优先级建议（仅排序，未动手）

| 顺序 | 事项 | 理由 |
|---|---|---|
| 1 | 统一东莞判定口径，收敛到 `is_customer_warehouse_slot` 一个函数 | 口径分裂已经造成真实订单挂起，且是所有下游问题的根 |
| 2 | 修 `SO-20260918-53E2` 的 12 台数据（先确认机台实际在东莞还是在 B07） | 数据修完，订单才能完结、才能退/删 |
| 3 | 撤回接口加归属校验；审批任务随实例一起关闭 | 一条 API 就能绕过审批，属安全缺陷 |
| 4 | 逆向发起加权限校验（至少限定角色/权限码） | 现在"登录即可发起删单" |
| 5 | `mark_execution_failure` 覆盖"已通过"阶段；清理 4 条卡死实例 | 5 个业务对象被永久占用 |
| 6 | 让 `REVERSE_WORKFLOW_RULES['approval']` 真正生效，或在模型发布时校验策略一致性 | 策略表当前是摆设 |
| 7 | 明确"已发货退回"到底走哪条路径，删掉另一条 | 现在审批链形同虚设 |
| 8 | 加后台调度：租约回收、outbox 重试、待派生超时提醒 | 消除人工巡检依赖 |
| 9 | 冲突校验统一到业务对象，与对象锁口径对齐 | 防止删单与撤回配货并发 |
| 10 | 其余 P2 项 | 按迭代排 |

---

## 八、关键代码位置

| 内容 | 位置 |
|---|---|
| 逆向规则表（未被服务端执行） | `crud/workflows.py:558` |
| 逆向实例创建 / 冲突校验 / 加锁 | `crud/workflows.py:1046` |
| 审批流转（含 withdraw 缺口） | `crud/workflows.py:1217` |
| 执行器唯一解析入口 | `api/routes/workflows.py:23` |
| 审批通过即执行 | `api/routes/workflows.py:291` |
| shipment-recall 被拒 | `api/routes/workflows.py:238` |
| 执行失败收敛 | `crud/workflows.py:1627` |
| 退换货（绕过引擎） | `api/routes/inventory.py:1955` |
| 东莞转仓 | `api/routes/inventory.py:1640` |
| 发货后订单完成计数（库位单写法） | `api/routes/inventory.py:1703` |
| 东莞统一判定工具（零调用） | `crud/inventory.py:55` |
| 订单进度装载 | `crud/order_progress.py:60` |
