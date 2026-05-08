# V7 FastAPI 集成 Go 智能排产沙盘方案

本方案将当前 Go 智能排产服务作为独立业务服务接入 V7，由 FastAPI 负责统一入口、权限校验、HTTP 代理和 WebSocket 代理。

## 已确认决策

- **接入模式**：Go 独立服务 + FastAPI 代理。
- **数据库策略**：开发阶段已与 V7 共用同一个数据库，当前沙盘相关表作为 V7 正式模块表继续使用。
- **前端策略**：V7 前端直接迁移当前 Vue 沙盘页面和相关组件。
- **菜单策略**：旧“生产统筹规划”和新“预测沙盘”并行运行，稳定后再决定是否替换。
- **权限策略**：FastAPI 校验 V7 登录态和权限，再向 Go 服务注入 `X-Username`、`X-Role` 等身份头。
- **实时推送策略**：第一阶段由 FastAPI 代理 Go WebSocket，前端只连接 V7/FastAPI。

## 目标架构

```text
V7 Vue 前端
  ↓ HTTP / WebSocket
V7 FastAPI 后端
  ↓ 内网 HTTP / WebSocket 代理
Go 智能排产服务
  ↓
V7 共用 MySQL 数据库
```

## 第一阶段目标

在不破坏 V7 原“生产统筹规划”模块的前提下，新增一个并行的“预测沙盘”模块，跑通完整业务闭环：

1. V7 用户登录后进入预测沙盘。
2. 沙盘通过 FastAPI 获取批次、机台、机型和配置数据。
3. FastAPI 校验权限后转发到 Go 服务。
4. Go 服务继续执行排产、拖拽、级联后推、批次审核等核心逻辑。
5. 数据直接落到当前已共用的 V7 MySQL 表。
6. WebSocket 事件通过 FastAPI 代理转发给 V7 前端。

## 前端迁移范围

### 必迁

- `web/src/views/PredictionSandbox.vue`
- `web/src/components/UnitCard.vue`
- `web/src/components/CapacityRatioEditor.vue`
- `web/src/stores/useBatchStore.js`
- `web/src/services/api.js` 中与沙盘相关的接口方法
- `web/src/services/socket.js` 中 WebSocket 连接逻辑

### 视功能需要迁移

- `web/src/components/RushOrderEntry.vue`
- `web/src/stores/useRushStore.js`

如果第一阶段只替代生产统筹规划，可先聚焦预测沙盘本体；加急订单入口可作为第二批迁移内容。

## FastAPI 代理范围

V7 后端新增沙盘代理模块，路径前缀 `/api/v1/sandbox`（避免与现有 `/api/v1/planning` 冲突）：

```text
/api/v1/sandbox/*
/ws/sandbox (第二阶段)
```

### HTTP 代理接口

FastAPI 对外暴露 V7 统一路径：

```text
GET    /api/v1/sandbox/batches
GET    /api/v1/sandbox/batches/{id}
GET    /api/v1/sandbox/batches/{id}/units
POST   /api/v1/sandbox/batches/{id}/confirm
POST   /api/v1/sandbox/batches/batch-confirm
POST   /api/v1/sandbox/batches/generate-next
POST   /api/v1/sandbox/forecast/recompute
GET    /api/v1/sandbox/capacity-ratio
PATCH  /api/v1/sandbox/capacity-ratio
GET    /api/v1/sandbox/production-queue
GET    /api/v1/sandbox/units/empty-containers
GET    /api/v1/sandbox/units/{id}
PATCH  /api/v1/sandbox/units/{id}
PATCH  /api/v1/sandbox/units/{id}/unlock
POST   /api/v1/sandbox/units/{id}/move-batch
POST   /api/v1/sandbox/units/{id}/insert-cascade
POST   /api/v1/sandbox/units/swap-content
POST   /api/v1/sandbox/units/rush-insert
POST   /api/v1/sandbox/units/{id}/mark-spot
GET    /api/v1/sandbox/production-lines
POST   /api/v1/sandbox/production-lines/{id}/assign
POST   /api/v1/sandbox/production-lines/{id}/manual-complete
```

FastAPI 内部转发到 Go：

```text
http://127.0.0.1:3001/api/*
```

## 权限与身份传递

FastAPI 负责：

1. 校验 V7 登录态。
2. 判断用户是否有进入预测沙盘的权限。
3. 转发请求时注入内部身份头。

建议注入：

```text
X-Username: 当前 V7 用户名
X-Role: 当前 V7 角色
X-User-ID: 当前 V7 用户 ID
X-Internal-Token: FastAPI 与 Go 服务之间的内部密钥
```

Go 服务负责：

