# 智能排产系统 V3.0

智能排产系统 V3.0 是一个面向制造排产场景的 Web 工作台，用于根据订单、机型、产能和批次规则生成预测批次，并支持在预测沙盘中人工调整、审核确认、分配产线和生产跟踪。

系统提供两个核心工作区：

- **生产看板**：查看产线状态、待排产批次、生产中批次，并将确认后的批次分配到空闲产线。
- **预测沙盘**：生成和调整未来批次计划，支持拖拽改单、批次审核、机型过滤、比例配置和异常修复。

## 主要功能

### 1. 登录与权限控制

- 支持账号密码登录。
- 前端只允许 `admin` / `boss` 角色进入老板工作台。
- 请求会携带 Token、用户名和角色信息，由后端接口进行权限校验。

### 2. 预测沙盘

预测沙盘用于查看和调整系统生成的预测批次。

主要能力：

- **全量重算**：重新生成预测批次和机台排布。
- **生成下一批**：按指定机型类生成新的后续批次。
- **批次过滤**：按机型类、具体机型筛选批次。
- **批次审核**：支持勾选多个预测批次并批量审核。
- **卡片拖拽调整**：在批次之间拖拽机台卡片，调整排产位置。
- **信息强改**：可编辑卡片的合同号、客户、经销商、机型和备注，并保存为锁定状态。
- **现货标记**：可将卡片标记为现货。
- **解锁卡片**：对已锁定卡片执行解锁。
- **一键修复串机型**：修复批次内机型类不一致的问题。
- **容量比例配置**：通过沙盘顶部组件调整容量/备货比例相关配置。

### 3. 固定批次列顺序

预测沙盘中的批次列顺序使用 `forecast_batch_slots.slot_no` 固定排序。

这样可以避免把交期较早的卡片拖入目标批次后，因为目标批次的交期范围变化导致整列立即跳位，提升人工拖拽调整时的确认感。

排序规则：

1. 优先使用 `forecast_batch_slots.slot_no`。
2. 如果没有 `slot_no`，回退使用 `batches.batch_no`。

### 4. 卡片溢出级联后推

当卡片拖入目标批次后，如果目标批次超过容量，系统会按固定批次顺序执行级联后推。

规则：

- 溢出卡片只会推入同一机型类的后续预测批次。
- 后推顺序按 `forecast_batch_slots.slot_no` 从前到后执行。
- 如果下一个批次也满了，会继续挤出该批次末尾卡片，继续向后推。
- 如果已经没有后续可承接批次，则进入待处理队列。

该机制保证人工插入卡片后，不会直接拒绝操作，也不会随意插入不同机型类批次。

### 5. 生产看板

生产看板用于查看实际生产执行状态。

主要能力：

- **产线监控**：展示所有产线的空闲/忙碌状态和当前生产内容。
- **待排产批次**：展示已确认、待分配到产线的批次。
- **整批分配**：将待排产批次分配到空闲产线。
- **生产中批次**：展示正在生产的批次，并可跳转到对应产线。
- **手动完工**：对忙碌产线执行手动完工操作。
- **实时刷新**：通过 WebSocket 接收后端事件，更新看板状态。

### 6. 加急订单处理

系统支持加急订单录入和插入。

主要能力：

- 新增加急订单。
- 选择空容器/空位进行人工插入。
- 自动寻找合适位置插入。
- 加急订单信息包括合同号、客户、机型、经销商和交期。

### 7. 批次管理

批次具有完整的状态流转：

- `Predicted`：预测生成，待审核。
- `Confirmed`：已审核，待分配生产线。
- `In_Production`：生产中。
- `Completed`：已完成。

支持能力：

- 查询批次列表。
- 查询批次详情和机台明细。
- 单批审核。
- 批量审核。
- 分配产线。
- 手动完工。
- 插入空位。

### 8. 机台卡片管理

机台卡片代表批次中的具体排产单元。

支持能力：

- 查询机台详情。
- 修改合同号、客户、经销商、机型、备注等信息。
- 批次内重新排序。
- 跨批次移动。
- 内容交换。
- 锁定/解锁。
- 标记现货。
- 查询空容器。

