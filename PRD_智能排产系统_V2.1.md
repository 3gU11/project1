# 智能排产与预测改单系统
## 产品需求规格说明书 V2.1 · 业务对齐落地版

> 机密文件，仅供内部使用
> 修订记录：V2.1 在 V2.0 基础上对预测引擎、Lock 机制、横向拖拽改单交互、数据模型四大模块作彻底重构，使之与现有 MySQL 表结构（`rjfinshed`）对齐，可直接进入开发。

---

## 0. V2.1 关键变更一览（相对 V2.0）

| 模块 | V2.0 旧定义 | V2.1 新定义 | 变更原因 |
|---|---|---|---|
| 预测断批规则 | 每批按交期顺序切分 | **相邻台间交期间隔 > 30 天必须断批** | 业务真实场景：跨月订单不应混批生产 |
| 机型产能比例 | 2 类（A/B 二选一） | **N 类机型，每类对应一个比例（总和 = 100%）** | 实际机型种类多，需可扩展 |
| 自动填充逻辑 | 全批按比例切分台数 | **批内已含合同指定台先锁定，剩余空槽按比例分配并趋近目标比例** | 合同指定台数是硬约束 |
| Lock 机制 | 批次级 Lock（一台动整批锁） | **仅信息强改场景锁机台**；拖拽换批不锁，目标批立即重算 | 批次级 Lock 过粗，会冻结大量未编辑机台 |
| Cron 跳过逻辑 | 跳过整批 | 仅跳过 `unit.is_locked = true` 的单台机 | 同上 |
| 看板核心模型 | 机台 = 订单（卡片即合同） | **机台 = 容器；订单 = 内容物**；可在容器间转移 | 急单优先级高于合同分配，物理机台 ≠ 合同 |
| 横向拖拽落点 | 被挤掉的合同 → 挂起合同池 | 被挤掉的合同 → **弹窗选择一个空容器机台落入** | 业务要求实时安置，不允许漂浮 |
| 挂起合同池 | 必须存在，超时告警 | **删除该模块**（V2.1 不再需要） | 横向拖拽改用即时落点机制 |
| 批次容量 | 每批 20 台 | **每批 27~30 台，总共固定 20 批** | 产线实际容量 27-30 台，扩大批次容量以提高排产效率 |
| 急单插入级联 | 无 | **急单插入级联：被顶掉的订单保持机型相同顺延到下一批，无匹配机型则继续往后查找** | 急单插入后要保证原订单不丢失，自动沿批次级联安置 |

---

## 1. 系统概述

### 1.1 系统定位

替代传统 Excel 线下排产模式，实现 **数据预测 → 沙盘推演 → 生产派工 → 现货掉落抢单** 全链路数字化闭环。

### 1.2 系统组成

- **预测引擎（Backend Cron + 实时重算）**：基于真实合同 + 交期 + 产能比例自动生成批次
- **老板工作台（PC Web）**：双 Tab 视图——Tab1 生产排程看板 / Tab2 预测沙盘
- **销售抢单端（微信小程序）**：接收实时现货推送，区域限制性抢单

### 1.3 核心业务原则（开发硬约束）

| 序号 | 原则 | 落地点 |
|---|---|---|
| P1 | 整批生产、整批完工 | 产线只接受整批分配，MES Webhook 触发整批完工 |
| P2 | 机台是容器，订单是内容物 | 看板拖拽改单只移动订单字段，不移动 unit_id |
| P3 | 零损耗 | 任何拖拽不可物理删除合同，必须显式落点 |
| P4 | 数据锁定优先级：人工 > 算法 | Cron / 实时重算遇到 `is_locked=true` 必跳过 |
| P5 | 区域权限硬拦截 | 后端接口层校验 `region`，不依赖前端隐藏 |
| P6 | Cron 与编辑并发安全 | DB 行级锁 + 状态先查后写 |

---

## 2. 功能模块详述

### 2.1 预测引擎

#### 2.1.1 数据来源

- **真实合同源**：现有 `factory_plan` 表（合同号 / 机型 / 排产数量 / 要求交期 / 状态 / 客户名 / 代理商 / 指定批次/来源）
- **机型字典**：现有 `model_dictionary` 表（model_name / sort_order / enabled）
- **过滤条件**：`factory_plan.状态` IN ('待排产', '已排产但未锁定') 且 `要求交期` 非空

> 现有库 `要求交期` 字段类型为 `varchar`，需在 ETL 阶段统一转为 `DATE`，无效值进异常表。

#### 2.1.2 批次切分规则

切分算法（按交期升序遍历）：

```
sorted_units = factory_plan 中所有待排产台数，按 要求交期 升序展开（每"排产数量=N"展开为 N 行）
batch = []
batches = []
prev_due = null
MAX_BATCHES = 20

for unit in sorted_units:
    if batch is not empty:
        # 规则 A（高优先）：跨月断批
        if (unit.要求交期 - prev_due) > 30 天:
            batches.append(batch); batch = []
        # 规则 B：满 27-30 台断批
        elif len(batch) >= 27:
            batches.append(batch); batch = []
    batch.append(unit)
    prev_due = unit.要求交期

# 收尾：最后一个未满批次
if batch is not empty:
    if len(batches) < MAX_BATCHES:
        batches.append(batch)
    else:
        # 超过 20 批，剩余机台追加到最后一批
        batches[MAX_BATCHES - 1].extend(batch)
```