1. 校验 `X-Internal-Token`。
2. 信任 FastAPI 注入的用户身份。
3. 继续执行业务权限判断，例如只允许 `admin` / `boss` / `planner` 执行关键操作。

## WebSocket 代理方案

前端只连接：

```text
/ws/planning
```

FastAPI 作为桥接层：

```text
V7 前端 WebSocket
  ↔ FastAPI /ws/planning
  ↔ Go /ws
```

第一阶段建议只转发沙盘需要的事件，避免一次性迁移生产看板所有实时事件。

## Go 服务调整点

- 保持 Go 服务独立启动，默认监听 `127.0.0.1:3001`。
- 增加内部服务密钥配置，例如 `INTERNAL_SERVICE_TOKEN`。
- Go 中间件增加内部 Token 校验。
- 允许从 FastAPI 注入的请求头读取用户名、角色和用户 ID。
- 保持现有核心业务逻辑不重写：
  - 全量重算
  - 生成下一批
  - 批次查询
  - 卡片拖拽
  - 同机型类约束
  - 溢出级联后推
  - 批次审核
  - 容量比例配置

## 全量重算性能优化

### 问题分析

当前 `FullRecompute()` 存在两个性能瓶颈：

1. **逐行写入**：批次和 units 逐条 `tx.Create`，N 个批次产生 2N 次 INSERT。
2. **逐行 UPDATE**：`reorderBatchSlots` 和 `ReSlotBatch` 逐行 `Update("slot_index")`，M 个 unit 产生 M 次 UPDATE。

### 已实施优化

#### 3a. 批量写入（predictor.go）

- 所有 batch 收集到切片，一次性 `tx.Create(&allBatches)`
- 所有 unit 扁平化到切片，一次性 `tx.Create(&allUnits)`
- 预计写入耗时减少 60-80%

#### 3b. 批量 UPDATE（unit_svc.go, unit_repo.go, handler/unit.go）

- `reorderBatchSlots` 和 `ReSlotBatch` 改为单条 `CASE WHEN` SQL：
  ```sql
  UPDATE units SET slot_index = CASE unit_id
    WHEN 'id1' THEN 1 WHEN 'id2' THEN 2 ...
  END WHERE unit_id IN ('id1', 'id2', ...)
  ```
- 从 M 次 UPDATE 减少为 1 次

### 后续优化方向（第二阶段）

- **增量重算**：拖拽/修改操作只重算受影响的批次，而非全量
- **内存缓存**：缓存 `factory_plan` 和 `model_dictionary` 查询结果
- **数据库索引**：为 `units.batch_id`、`units.model_type`、`batches.status` 添加索引
- **异步任务**：全量重算改为异步任务 + 进度查询，避免 HTTP 超时

## 数据库处理

当前沙盘已与 V7 共用数据库，因此第一阶段不做跨库同步。

当前表作为正式模块表继续使用：

- `batches`
- `units`
- `forecast_batch_slots`
- `production_queue`
- 产能比例/机型配置相关表
- 用户表继续以 V7 为准

需要确认但不阻塞第一阶段：

- 表名是否与 V7 旧模块冲突。
- 旧生产统筹规划是否也写入 `batches` / `units`。
- 旧模块和新沙盘并行时，是否需要按状态或来源字段隔离数据。

## 菜单与路由策略

V7 中新增菜单入口，例如：

```text
生产管理 / 预测沙盘
```

旧模块保留：

```text
生产管理 / 生产统筹规划
```

并行期间：

- 旧模块用户可继续访问旧功能。
- 新沙盘只开放给指定角色或测试用户。
- 稳定后再决定是否把旧入口指向新沙盘。

## 推荐实施步骤

### 步骤 1：搭建 Go 服务接入边界 ✅ 已完成

- 固定 Go 服务端口和启动方式（`127.0.0.1:3001`）。
- 增加内部服务密钥（`INTERNAL_SERVICE_TOKEN` 环境变量）。
- Go 中间件增加 `InternalToken()` 校验，挂在 CORS 之后、AdminOnly 之前。
- CORS 允许头新增 `X-Internal-Token`、`X-User-ID`。

### 步骤 2：在 FastAPI 中新增 sandbox 代理模块 ✅ 已完成

- 新建 `api/routes/sandbox.py`，使用 `httpx.AsyncClient` 转发。
- 路由前缀 `/api/v1/sandbox`，注册到 `api/main.py`。
- 注入 `X-Username`、`X-Role`、`X-User-ID`、`X-Internal-Token` 头。
- 重算接口超时 120s，普通接口 30s。
- Go 服务不可用时返回 503 + 友好提示。
- 添加 `httpx==0.27.0` 到 `requirements.txt`。
- 添加 `GO_SANDBOX_URL`、`GO_INTERNAL_TOKEN` 到 `config.py`。