## 技术架构

### 前端

目录：`web/`

技术栈：

- Vue 3
- Vite
- Pinia
- Element Plus
- Axios
- vue-draggable-plus
- 原生 WebSocket

主要页面：

- `web/src/App.vue`：登录、顶部布局和页签入口。
- `web/src/views/ProductionKanban.vue`：生产看板。
- `web/src/views/PredictionSandbox.vue`：预测沙盘。
- `web/src/components/RushOrderEntry.vue`：加急订单入口。
- `web/src/components/UnitCard.vue`：机台卡片组件。

### 后端

目录：`server/`

默认后端为 Go 实现，同时保留 Node.js 兼容实现。

Go 技术栈：

- Go 1.22
- Gin
- GORM
- MySQL
- Redis 可选
- Gorilla WebSocket

Node.js 兼容后端技术栈：

- Express
- MySQL2
- Socket.IO
- JWT
- Redis 可选

主要 Go 模块：

- `server/cmd/main.go`：Go 后端入口。
- `server/internal/router`：API 路由注册。
- `server/internal/handler`：接口处理层。
- `server/internal/service`：业务服务层。
- `server/internal/repo`：数据库访问层。
- `server/internal/engine`：预测和排产算法相关逻辑。
- `server/internal/model`：数据库模型定义。
- `server/internal/ws`：WebSocket 实时通知。

### 数据库

数据库使用 MySQL。

核心表包括：

- `batches`：批次主表。
- `units`：批次内机台/订单卡片。
- `forecast_batch_slots`：预测批次固定槽位顺序。
- `production_lines`：生产线信息。
- `production_queue`：无法直接排入批次的待处理队列。
- `users`：登录用户。
- 其他配置表：机型、产能比例、排产参数等。

## API 概览

前端统一通过 `/api` 调用后端接口。

### 认证

- `POST /api/auth/login`：登录。
- `GET /api/auth/me`：获取当前用户。

### 批次

- `GET /api/batches`：获取批次列表。
- `GET /api/batches/:id`：获取批次详情。
- `GET /api/batches/:id/units`：获取批次机台。
- `POST /api/batches/:id/confirm`：审核单个批次。
- `POST /api/batches/batch-confirm`：批量审核批次。
- `POST /api/batches/generate-next`：生成下一批。
- `POST /api/batches/:id/insert-empty-slot`：插入空位。

### 机台/卡片

- `GET /api/units/:id`：获取机台详情。
- `PATCH /api/units/:id`：更新机台信息。
- `PATCH /api/units/:id/unlock`：解锁机台。
- `POST /api/units/:id/move-batch`：跨批次移动。
- `POST /api/units/:id/reorder-slot`：批次内重排。
- `POST /api/units/swap-content`：交换卡片内容。
- `POST /api/units/rush-insert`：插入加急订单。
- `GET /api/units/empty-containers`：查询空容器。
- `POST /api/units/:id/mark-spot`：标记现货。
- `POST /api/units/repair-family-mismatches`：修复串机型。

### 预测

- `POST /api/forecast/recompute`：全量重算。
- `GET /api/forecast/achievement`：获取预测达成情况。

### 产线

- `GET /api/production-lines`：获取生产线列表。
- `POST /api/production-lines/:id/assign`：分配批次到产线。
- `POST /api/production-lines/:id/manual-complete`：手动完工。

### 配置

- `GET /api/model-types`：获取机型列表。
- `GET /api/capacity-ratio`：获取容量比例配置。
- `PATCH /api/capacity-ratio`：更新容量比例配置。

## 启动方式

### 一键启动

项目根目录提供 `start-all.bat`。

默认启动 Go 后端和前端：

```bat
start-all.bat
```

显式启动 Go 后端：

```bat
start-all.bat go
```

启动 Node.js 兼容后端：

```bat
start-all.bat node
```

启动后访问：

```text
http://localhost:5173
```

### 单独启动前端

```bash
cd web
npm install
npm run dev
```

前端开发服务默认地址：

```text
http://localhost:5173
```

Vite 代理配置：