> ⚠ 规则 A 优先级高于规则 B：若第 15 台与第 16 台交期间隔超 30 天，第 15 台所在批就此封批，即使未满 27 台。批次总数固定为 20 批，超过 20 批后剩余机台全部追加到最后一批。

#### 2.1.3 产能比例与自动填充

**机型比例配置**：

- 前端提供可视化配置项：列出 `model_dictionary` 中 `enabled=1` 的所有机型
- 用户为每类机型设置百分比（整数，sum = 100）
- 配置入 `system_config` 表，键 = `capacity_ratio`，值 = JSON：
  ```json
  { "A": 40, "B": 35, "C": 25 }
  ```

**批次内填充逻辑**（关键）：

每批 27~30 台中可分为两类：

1. **合同指定台数**（来自 `factory_plan.指定批次/来源` JSON 中显式指定的合同行）—— 机型已确定，**进入批次后即在此批内固定，不参与比例重算**（但批次未发布前仍可被人工拖出）
2. **空槽自动填充台数** = 27~30 − 合同指定台数 —— 由算法按当前 `capacity_ratio` 趋近分配

**趋近算法（伪码）**：

```
BATCH_CAPACITY = 27  # 基准容量，实际允许 27~30
target_count[model] = round(BATCH_CAPACITY * ratio[model] / 100)   # 目标台数
fixed_count[model] = 已被合同指定的该机型台数                     # 已固定台数
remaining[model] = max(0, target_count[model] - fixed_count[model])
slot_total = BATCH_CAPACITY - sum(fixed_count.values())

# 若 sum(remaining) ≠ slot_total，按 (target - fixed) / sum(target - fixed) 等比缩放后再 round
# 取整余数：差几台就补/扣到目标比例偏差最大的机型
```

> ⚠ "趋近"而非"严格等于"：因为合同指定台数已固定，剩余空槽不一定能让最终比例完全匹配目标。算法目标是**让该批整体机型分布尽可能逼近目标比例**。

#### 2.1.4 触发机制

| 触发场景 | 动作 |
|---|---|
| Cron Job（每 1 小时） | 全量扫描，重新切分批次 + 重算各批次空槽机型 |
| 调整产能比例（Tab2 顶部组件） | **立即重算所有未发布批次**（status=Predicted）的空槽机型，已锁机台跳过 |
| 沙盘拖拽换批（Tab2） | **仅重算源批 + 目标批**两批的空槽机型，已锁机台跳过 |
| 信息强改（Tab2，编辑某机台机型/合同号/客户等） | 仅修改该机台，置 `unit.is_locked = true`，**同批其他空槽立即重算**以维持比例趋近 |
| 审核通过（Tab2） | 批次 status: Predicted → Confirmed，从 Tab2 视图移除，进入 Tab1 待排产队列 |

#### 2.1.5 Lock 机制（V2.1 新规则）

**Lock 粒度**：单机台级。

| 字段位置 | 字段 | 含义 |
|---|---|---|
| `units` 表 | `is_locked` BOOL DEFAULT false | true = 该机台所有字段不可被算法覆盖 |
| `units` 表 | `locked_by` VARCHAR | 锁定操作人（审计用） |
| `units` 表 | `locked_at` DATETIME | 锁定时间戳 |

**触发 Lock 的操作**（仅一种）：

- 在 Tab2 沙盘对**单台机**点击"信息强改"并修改任意字段（机型 / 合同号 / 客户 / 代理商等）→ 该机台 `is_locked = true`

**不触发 Lock 的操作**：

- 拖拽换批：仅改变 `unit.batch_id`，不锁机台。源批与目标批的空槽机台立即按比例重算
- 调整产能比例：不锁任何机台
- 横向拖拽改单（Tab1）：在容器间转移订单内容，不影响 Lock 状态

**解锁**：管理员手动解锁按钮（机台卡片右键菜单），二次确认后 `is_locked = false`。

> ⚠ Cron 与实时重算执行时，对 `is_locked = true` 的机台**完全跳过**，不读不写。

#### 2.1.6 并发安全

- Cron 执行 + 前端编辑可能并发：DB 操作统一使用 `SELECT ... FOR UPDATE` 行级锁
- 重算是**幂等**操作：以 `batch_id` 为粒度加 Redis 锁 `lock:batch:{batch_id}`，TTL = 30s

---

### 2.2 Tab2 — 预测沙盘

#### 2.2.1 页面布局

```
┌────────────────────────────────────────────────────┐
│  顶部：产能比例配置组件（机型 → 百分比，sum=100） │ ← 修改后立即触发全量重算
├────────────────────────────────────────────────────┤
│  批次列表（横向滚动卡片流，每批 27~30 台，共 20 批，展开/折叠）   │
│  ┌────────────────────────────┐                   │
│  │  第 1 批 / 共 27~30 台，共 20 批 / 交期: 06-01 ~ 06-15      │
│  │  机型分布：A:11 / B:9 / C:7（目标 11/9/7 ✓）  │
│  │  ┌──┬──┬──┬──┬──┬──┐                          │
│  │  │1 │2 │3 │🔒│5 │..│ ← 🔒 = is_locked=true   │
│  │  └──┴──┴──┴──┴──┴──┘                          │
│  │  [审核通过]                                    │
│  └────────────────────────────┘                   │
│  ...                                              │
└────────────────────────────────────────────────────┘
```