### 步骤 3：全量重算性能优化 ✅ 已完成

- `predictor.go:FullRecompute` 改为批量 INSERT（一次写入所有 batch + 一次写入所有 unit）。
- `unit_svc.go:reorderBatchSlots` 改为 `CASE WHEN` 批量 UPDATE。
- `unit_repo.go:ReSlotBatch` 改为 `CASE WHEN` 批量 UPDATE。
- `handler/unit.go:reorderBatchSlots` 同步优化。

### 步骤 4：迁移 Vue 预测沙盘页面 ✅ 已完成

- 新建 `frontend/src/services/sandboxApi.ts`（使用 V7 的 `request.ts`）。
- 新建 `frontend/src/stores/useSandboxBatchStore.ts`、`useSandboxRushStore.ts`。
- 新建 `frontend/src/utils/sandboxModelType.ts`。
- 迁移组件到 `frontend/src/components/sandbox/`（UnitCard、BatchCard、CapacityRatioEditor、EmptyContainerPicker）。
- 迁移主页面到 `frontend/src/views/sandbox/PredictionSandbox.vue`。
- 所有 API 前缀改为 `/api/v1/sandbox/`。
- 第一阶段用 5s 轮询替代 WebSocket。
- 安装 `vue-draggable-plus` 依赖。

### 步骤 5：菜单与权限配置 ✅ 已完成

- 路由：`/sandbox` → `PredictionSandbox.vue`，权限 `SANDBOX_VIEW`。
- `DEFAULT_ROLE_PERMISSIONS`：Admin/Boss 新增 `SANDBOX_VIEW` + `SANDBOX_EDIT`。
- `FUNC_MAP` 新增 `SANDBOX_VIEW` 条目。

### 步骤 6：跑通最小业务闭环（待验证）

验证以下功能：

- 打开预测沙盘。
- 获取批次列表。
- 全量重算。
- 生成下一批。
- 拖拽卡片跨批次移动。
- 满批次级联后推。
- 批次审核。
- 容量比例配置。

### 步骤 7：接入 WebSocket 代理（第二阶段）

- V7 前端连接 `/ws/sandbox`。
- FastAPI 桥接 Go `/ws`。
- 替换 5s 轮询为 WebSocket 事件驱动。
- 验证沙盘刷新事件是否正常。

### 步骤 8：灰度并行

- 新旧模块并行。
- 只给指定用户开放新沙盘。
- 记录异常和数据差异。
- 稳定后再决定旧生产统筹规划是否替换。

## 主要风险

- **表数据冲突**：旧生产统筹规划如果也写相同表，需要增加数据来源或状态隔离。→ 缓解：沙盘表有 `source='algorithm'` 和 `status='Predicted'` 字段可区分。
- **权限绕过**：Go 服务必须增加内部 Token，避免前端绕过 FastAPI 直接调用。→ ✅ 已实施 `InternalToken()` 中间件。
- **WebSocket 桥接复杂**：FastAPI 代理 WebSocket 需要单独验证断线重连和事件格式。→ 缓解：第一阶段用 5s HTTP 轮询替代，第二阶段再接入 WebSocket。
- **接口超时**：全量重算可能耗时较长，FastAPI 代理超时时间要单独配置。→ ✅ 已配置重算接口 120s 超时 + 批量写入优化。
- **前端组件依赖**：迁移 Vue 页面时要确认 V7 是否已安装 Element Plus、Pinia、vue-draggable-plus 等依赖。→ ✅ V7 已有 Element Plus + Pinia，`vue-draggable-plus` 已安装。
- **Go 服务未启动**：前端访问沙盘时代理报错。→ ✅ FastAPI 代理返回 503 + "沙盘服务不可用"提示。

## 已确认问题

- **V7 前端技术栈**：已确认使用 Vue 3 + Element Plus + Pinia + TypeScript。
- **Go 服务可运行**：源码在本机 `d:\Program_1\server`，服务已可启动。
- **API 路径前缀**：使用 `/api/v1/sandbox/`，避免与现有 `/api/v1/planning/` 冲突。
- **权限标识**：`SANDBOX_VIEW`（查看）、`SANDBOX_EDIT`（编辑/拖拽/重算）。
- **菜单名称**：🧪 预测沙盘。
- **第一阶段不含加急订单入口**：RushOrderEntry 组件已迁移但暂不集成到主页面。

## 环境变量配置

Go 服务 `.env` 新增：
```
INTERNAL_SERVICE_TOKEN=v7-sandbox-2026-internal-key
```

V7 FastAPI 侧配置（`config.py` 或 `.env`）新增：
```
GO_SANDBOX_URL=http://127.0.0.1:3001
GO_INTERNAL_TOKEN=v7-sandbox-2026-internal-key
```