- `/api` -> `http://127.0.0.1:3001`
- `/ws` -> `ws://127.0.0.1:3001`

### 单独启动 Go 后端

```bash
cd server
go build -o smart-scheduling-server-go.exe ./cmd/main.go
./smart-scheduling-server-go.exe
```

Go 后端默认监听：

```text
http://127.0.0.1:3001
```

### 单独启动 Node.js 后端

```bash
cd server
npm install
npm run dev
```

## 环境配置

后端环境变量位于：

```text
server/.env
```

常见配置项：

```env
DB_HOST=localhost
DB_PORT=3306
DB_USER=root
DB_PASSWORD=your_password
DB_NAME=your_database
JWT_SECRET=change-me-in-production
REDIS_ENABLED=false
REDIS_HOST=localhost
REDIS_PORT=6379
PORT=3001
```

## 开发与验证

### 后端测试

```bash
cd server
go test ./internal/...
```

### 前端构建

```bash
cd web
npm run build
```

## 使用流程建议

1. 登录系统。
2. 进入预测沙盘。
3. 点击“全量重算”生成预测批次。
4. 根据机型类和具体机型筛选批次。
5. 在沙盘中拖拽卡片调整批次位置。
6. 检查批次容量、交期范围和机型分布。
7. 审核选中的预测批次。
8. 回到生产看板，将已审核批次分配到空闲产线。
9. 生产完成后执行手动完工。

## 重要业务规则

- 批次列顺序由 `forecast_batch_slots.slot_no` 固定，不随交期范围变化而跳动。
- 卡片跨批次移动必须满足同机型类约束。
- 备货卡片（无合同号）不允许跨批次拖拽移动。
- 目标批次满员时触发级联后推。
- 后推只发生在同机型类的后续预测批次中。
- 没有后续可承接批次时，溢出卡片进入待处理队列。
- 已锁定卡片需要先解锁后才能进行部分修改或调整。
- 信息强改后卡片自动锁定，防止被重算覆盖。
- 批次审核时需要手动输入批次号（格式 `MM-SS`），每次只能审核一列。
- 角色比较必须大小写不敏感（数据库中为首字母大写如 `Admin`、`Boss`）。

## 排序规则

系统中共有 10 个主要排序场景和多个隐含排序点，下表为完整速查。

### 排序规则速查表

| # | 排序场景 | 排序键 | 方向 | 位置 |
|---|---|---|---|---|
| 1 | 批次列排序（跨列） | `slot_no` → `batch_no` | ASC | `batch_repo.go` / `PredictionSandbox.vue` |
| 2 | 批次内卡片排序（列内） | `sort_order` → 机型名 → `slot_index` | ASC | `predictor.go` / `unit.go` |
| 3 | 合同读取排序 | `due_date` → `contract_no` | ASC | `contract_repo.go` |
| 4 | 合同交期分组排序 | `due_date` | ASC | `predictor.go` |
| 5 | 空位模型名排序 | 字符串字母序 | ASC | `predictor.go` / `unit.go` |
| 6 | 空位比例分配顺序 | `ratio` 百分比 | DESC | `predictor.go` / `unit.go` |
| 7 | 比例余数分配 | 小数部分 | DESC | `predictor.go` |
| 8 | 无合同卡片重平衡排序 | `slot_index` → `unit_id` | ASC | `unit.go` |
| 9 | 机型列表排序（API） | `sort_order` → `model_name` | ASC | `meta.go` |
| 10 | 前端批次内卡片排序 | `slot_index` | ASC | `PredictionSandbox.vue` |

### 1. 批次列排序（跨列顺序）

预测沙盘中的批次列顺序由 `forecast_batch_slots.slot_no` 固定，不再按交期范围动态排序。

排序规则：

1. 优先使用 `forecast_batch_slots.slot_no` 升序。
2. 如果批次没有关联 slot 记录，回退使用 `batches.batch_no` 升序。
3. 前端 `batchSlotOrder()` 函数和后端 `COALESCE(fbs.slot_no, batches.batch_no) ASC` 保持一致。

后端实现（`batch_repo.go`）：