#### 2.2.2 操作清单

| 操作 | UI 入口 | 后端动作 |
|---|---|---|
| 调整产能比例 | 顶部输入框 + [应用] 按钮 | `PATCH /capacity-ratio` → 触发全量未发布批次重算 |
| 拖拽机台换批 | 直接拖卡片到目标批次 | `POST /units/:id/move-batch` → 源批 + 目标批重算空槽 |
| 信息强改单台 | 双击卡片打开编辑抽屉 → 保存 | `PATCH /units/:id` → 设 `is_locked=true`，本批其他空槽重算 |
| 解锁单台 | 卡片右键 → "解锁" → 二次确认 | `PATCH /units/:id/unlock` → `is_locked=false` |
| 单批审核通过 | 批次卡片底部 [审核通过] | `POST /batches/:id/confirm` |
| 多批审核通过 | 顶部勾选多批 + [批量审核通过] | `POST /batches/batch-confirm` |

#### 2.2.3 审核通过流转

- 批次 `status` 变更为 `Confirmed`
- Tab2 视图移除该批
- Tab1 待排产队列追加该批
- 同步生成 `audit_log` 记录（user / ip / timestamp / batch_id）

---

### 2.3 Tab1 — 生产排程看板

#### 2.3.1 核心数据模型（重要变更）

**机台 = 容器；订单 = 内容物。**

| 实体 | 角色 | 永不改变的字段 | 可被搬运的字段 |
|---|---|---|---|
| `unit`（机台/容器） | 物理槽位 | `unit_id`, `serial_no`（流水号）, `model_type`（机型，由生产决定）, `production_line_id` | — |
| `unit` 上的"订单内容" | 经销商订单信息 | — | `contract_no`, `customer`, `dealer_id`, `sales_id`, `order_remark` |

> ⚠ 拖拽改单**只移动订单字段**（`contract_no` / `customer` / `dealer_id` / `sales_id` / `order_remark`），**不移动 `unit_id`**，更不交换物理产线位置。

#### 2.3.2 页面布局

```
┌──────────────────────────────────────────────┬──────────────┐
│  左侧：20 条产线监控（横向并列）              │ 右侧：       │
│                                              │ 待排产队列   │
│  产线 1:  [批#3 ▼] 机1 机2 机3 ...          │ ┌──────────┐│
│           A合同 B合同 (空) ...               │ │第 5 批   ││
│  产线 2:  [批#4 ▼] 机21 机22 ...            │ │共 27~30 台││
│           ...                                │ │[整批分配] ││
│  产线 3:  [空闲]   ← 可接受新批              │ ├──────────┤│
│  ...                                         │ │第 6 批   ││
│  产线 20: [批#7 ▼]                           │ │...       ││
│                                              │ └──────────┘│
└──────────────────────────────────────────────┴──────────────┘
```

#### 2.3.3 整批分配（右侧 → 左侧）

- 仅支持**整批拖拽**或**整批点击 [分配] 按钮**到空闲产线
- **禁止拆分批次**（前端拖拽时不允许拆单台）
- 分配后产线 `status` = `Busy`，`current_batch_id` = 该批
- 后端：`POST /production-lines/:id/assign` body = `{ batch_id }`

#### 2.3.4 横向拖拽改单（V2.1 重构核心）

**场景**：急单（B 合同）需要插入到正在生产中的产线 X 上。

**操作流程**：

```
Step 1: 用户从右侧待排产队列 / 其他产线 / 急单输入入口
        拖拽急单卡片 B 到产线 X 的目标机台 A 上

Step 2: 系统校验：
        - 机台 A 的 model_type 是否与急单 B 的需求机型匹配？
          → 不匹配则弹错"机型不匹配，无法落入此机台"，操作中止
        - 机台 A 当前是否已锁定（is_locked=true）？
          → 已锁定弹错"机台已锁，请先解锁"，操作中止

Step 3: 触发"急单覆盖确认弹窗"，展示：
        - 目标机台 A 当前订单内容（合同 / 客户 / 代理商）
        - 急单 B 订单内容
        - 提示语："急单 B 将覆盖机台 A 的当前订单。
                  原订单 A 需要落入哪台空机台？"

Step 4: 系统弹出"空容器选择面板"：
        - 列出所有 contract_no IS NULL 且 model_type = A.model_type 且 is_locked=false 的机台
        - 按产线 + 批次顺序排列，可搜索、可筛选
        - 用户必须选择 1 台作为原订单 A 的新落点（不可跳过）

Step 5: 用户点击 [确认覆盖]，事务执行：
        BEGIN;
        UPDATE units SET contract_no, customer, dealer_id, sales_id, order_remark
                          = (急单 B 的字段)
        WHERE unit_id = A.unit_id;

        UPDATE units SET contract_no, customer, dealer_id, sales_id, order_remark
                          = (原 A 的字段)
        WHERE unit_id = 用户选定的空容器.unit_id;

        INSERT INTO sys_operation_log (...);
        COMMIT;

Step 6: 推送事件：
        - 'unit:updated' to 工作台所有打开 Tab1 的用户
        - 该急单 B 在原位置的卡片自动消失（如果是从其他产线拖来，源位置变空）
```

**异常分支**：