```go
// 批次列表查询和级联后推时获取预测批次，统一使用此排序
Order("COALESCE(fbs.slot_no, batches.batch_no) ASC")
```

前端实现（`PredictionSandbox.vue`）：

```javascript
function batchSlotOrder(batch) {
  const slotNo = Number(batch?.forecast_slot_no)
  if (Number.isFinite(slotNo) && slotNo > 0) return slotNo
  return Number(batch?.batch_no || 0)
}
// filteredBatches computed 中按此函数排序，二级键为 batch_no ASC
```

这样做的目的是：当用户把交期靠前的卡片拖入目标批次后，目标批次的交期范围虽然提前了，但列的位置不会跳动，保证操作确认感。

### 2. 批次内卡片排序（列内顺序）

批次内的机台卡片按 `model_dictionary` 表中的 `sort_order` 字段排序。

排序规则（`sortOneBatchByModelDictionary` / `sortAndReindexUnitsByModelDictionary`）：

1. 每张卡片的 `model_type` 在 `model_dictionary` 中查找对应的 `sort_order`，得到排序权重 `modelSortRank`。
2. 如果 `model_dictionary` 中没有该机型，权重默认为 `1,000,000`（排到最后）。
3. 先按 `sort_order` 升序排列。
4. `sort_order` 相同时，按机型名称字母序排列（`normalizeModelKey` 转大写后比较）。
5. 机型名称也相同时，按 `slot_index` 升序排列。
6. 排序后重新分配 `slot_index`（从 1 开始连续编号）。

实现位置：

- 全量重算时：`server/internal/engine/predictor.go` 的 `sortAndReindexUnitsByModelDictionary()` 函数。
- 拖拽移动后：`server/internal/handler/unit.go` 的 `sortOneBatchByModelDictionary()` 函数。
- 两处实现逻辑完全一致，排序后通过 `RewriteBatchAssignments()` 写回数据库。

排序权重加载：

```go
// 从 model_dictionary 表加载排序权重（只读 enabled = 1 的条目）
// 同一 model_name 大小写归一化后相同时，取最小的 sort_order 值
SELECT model_name, sort_order FROM model_dictionary WHERE enabled = 1
```

该排序在以下时机触发：

- 全量重算生成批次后。
- 卡片跨批次移动后，对涉及的源批次、目标批次和级联涉及的所有批次执行排序。

### 3. 合同读取排序

从 `factory_plan` 表读取有效合同时的初始排序（`contract_repo.go`）：

```sql
ORDER BY due_date ASC, contract_no ASC
```

交期靠前的合同优先处理，同交期按合同号字母序。

### 4. 合同交期分组排序

全量重算时，对每个机型类的合同按交期排序后再进行拆批（`predictor.go`）：

```go
sort.Slice(contracts, func(i, j int) bool {
    return contracts[i].DueDate.Before(contracts[j].DueDate)
})
```

虽然 SQL 已按 `due_date` 排序，但此处对归一化分组后的每个子集再次排序以确保正确性。

### 5. 空位模型名排序

批次空位填充时，将按比例生成的空位机型名按字母序排列，保证空位卡片顺序确定性：

```go
// predictor.go buildFilledUnits() 和 unit.go chooseFillModels()
sort.Strings(emptyModels)  // 例如: FR-400G, FR-500G, FR-600G
```

### 6. 空位比例分配顺序

`distributeEmptySlots` / `distributeByRatioForSlots` 中，按比例值降序处理尺寸键，高比例尺寸优先分配：

```go
sort.Slice(items, func(i, j int) bool { return items[i].ratio > items[j].ratio })
```

### 7. 比例余数分配

在 Level1（机型类比例）和 Level2（具体尺寸比例）分配中，向下取整后的余数按小数部分从大到小补给：

- 例如 `total=20, G:24%` → 精确值 4.8，取整 4，余数 0.8。
- `XS:76%` → 精确值 15.2，取整 15，余数 0.2。
- G 余数 0.8 > XS 余数 0.2 → G 先获得 +1 → 最终 G=5, XS=15。

### 8. 无合同卡片重平衡排序