| 异常场景 | 处理 |
|---|---|
| 没有任何空容器可选 | 弹错"当前无可用空容器，请先释放或调整其他订单"，急单覆盖操作回滚 |
| 用户在弹窗中点击 [取消] | 整个操作回滚，机台 A 订单内容不变 |
| 弹窗选择期间，候选空容器被其他人抢占 | 提交时校验，若已被占用，前端刷新候选列表并提示重新选择 |

> ⚠ 与 V2.0 区别：**V2.0 中被挤掉的合同进入"挂起合同池"等待二次绑定**；V2.1 要求**当场选定落点机台，不允许漂浮**。挂起池模块已废弃。

#### 2.3.5 急单插入级联逻辑（V2.1 新增）

当急单插入某个批次的特定机台时，该机台原有的订单不会被丢弃，而是按照级联算法自动顺延到后续批次中同机型的机台位置。

**级联算法**：

```
function cascade(pushedOrder, batchIndex):
    // 超过 20 批，追加到最后一个批次
    if batchIndex > 20:
        将 pushedOrder 追加到 batches[19]（第 20 批）末尾
        return

    batch = batches[batchIndex]

    // 在当前批次中查找同机型的机台
    matchSlot = batch 中 model == pushedOrder.model 的机台

    if matchSlot 不存在:
        // 当前批无匹配机型，继续往后找
        cascade(pushedOrder, batchIndex + 1)
    else if matchSlot 无指定订单（空闲机台）:
        // 直接写入空闲槽位
        write pushedOrder → matchSlot
    else:
        // 该槽位有订单，顶掉并级联
        replacedOrder = matchSlot 的当前订单
        write pushedOrder → matchSlot
        cascade(replacedOrder, batchIndex + 1)
```

**级联规则说明**：

| 规则 | 说明 |
|---|---|
| 机型匹配优先 | 被顶掉的订单必须落入同机型的机台，不允许跨机型安置 |
| 逐批级联 | 当前批找不到匹配槽位时，自动尝试下一批，直到找到为止 |
| 批次上限保护 | 级联到第 20 批仍无匹配空槽时，直接追加到第 20 批末尾 |
| 级联链 | 一次急单插入可触发多级级联（A 顶 B，B 顶 C，C 顶 D …），算法递归处理 |
| 无空闲槽位 | 若级联到最后一台同机型机台（该机台亦有订单），则该订单被强行顶掉并追加到第 20 批末尾 |

> ⚠ 级联过程中不触发 Lock 机制，不写 `is_locked`。被级联的订单移动仅改变 `batch_id` 和 `slot_index`，不影响合同内容的完整性。

**示例场景**：

```
假设：
  批次 1：slot 3 是机型 A，当前订单 = 合同#001
  批次 2：slot 5 是机型 A，当前订单 = 合同#002
  批次 3：slot 2 是机型 A，当前为空

急单 X（机型 A）插入批次 1 的 slot 3：
  Step 1：急单 X 覆盖 slot 3 → 合同#001 被顶掉
  Step 2：级联合同#001 到批次 2 → 找到 slot 5（机型 A），已占合同#002
          合同#001 覆盖 slot 5 → 合同#002 被顶掉
  Step 3：级联合同#002 到批次 3 → 找到 slot 2（机型 A），为空
          合同#002 写入 slot 2 → 级联结束
```

#### 2.3.6 完工流转

- **MES Webhook**（详见 2.4）触发
- 兜底：管理员可点击产线卡片 [手动完工] 按钮（仅生产环境管理员角色可见）
- 完工后：批次 `status` = `Completed`，产线 `status` = `Idle`，`current_batch_id` = NULL

---

### 2.4 MES 对接 — 完工信号 Webhook

#### 2.4.1 接口定义

- **端点**：`POST /webhook/mes/completion`
- **认证**：HMAC-SHA256 签名，header `X-MES-Signature`
- **签名算法**：`HMAC-SHA256(body, shared_secret)`，shared_secret 存于 `system_config.mes_webhook_secret`
- **幂等**：同一 `(batch_id, event)` 5 分钟内重复调用直接返回 200，不重复处理

#### 2.4.2 请求体规范（待 MES 方最终确认）

```json
{
  "batch_id": "BATCH-2025-001",
  "event": "batch_completed",
  "units": [
    { "serial_no": "SN20250601001", "status": "warehoused" }
  ],
  "timestamp": "2025-06-01T10:00:00+08:00"
}
```

#### 2.4.3 处理逻辑

```
1. 验证 HMAC 签名 → 失败返回 401
2. 查询 batch_id 是否存在 → 不存在返回 404
3. 幂等检查（Redis: SETNX webhook:{batch_id}:{event}, TTL=300）
4. 逐台 UPDATE units SET status='In_Warehouse' WHERE serial_no IN (...)
5. 检查该批所有 units 是否均为 In_Warehouse
   → 是：UPDATE batches SET status='Completed';
         UPDATE production_lines SET status='Idle', current_batch_id=NULL;
   → 否：仅更新机台状态
6. 推送 'batch:completed' 事件到 Tab1 WebSocket
7. 写入 sys_operation_log
```

> ⚠ MES 接入前，所有完工操作走管理员"手动完工"按钮兜底。

---

### 2.5 销售抢单小程序

#### 2.5.1 现货来源

V2.1 中**唯一**产生现货的场景：**人工在 Tab1 显式将某机台标记为现货**（操作菜单 [转为现货]）。

> 与 V2.0 差异：V2.0 中"放空操作 → 自动现货"已被 V2.1 横向拖拽改单替代（被挤订单必须落到指定空容器，而不会自动变现货）。**只有管理员显式操作才能产生现货**。

#### 2.5.2 推送

- WebSocket 频道：`/ws/spot-inventory`
- 事件：`spot:new`（新增）/ `spot:claimed`（被抢）/ `spot:revoked`（撤回）
- 推送延迟目标：< 500ms

#### 2.5.3 区域拦截

- `users.region` 新增字段（VARCHAR），值域：`guangdong` / `non_guangdong` / 其他
- 后端在 `GET /spot-inventory` 与 `POST /spot-inventory/:id/claim` 接口入口判断 `req.user.region`
- `region = guangdong` → 直接 403，错误码 `REGION_BLOCKED`
- 前端不展示抢单 Tab，但**不依赖前端**

#### 2.5.4 抢单并发控制

- Redis: `SET NX EX spot:{unit_id} {user_id} 10`
- 加锁成功者：写入合同信息，推送 `spot:claimed`
- 加锁失败者：返回 HTTP 409，前端提示"已被抢走"

#### 2.5.5 合同回流

- 抢单成功 → 销售在小程序填写合同信息（合同号 / 客户 / 备注）
- 提交后写入对应 unit 的订单字段
- WebSocket 推送 `unit:updated` 到 Tab1

---

## 3. 数据模型（基于现有 `rjfinshed` 库扩展）

### 3.1 复用现有表

| 表 | 用途 | 是否需要 ALTER |
|---|---|---|
| `factory_plan` | 真实合同源数据 | 否（只读） |
| `model_dictionary` | 机型字典 | 否 |
| `finished_goods_data` | 完工后归档（V2.1 中等价于"完工后机台快照"） | 否 |
| `sales_orders` | 销售订单（小程序抢单回写目标） | 否 |
| `audit_log` | 审计日志 | 否 |
| `sys_operation_log` | 操作日志 | 否 |
| `users` | 用户 | **是**：新增 `region` |
| `roles` / `role_permissions` | 角色权限 | 否 |
| `transaction_log` | 现货抢单流水 | 否 |

### 3.2 新增表

#### 3.2.1 `batches` 批次表