拖拽后对涉及批次的无合同空位卡片重新分配机型时（`unit.go` `rebalanceSingleBatchUnboundUnitsByRatio`），先按位置排序以确定替换顺序：

```go
sort.SliceStable(unbound, func(i, j int) bool {
    if unbound[i].SlotIndex != unbound[j].SlotIndex {
        return unbound[i].SlotIndex < unbound[j].SlotIndex  // 1. slot_index ASC
    }
    return unbound[i].UnitID < unbound[j].UnitID             // 2. unit_id 字母序 ASC
})
```

### 9. 机型列表排序（API）

`GET /api/model-types` 接口返回的机型下拉列表（`meta.go`），排除 `G`、`XS`、`AUTO` 纯机型类名：

```go
Order("sort_order ASC, model_name ASC")
```

### 10. 前端批次内卡片排序

前端在加载/刷新数据后按 `slot_index` 排序（`PredictionSandbox.vue`）：

```javascript
function sortBatchUnitsInPlace(batches) {
  for (const b of (batches || [])) {
    b.units.sort((a, c) => Number(a.slot_index || 0) - Number(c.slot_index || 0))
  }
}
// 每次 refresh() 后立即调用
```

### 隐含排序点

| 场景 | 排序 | 位置 |
|---|---|---|
| 获取批次机台列表 | `slot_index ASC` | `unit_repo.go` `GetByBatch()` |
| 加锁读取批次机台 | `batch_id ASC, slot_index ASC` | `unit_repo.go` `ListByBatchIDsForUpdate()` |
| CompactSlots 重编号 | `slot_index ASC`（保持原序重编号） | `unit_repo.go` |
| ReorderBatchWithUnit | `slot_index ASC`（排除目标后重插入） | `unit_repo.go` |
| ReSlotBatch 重编号 | `slot_index ASC`（保持原序，重写 unit_id） | `unit_repo.go` |
| 空容器查询 | `slot_index ASC`，`LIMIT 50` | `unit_repo.go` `FindEmptyContainers()` |
| 预测达成统计 | `batch_no DESC`，`LIMIT 20` | `forecast.go` `Achievement()` |
| 前端机型类筛选列表 | 字母序 `sort()` | `ProductionKanban.vue` / `useBatchStore.js` |
| 溢出卡片选取 | 末尾卡片（`len-1`），受保护时取 `len-2` | `unit.go` `cascadeOverflowBySlot()` |
| 空位卡片逐出选取 | 从末尾往前扫描第一个无合同卡片 | `unit.go` `pickEjectableUnboundUnit()` |
| Slot 计划轮转 | 固定顺序 G → XS → AUTO 循环 | `predictor.go` `plannedModelFamilies()` |

## 核心业务逻辑

### 全量重算流程（FullRecompute）

全量重算是系统的核心预测生成流程，由 `POST /api/forecast/recompute` 触发。

步骤：

1. **清除旧数据**：删除所有 `Predicted` 状态的批次、机台和 `forecast_batch_slots` 记录，清除待处理队列中 `Waiting` 状态的条目。
2. **读取有效合同**：从合同表中读取所有有效合同单元（`contract_units`）。
3. **排除已排产合同**：统计已排入非预测批次（`Confirmed`/`In_Production`/`Completed`）的合同数量，从待排产列表中扣除已排数量，避免重复排产。
4. **机型归一化与分组**：将每个合同单元的 `model_type` 归一化为 `G`/`XS`/`AUTO` 三类，按类分组。
5. **交期排序**：每组内按 `due_date` 升序排列。
6. **交期拆批**：调用 `splitIntoBatches`，按容量和交期间隔拆分批次。
7. **机型比例分配 slot 计划**：调用 `plannedModelFamilies`，根据 Level1 比例（G:24%, XS:76%，AUTO 为剩余）确定每个 slot 的机型类，按 G→XS→AUTO 轮转排列。
8. **按 slot 计划填充批次**：遍历 slot 计划，从对应机型类的拆批结果中取出批次，用 `buildFilledUnits` 填充空位。
9. **机型字典排序**：对每个批次的机台按 `model_dictionary.sort_order` 排序并重编号。
10. **写入数据库**：在事务中创建批次、机台和 `forecast_batch_slots` 记录。
11. **溢出合同入队**：超出 slot 计划的合同写入 `production_queue`。
12. **广播 WebSocket**：通知前端批次已更新。