```sql
CREATE TABLE `batches` (
  `batch_id`            VARCHAR(64)  NOT NULL COMMENT '批次唯一标识，格式 BATCH-YYYYMM-NNN',
  `batch_no`            INT          NOT NULL COMMENT '第 N 批，展示用',
  `status`              VARCHAR(32)  NOT NULL DEFAULT 'Predicted'
                        COMMENT 'Predicted / Confirmed / In_Production / Completed',
  `due_date_start`      DATE         NULL COMMENT '本批最早交期',
  `due_date_end`        DATE         NULL COMMENT '本批最晚交期',
  `capacity_snapshot`   JSON         NULL COMMENT '生成时产能比例快照',
  `source`              VARCHAR(32)  NOT NULL DEFAULT 'algorithm'
                        COMMENT 'algorithm / manual',
  `production_line_id`  VARCHAR(64)  NULL COMMENT '已分配的产线，NULL 表示未分配',
  `created_at`          DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at`          DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP
                        ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`batch_id`),
  INDEX `idx_batches_status` (`status`),
  INDEX `idx_batches_line` (`production_line_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
```

#### 3.2.2 `units` 机台表（容器）

```sql
CREATE TABLE `units` (
  `unit_id`             VARCHAR(64)  NOT NULL COMMENT '机台唯一标识，UUID',
  `serial_no`           VARCHAR(100) NULL     COMMENT '流水号，关联 finished_goods_data',
  `batch_id`            VARCHAR(64)  NOT NULL COMMENT '所属批次',
  `slot_index`          INT          NOT NULL COMMENT '批内位置 1~30',
  `model_type`          VARCHAR(100) NOT NULL COMMENT '机型，关联 model_dictionary.model_name',
  `production_line_id`  VARCHAR(64)  NULL     COMMENT '当前产线，NULL=待排产',
  `status`              VARCHAR(32)  NOT NULL DEFAULT 'Pending'
                        COMMENT 'Pending / In_Production / In_Warehouse / Spot_Inventory / Sold',

  -- 订单内容（可被横向拖拽搬运）
  `contract_no`         VARCHAR(100) NULL COMMENT '合同号',
  `customer`            VARCHAR(255) NULL COMMENT '客户名',
  `dealer_id`           VARCHAR(64)  NULL COMMENT '经销商 ID',
  `sales_id`            VARCHAR(64)  NULL COMMENT '销售 ID',
  `order_remark`        VARCHAR(500) NULL COMMENT '订单备注',

  -- 锁定标记
  `is_locked`           TINYINT(1)   NOT NULL DEFAULT 0 COMMENT '1=锁定，算法跳过',
  `locked_by`           VARCHAR(100) NULL,
  `locked_at`           DATETIME     NULL,

  -- 来源标记
  `is_contract_pinned`  TINYINT(1)   NOT NULL DEFAULT 0
                        COMMENT '1=该机型由合同显式指定（factory_plan.指定批次/来源）',

  `created_at`          DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at`          DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP
                        ON UPDATE CURRENT_TIMESTAMP,

  PRIMARY KEY (`unit_id`),
  UNIQUE KEY `uq_units_batch_slot` (`batch_id`, `slot_index`),
  INDEX `idx_units_batch` (`batch_id`),
  INDEX `idx_units_line_status` (`production_line_id`, `status`),
  INDEX `idx_units_locked` (`is_locked`),
  INDEX `idx_units_empty_container`
        (`status`, `contract_no`, `model_type`, `is_locked`)
        COMMENT '空容器查询索引：横向拖拽时高频使用',
  CONSTRAINT `fk_units_batch` FOREIGN KEY (`batch_id`) REFERENCES `batches`(`batch_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
```

#### 3.2.3 `production_lines` 产线表

```sql
CREATE TABLE `production_lines` (
  `line_id`             VARCHAR(64)  NOT NULL,
  `line_name`           VARCHAR(100) NOT NULL COMMENT '产线 1 ~ 产线 20',
  `current_batch_id`    VARCHAR(64)  NULL,
  `status`              VARCHAR(32)  NOT NULL DEFAULT 'Idle'
                        COMMENT 'Idle / Busy / Maintenance',
  `display_order`       INT          NOT NULL DEFAULT 0,
  `updated_at`          DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP
                        ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`line_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
```

#### 3.2.4 `system_config` 配置表

```sql
CREATE TABLE `system_config` (
  `config_key`   VARCHAR(100) NOT NULL,
  `config_value` TEXT         NULL,
  `description`  VARCHAR(255) NULL,
  `updated_by`   VARCHAR(100) NULL,
  `updated_at`   DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP
                 ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`config_key`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 初始化数据
INSERT INTO system_config VALUES
  ('capacity_ratio', '{"A":40,"B":35,"C":25}', '机型产能比例', 'system', NOW()),
  ('batch_size_max', '30', '单批最大台数', 'system', NOW()),
  ('batch_break_days', '30', '断批的交期间隔阈值（天）', 'system', NOW()),
  ('mes_webhook_secret', 'CHANGE_ME', 'MES Webhook HMAC 密钥', 'system', NOW());
```

### 3.3 ALTER 现有表

```sql
-- users 表新增区域字段
ALTER TABLE `users`
  ADD COLUMN `region` VARCHAR(50) NULL DEFAULT NULL
    COMMENT 'guangdong / non_guangdong' AFTER `name`,
  ADD COLUMN `wechat_openid` VARCHAR(100) NULL DEFAULT NULL
    COMMENT '小程序登录用' AFTER `region`,
  ADD INDEX `idx_users_region` (`region`),
  ADD INDEX `idx_users_openid` (`wechat_openid`);
```

### 3.4 实体关系图（文字版）

```
factory_plan (合同源数据)
       │
       │ 预测引擎读取并展开
       ▼
   batches  ───┬───►  units (容器，含订单内容字段)
       │      │
       │      └───►  units.is_locked  (Lock 标记)
       │
       └───►  production_lines.current_batch_id (整批分配后)
                       │
                       ▼
                 MES Webhook 完工 ───►  finished_goods_data (归档)

users.region  ───►  spot-inventory 接口区域拦截
sales_orders  ◄───  小程序抢单回写
```

---

## 4. 接口清单

### 4.1 PC 工作台接口

| 方法 | 路径 | 说明 | 权限 |
|---|---|---|---|
| GET | `/api/batches?status=Predicted` | 获取预测批次列表（Tab2） | admin |
| GET | `/api/batches?status=Confirmed&unassigned=true` | 获取待排产队列（Tab1 右侧） | admin |
| POST | `/api/batches/:id/confirm` | 单批审核通过 | admin |
| POST | `/api/batches/batch-confirm` | 多批审核通过，body `{ batch_ids: [] }` | admin |
| GET | `/api/capacity-ratio` | 获取当前产能比例 | admin |
| PATCH | `/api/capacity-ratio` | 更新比例，body `{ "A":40,"B":35,"C":25 }`，触发全量重算 | admin |
| POST | `/api/forecast/recompute` | 手动触发 Cron 重算（管理员调试用） | admin |
| PATCH | `/api/units/:id` | 信息强改，触发 `is_locked=true` + 同批空槽重算 | admin |
| PATCH | `/api/units/:id/unlock` | 解锁单台 | admin |
| POST | `/api/units/:id/move-batch` | 拖拽换批，body `{ target_batch_id }` | admin |
| POST | `/api/units/swap-content` | **横向拖拽改单核心接口** | admin |
| GET | `/api/units/empty-containers?model_type=A` | 查询匹配机型的空容器（弹窗候选列表） | admin |
| POST | `/api/units/:id/mark-spot` | 显式标记为现货 | admin |
| GET | `/api/production-lines` | 获取 20 条产线状态 | admin |
| POST | `/api/production-lines/:id/assign` | 整批分配，body `{ batch_id }` | admin |
| POST | `/api/production-lines/:id/manual-complete` | 手动完工兜底 | admin |

### 4.2 横向拖拽改单接口详细规范

**`POST /api/units/swap-content`**

请求 body：
```json
{
  "source_unit_id": "uuid-of-急单A的当前位置",
  "target_unit_id": "uuid-of-被覆盖的机台B",
  "fallback_unit_id": "uuid-of-用户选定的空容器C",
  "operator": "username",
  "reason": "急单插入"
}
```

后端事务：
```sql
BEGIN;

-- 1. 锁三台机台行，防止并发
SELECT * FROM units WHERE unit_id IN (source_unit_id, target_unit_id, fallback_unit_id) FOR UPDATE;

-- 2. 校验
--    a) target_unit.is_locked = false
--    b) fallback_unit.contract_no IS NULL（仍是空容器）
--    c) fallback_unit.model_type = target_unit.model_type
--    d) source_unit.model_type 与 target_unit.model_type 兼容（一般等同）