### 交期拆批（splitIntoBatches）

将同一机型类的合同单元按交期和容量拆分为多个批次。

规则：

1. 按 `due_date` 升序逐个放入当前批次。
2. 当当前批次人数达到 `capacity` 时，结束当前批次，开始新批次。
3. 当当前合同交期与批次首道交期相差超过 `batch_break_days`（默认 30 天）时，即使未满员也拆分为新批次。
4. 每个批次的 `due_date_start` 和 `due_date_end` 分别设为该批次首末合同的交期。

### 机型比例分配

系统使用两级比例体系控制批次的机型分布。

#### Level1：机型类比例

控制 G / XS / AUTO 三类机型在总 slot 数中的占比。

默认值：

```text
G: 24%, XS: 76%, AUTO: 剩余（约 0%，由配置决定）
```

分配算法（`plannedModelFamilies`）：

1. 按比例计算每个机型类应占的 slot 数（向下取整）。
2. 余数按小数部分从大到小分配给对应机型类。
3. 按 G → XS → AUTO 的固定顺序轮转分配，形成 slot 计划数组。

例如 `max_batch_slots = 20`，比例 G:24/XS:76/AUTO:0 时，slot 计划为：

```text
[XS, G, XS, XS, XS, G, XS, XS, XS, XS, G, XS, XS, XS, XS, G, XS, XS, XS, XS]
```

#### Level2：具体机型比例

控制每个批次内空位的尺寸分布。

默认值：

```text
G:    300:11%, 400:67%, 500:14%, 600:8%
XS:   400:51%, 500:24%, 600:17%, big:8%
AUTO: 400:51%, 500:24%, 600:17%, other:8%
```

分配算法（`distributeEmptySlots`）：

1. 按比例计算每个尺寸应占的空位数（向下取整）。
2. 余数按小数部分从大到小分配。
3. 尺寸键映射为具体机型名（如 `FR-400G`、`FR-500XS(PRO)`、`FR-400AUTO`）。

### 空位填充（buildFilledUnits）

当批次中的合同单元数量不足容量时，系统自动填充空位。

规则：

1. 合同单元占据前面的 slot。
2. 剩余空位按 Level2 比例分配具体机型。
3. 空位卡片的 `contract_no` 为空，`status` 为 `Pending`。
4. 空位卡片可被后续拖入的合同卡片替换（级联后推时优先替换空位）。

### 机型归一化（NormalizeModelType）

系统将各种具体机型名称归一化为三大机型类，用于批次分组和约束判断。

规则：

| 输入模式 | 归一化结果 |
|---|---|
| 包含 `AUTO`（不区分大小写） | `AUTO` |
| 包含 `XS`（不区分大小写） | `XS` |
| 匹配正则 `FR-\d+G` | `G` |
| 精确等于 `G` / `XS` / `AUTO` | 原值 |
| 其他 | 保留原值并打印警告日志 |

### 卡片跨批次移动与溢出级联后推

当用户在预测沙盘中将卡片从一个批次拖到另一个批次时，系统执行以下流程。

#### 移动前校验

1. 源卡片必须未锁定（`is_locked = false`）。
2. 目标批次必须与源卡片属于同一机型类（归一化后比较）。
3. 机型类不匹配时返回 400 错误。

#### 移动执行

1. 将卡片移入目标批次，插入到指定 slot 位置。
2. 对目标批次执行 slot 重排（`ReorderBatchWithUnit`）。
3. 检查目标批次是否超过容量。

#### 溢出级联后推（cascadeOverflowBySlot）

当目标批次超过容量时，触发级联后推。

规则：

1. 从目标批次开始，按 `forecast_batch_slots.slot_no` 顺序向后遍历同机型类的预测批次。
2. 对每个超容量批次：
   - 找出末尾卡片作为溢出卡片。
   - 如果末尾卡片就是刚插入/刚推入的受保护卡片，则取倒数第二张作为溢出卡片。
   - 保护机制确保用户主动操作的卡片不会被立即挤出。
3. 溢出卡片推入下一个批次时：
   - 如果下一批次有空位卡片（无合同号的占位卡片），直接替换该空位，级联终止。
   - 如果下一批次没有空位卡片，溢出卡片插入到首位（`slot_index = 1`），并继续检查该批次是否也超容量。
4. 如果下一批次也超容量，递归执行同样逻辑，保护本次推入的卡片。
5. 如果已经没有后续批次，溢出卡片进入待处理队列（`production_queue`）。
6. 每个被影响的批次都会执行 slot 压缩（`CompactSlots`）。

#### 移动后处理

1. 对源批次和所有涉及的批次执行无合同空位的比例重平衡（`rebalanceBatchesUnboundUnitsByRatio`），按 Level2 比例重新分配空位机型。
2. 对所有涉及的批次执行机型字典排序（`sortTouchedBatchesByModelDictionary`）。
3. 提交事务。

### 交期间隔拆分（enforceFamilyGapDays）

在卡片移动后，系统会检查同机型类所有预测批次的交期跨度。

规则：

1. 遍历每个批次，找到有合同号且未锁定的卡片中最早和最晚的交期。
2. 如果交期跨度超过 `batch_break_days`（默认 30 天），将最晚交期的卡片推到下一个批次。
3. 推入下一个批次时，同样优先替换空位卡片；没有空位则插入首位。
4. 如果下一个批次也超容量，触发级联后推。
5. 移出卡片后，当前批次用自动填充补足容量。
6. 重复检查直到所有批次的交期跨度都在阈值内。

### 待处理队列（production_queue）

当溢出卡片无法被任何后续批次承接时，进入待处理队列。

队列条目包含：

- `model_type`：机型类。
- `contract_no`：合同号。
- `customer`：客户。
- `dealer_name`：经销商。
- `due_date`：交期。
- `quantity_remaining`：剩余数量（通常为 1）。
- `status`：`Waiting`。
- `priority`：按入队顺序递增，先入队的优先级更高。

全量重算时会清除所有 `Waiting` 状态的队列条目并重新生成。

### 批次容量配置

每个机型类的批次容量通过 `model_capacity` 配置项控制。

默认值：

```text
G: 30, XS: 30, AUTO: 27
```

可通过 `GET /api/capacity-ratio` 查询和 `PATCH /api/capacity-ratio` 修改。

### 机型字典（model_dictionary）

`model_dictionary` 表定义了具体机型的启用状态和排序权重。

字段：

- `model_name`：具体机型名称（如 `FR-400G`、`FR-500XS(PRO)`）。
- `enabled`：是否启用（1=启用，0=禁用）。
- `sort_order`：排序权重，数值越小排越前。

用途：

1. 批次内卡片排序时，按 `sort_order` 确定卡片先后顺序。
2. 卡片信息强改时，校验目标机型是否在字典中启用。

## 算法关系与数据流

系统的两大核心入口是**全量重算**（自动排产）和**用户拖拽**（人工调整），它们共享底层的拆批、比例分配、空位填充和排序算法。

### 全量重算数据流

```text
factory_plan (合同表)
  │ ORDER BY due_date ASC, contract_no ASC
  ▼
ReadValidContractUnits → 合同单元列表
  │ 排除已排产合同（Confirmed/In_Production/Completed）
  ▼
NormalizeModelType → 按 G/XS/AUTO 分组
  │ 每组内 sort by due_date ASC
  ▼
splitIntoBatches → 按容量(30/30/27) + 交期间隔(30天) 拆批
  ▼
plannedModelFamilies → Level1 比例分配 slot 计划
  │ 向下取整 + 余数按小数降序补齐 + G→XS→AUTO 轮转
  ▼
buildFilledUnits → 空位按 Level2 比例填充具体机型
  │ distributeEmptySlots + emptySlotConcreteModel
  ▼
sortAndReindexUnitsByModelDictionary → 字典排序
  │ sort_order → 机型名 → slot_index
  ▼
写入 batches + units + forecast_batch_slots → WebSocket 广播
```