-- 3. 暂存原 target 的订单内容到变量
-- 4. 把 source 的订单内容覆盖到 target
-- 5. 把暂存的原 target 内容写入 fallback
-- 6. 清空 source 的订单内容（如果 source 是 Tab1 上的"急单卡片"原位置）
--    或如果 source 是临时录入的急单，则不需此步

-- 7. 写 sys_operation_log
INSERT INTO sys_operation_log (...);

COMMIT;
```

返回：
```json
{
  "success": true,
  "affected_units": [
    { "unit_id": "...", "contract_no": "...", "customer": "..." }
  ],
  "ws_pushed": true
}
```

错误码：

| HTTP | code | 含义 |
|---|---|---|
| 400 | `MODEL_TYPE_MISMATCH` | 机型不匹配 |
| 409 | `TARGET_LOCKED` | 目标机台已锁 |
| 409 | `FALLBACK_OCCUPIED` | 候选空容器已被占用，前端需刷新列表 |
| 422 | `NO_EMPTY_CONTAINER` | 同机型无可用空容器（前端需提前在弹窗阶段告知） |

### 4.3 小程序接口

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/spot-inventory` | 现货列表（含区域拦截） |
| POST | `/api/spot-inventory/:id/claim` | 抢单 |
| POST | `/api/sales/login` | 微信登录 |

### 4.4 Webhook 与 WebSocket

| 类型 | 端点 | 说明 |
|---|---|---|
| Webhook | `POST /api/webhook/mes/completion` | MES 完工回调（HMAC 签名） |
| WS | `/ws/workbench` | PC 工作台事件：`unit:updated`, `batch:updated`, `line:updated`, `batch:completed` |
| WS | `/ws/spot-inventory` | 小程序事件：`spot:new`, `spot:claimed`, `spot:revoked` |

---

## 5. 技术架构

| 层级 | 选型 | 说明 |
|---|---|---|
| PC 前端 | React + dnd-kit + Zustand | dnd-kit 处理两个核心拖拽场景：1) Tab2 跨批拖拽 2) Tab1 横向跨产线拖拽 + 弹窗候选选择 |
| 小程序 | Taro | 一套代码可扩多端 |
| 后端 | Node.js + NestJS | Cron + WebSocket + 事务 + DI |
| 实时推送 | Socket.io | 已选用，断线重连开箱即得 |
| 数据库 | **MySQL 8.0**（与现有 `rjfinshed` 库一致） | 注意：JSON 字段、行级锁、`SELECT ... FOR UPDATE` 均支持 |
| 缓存/锁 | Redis 7.x | 抢单 / 重算分布式锁 / Webhook 幂等键 |
| 部署 | Docker Compose | Nginx 反向代理 + 后端 + Redis + MySQL |

> ⚠ V2.0 PRD 中提到 PostgreSQL，V2.1 修正为**继续使用 MySQL**（与现有 `rjfinshed` 库一致），避免迁移成本。MySQL 8.0 完全支持 JSON、行级锁、CTE，业务上无差异。

### 5.1 非功能性需求

| 项 | 指标 |
|---|---|
| WebSocket 推送延迟 | < 500ms |
| 工作台并发 | < 10 用户 |
| 预测重算耗时 | 全量 < 5s（10000 台合同规模内） |
| 数据保留 | 完工批次永久归档至 `finished_goods_data` |
| Webhook 幂等 | Redis 5 分钟去重窗口 |

---

## 6. 开发计划

### 6.1 分期交付

| 期次 | 周期 | 交付内容 |
|---|---|---|
| **第一期** | 3 周 | 数据建模 (`batches` / `units` / `production_lines` / `system_config`) + 用户表 ALTER + 预测引擎（断批 + 比例填充 + Cron + 实时重算） + Tab2 沙盘（基础列表 + 比例配置 + 拖拽换批 + 信息强改 + 解锁 + 审核通过） |
| **第二期** | 3 周 | Tab1 看板（产线监控 + 待排产队列 + 整批分配 + 横向拖拽改单弹窗 + 空容器选择面板 + 显式转现货） + 操作日志 |
| **第三期** | 2 周 | Socket.io 双频道 + 抢单小程序（含区域拦截 + Redis 抢单锁 + 合同回流） + MES Webhook + 手动完工兜底 |
| **横切贯穿** | 全程 | JWT 鉴权 + 角色权限 + 区域拦截后端校验 + 系统配置后台 |

### 6.2 高风险项与对齐事项