### 用户拖拽数据流

```text
前端拖拽卡片 → onDragEnd → api.moveUnitBatch()
  │ 前端校验：备货卡片不允许跨批次拖拽
  ▼
MoveBatch handler
  │ 后端校验：未锁定 + 同机型类
  ▼
ReorderBatchWithUnit → 目标批次 slot 重排
  ▼
cascadeOverflowBySlot → 超容量级联后推
  │ 末尾卡片挤出，保护刚插入的卡片
  │ 优先替换空位终止，否则递归下一批次
  ▼
enforceFamilyGapDays → 交期间隔检查与拆分
  │ 跨度 > 30天 → 最晚交期卡片推到下一批次
  ▼
rebalanceBatchesUnboundUnitsByRatio → 空位机型重平衡
  ▼
sortTouchedBatchesByModelDictionary → 所有涉及批次重排序
  ▼
提交事务 → WebSocket 广播
```

## 并发控制与事务

### 全量重算锁

全量重算通过 Redis 分布式锁（`lock:recompute`，TTL=60s）保证同一时刻只有一个重算任务在执行。

- 锁获取成功 → 正常执行。
- 锁已被占用 → 返回 `409 Conflict`（不是 500）。
- Redis 不可用 → 降级为本地互斥锁，正常执行。

### 数据库事务

- 全量重算：整个流程在一个 DB 事务中执行，失败时整体回滚。
- 卡片移动：`MoveBatch` handler 中，从校验到级联后推到排序到提交，全部在一个事务中。
- 急单插入：通过 `SELECT ... FOR UPDATE` 锁定目标和回退两行，在事务中完成原订单迁移和急单写入。

### 行级锁

- `LockBatchForUpdate`：对批次行加 `FOR UPDATE` 锁。
- `ListByBatchIDsForUpdate`：对批次内所有机台行加 `FOR UPDATE` 锁。
- `ListPredictedByModelForUpdate`：对同机型类所有预测批次加 `FOR UPDATE` 锁。

## Slot 操作函数

以下函数负责批次内 `slot_index` 的维护，位于 `server/internal/repo/unit_repo.go`。

| 函数 | 功能 | 说明 |
|---|---|---|
| `CompactSlots` | 重编号 `slot_index` | 按当前 `slot_index ASC` 顺序重新编号为 1,2,3...，不改变 `unit_id` |
| `ReorderBatchWithUnit` | 插入卡片到指定位置 | 将目标卡片从其他位置取出，插入到 `targetSlot`，其余卡片顺延 |
| `RewriteBatchAssignments` | 按排序结果重写 | 接收排好序的 `unit_id` 列表，重写 `batch_id` 和 `slot_index` |
| `ReSlotBatch` | 重编号并重写 `unit_id` | 按 `slot_index ASC` 重编号，同时将 `unit_id` 改为 `{batchID}-S{slot}` 格式 |
| `ShiftSlots` | 批量偏移 slot | 将 `slot_index >= fromSlot` 的所有行的 `slot_index` 加上 `delta` |
| `GetMaxSlotInBatch` | 获取最大 slot | 返回 `MAX(slot_index)`，用于确定新卡片的插入位置 |

`ReorderBatchWithUnit` 和 `RewriteBatchAssignments` 都使用两阶段更新（先设为 `100000+i` 临时值再设为最终值）来避免唯一约束冲突。

## 项目结构

```text
.
├── README.md
├── start-all.bat
├── server/
│   ├── cmd/
│   ├── internal/
│   │   ├── config/
│   │   ├── database/
│   │   ├── engine/
│   │   ├── handler/
│   │   ├── model/
│   │   ├── repo/
│   │   ├── router/
│   │   ├── service/
│   │   └── ws/
│   ├── src/
│   ├── go.mod
│   └── package.json
└── web/
    ├── src/
    │   ├── components/
    │   ├── services/
    │   ├── stores/
    │   └── views/
    ├── vite.config.js
    └── package.json
```

## 备注

本系统当前推荐使用 Go 后端作为默认运行后端，Node.js 后端主要用于兼容旧实现或对照调试。