| 风险项 | 等级 | 应对 |
|---|---|---|
| 比例趋近算法的取整规则 | 🔴 高 | 第一期开发前由业务方书面确认：差额优先补给"目标偏差最大"还是"机型字典 sort_order 最小"？ |
| 横向拖拽弹窗 UI 体验（候选机台数量大时） | 🔴 高 | 第二期启动前 1~2 天 spike：候选 > 100 台时分页 + 搜索；< 20 台时直接列表 |
| MES Webhook 字段格式 | 🟡 中 | 在 V2.1 通过前安排 MES 方接口对齐会议 |
| Cron 与人工编辑并发 | 🟡 中 | DB 行级锁 + Redis 批次锁双保险 |
| 急单插入时无空容器 | 🟡 中 | 弹窗阶段就阻断，给业务清晰话术（"请先在 Tab1 释放某机台或转为现货"） |
| `factory_plan.要求交期` 字段类型为 varchar | 🟡 中 | ETL 阶段强制转 DATE，无效值进异常表，定期人工核对 |

---

## 7. 业务规则 Dev-Checklist（代码评审硬核查项）

- [ ] **整批入线**：禁止单台拆分进产线
- [ ] **机台 = 容器**：拖拽改单只 UPDATE 订单字段，不改 `unit_id` / `production_line_id` / `model_type`
- [ ] **零损耗**：`POST /api/units/swap-content` 必须强制传 `fallback_unit_id`，不传报 400
- [ ] **机型匹配硬校验**：覆盖前必须 `source.model_type == target.model_type == fallback.model_type`
- [ ] **Lock 优先级**：Cron / 实时重算遇到 `is_locked=true` 跳过，对应单元测试必须覆盖
- [ ] **断批规则**：交期间隔 > `system_config.batch_break_days` 必断批，单元测试覆盖临界值
- [ ] **比例趋近**：测试 case 包括"合同指定台数 > 目标台数"等极端场景
- [ ] **区域拦截**：`/api/spot-inventory` 接口层校验 `req.user.region`，单元测试模拟 guangdong 用户必返回 403
- [ ] **抢单并发**：Redis SET NX EX 测试用例必须覆盖 100 并发抢同一台
- [ ] **Webhook 幂等**：5 分钟窗口内重复调用必须返回 200 且不重复处理
- [ ] **审计日志**：所有 PATCH / POST 接口写入 `sys_operation_log`

---

## 附录 A：待确认事项（开发启动前必须回签）

| # | 问题 | 影响范围 | 负责确认方 |
|---|---|---|---|
| 1 | 比例趋近算法差额分配规则（目标偏差最大 / 字典序） | 预测引擎 | 产品 + 业务 |
| 2 | `factory_plan.指定批次/来源` JSON 的具体结构（如何解析"指定到第 N 批"） | 预测引擎 | 业务 + DBA |
| 3 | MES Webhook 字段格式、签名机制、事件类型 | 完工模块 | MES 厂商 |
| 4 | 区域字段除 guangdong 外的具体值域 | 区域拦截 | 业务 |
| 5 | 历史 Excel 数据是否需迁移作为初始批次 | 上线方案 | 业务 |
| 6 | 急单的录入入口（直接在 Tab1 录入？还是必须先进 Tab2 走预测流程？） | 看板交互 | 产品 |
| 7 | 解锁权限是否仅限超级管理员，还是普通管理员也可解锁 | 权限矩阵 | 业务 |

---

## 附录 B：关键流程图（文字版）

### B1：横向拖拽改单流程

```
[用户拖拽急单 B 到机台 A]
            │
            ▼
   ┌─────────────────────┐
   │  前端校验：         │
   │  - 机型匹配？        │
   │  - target 是否锁定？ │
   └─────────────────────┘
            │
       ┌────┴────┐
      失败      通过
       │         │
       ▼         ▼
    弹错      调用 GET /units/empty-containers?model_type=A
    中止           │
                   ▼
           ┌────────────────────┐
           │ 弹窗：             │
           │  - 显示 A 当前订单  │
           │  - 显示急单 B 内容  │
           │  - 候选空容器列表   │
           └────────────────────┘
                   │
              ┌────┴────┐
            取消      选定 fallback C
              │           │
              ▼           ▼
            回滚    POST /units/swap-content
                    { source: B位置, target: A, fallback: C }
                          │
                          ▼
                    ┌────────────┐
                    │ 后端事务：  │
                    │  锁 3 行   │
                    │  二次校验  │
                    │  互换字段  │
                    │  写日志    │
                    │  推送 WS   │
                    └────────────┘
                          │
                          ▼
                       前端刷新
                       UI 上 A 显示 B 内容
                          C 显示原 A 内容
```

### B2：预测引擎重算流程

```
触发源：Cron / 比例变更 / 拖拽换批 / 信息强改
                    │
                    ▼
     ┌──────────────────────────────┐
     │  确定影响范围：              │
     │  - Cron：所有 status=Predicted │
     │  - 比例：所有 status=Predicted │
     │  - 换批：源批 + 目标批         │
     │  - 强改：本批                  │
     └──────────────────────────────┘
                    │
                    ▼
     ┌──────────────────────────────┐
     │  对每个目标批次：            │
     │  Redis lock:batch:{id}        │
     │    SELECT FOR UPDATE          │
     │    跳过 is_locked=true 机台   │
     │    跳过 is_contract_pinned    │
     │      的合同指定机台          │
     │    剩余空槽按比例趋近重算    │
     │    UPDATE units 机型          │
     │  释放 Redis lock              │
     └──────────────────────────────┘
                    │
                    ▼
              推送 WS batch:updated
```

---

> 文档结束。本 V2.1 经业务重述与现有 SQL 库结构对齐，可直接进入开发评审与排期。
