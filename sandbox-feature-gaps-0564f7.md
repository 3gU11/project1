# 老板计划模块功能补全计划

将 V7 老板计划模块对齐 README 规范和原始 Go 前端的完整功能，补全缺失的 API 代理、UI 交互和业务约束。

---

## 缺失功能清单

### A. 缺失的 API 代理（Go 有，V7 FastAPI 未代理）

| # | API | README 描述 | Go 路由 |
|---|-----|------------|---------|
| A1 | `POST /units/repair-family-mismatches` | 一键修复串机型 | 无（需新增 Go handler） |
| A2 | `POST /units/:id/reorder-slot` | 批次内重排 | 无（Go move-batch 内含 reorder 逻辑） |
| A3 | `POST /batches/:id/insert-empty-slot` | 插入空位 | 无（需新增 Go handler） |
| A4 | `GET /model-types` | 获取机型列表 | 无（需新增 Go handler） |
| A5 | `GET /forecast/achievement` | 预测达成情况 | 无（需新增 Go handler） |

> **注意**：A1-A5 在 Go 后端 router.go 中均**不存在**对应路由。这些是 README 描述但 Go 后端也未实现的功能。需要先在 Go 侧补实现，再在 V7 代理。

### B. 缺失的 UI 功能（前端逻辑缺失）

| # | 功能 | 原版实现 | V7 现状 | 优先级 |
|---|------|---------|---------|--------|
| B1 | 一键修复串机型按钮 | `handleRepairMismatches` + API | 无按钮无 API | 高 |
| B2 | 具体机型筛选下拉框 | `modelFilter` + `modelTypes` 列表 | 只有机型类 radio | 高 |
| B3 | 信息强改-机型选择器 | `el-select` + `editModelTypes` 过滤 | `el-input` 手动输入 | 高 |
| B4 | 批次列固定排序(slot_no) | `batchSlotOrder` + `forecast_slot_no` | 无排序 | 高 |
| B5 | 批次内卡片按 slot_index 排序 | `sortBatchUnitsInPlace` | 无排序 | 高 |
| B6 | 交期范围计算显示 | `batchDueRangeText` 从 units 计算 | 只显示 batch 级字段 | 中 |
| B7 | 备货/已规划统计 | `plannedCount` / `stockCount` | 只显示总数 | 中 |
| B8 | 批次号格式化 | `displayBatchCode` / `formatBatchCode` | 显示 `batch_no` | 中 |
| B9 | 审核时输入批次号 | `ElMessageBox.prompt` 输入 MM-SS | 直接审核 | 高 |
| B10 | 拖拽限制(备货不可跨批) | 检查 `isStockUnit` | 无限制 | 高 |
| B11 | 横向滚动同步+边缘自动滚动 | `syncTopScroll` + `onEdgeHover` | 无 | 低 |
| B12 | 机型列表加载 | `loadModelTypes()` onMounted | 无 | 高（B2/B3 依赖） |

---

## 实施步骤

### 阶段 1：纯前端可补全的功能（无需 Go 改动）

这些功能只需修改 V7 前端代码，数据已从 Go 返回但前端未使用：

1. **B4: 批次列固定排序** — `filteredBatches` computed 中加入 `batchSlotOrder` 排序逻辑
2. **B5: 卡片按 slot_index 排序** — `refresh()` 后调用 `sortBatchUnitsInPlace`
3. **B6: 交期范围计算** — 添加 `batchDueRangeText` 函数，模板中使用
4. **B7: 备货/已规划统计** — 添加 `plannedCount` / `stockCount`，模板中显示
5. **B8: 批次号格式化** — 添加 `displayBatchCode` / `formatBatchCode`
6. **B10: 拖拽限制** — `onUnitMoved` 中检查备货机器禁止跨批
7. **B9: 审核输入批次号** — 修改 `batchConfirm` 为 prompt 输入 + 单选审核
8. **B11: 横向滚动同步** — 添加 topScroll + syncScroll + edgeAutoScroll

### 阶段 2：需 Go 后端新增 API 的功能

9. **Go: 新增 `GET /api/model-types`** — 查询机型列表
10. **Go: 新增 `POST /api/units/repair-family-mismatches`** — 修复串机型
11. **Go: 新增 `POST /api/batches/:id/insert-empty-slot`** — 插入空位
12. **Go: 新增 `GET /api/forecast/achievement`** — 预测达成
13. **V7 FastAPI: 代理新路由**
14. **V7 前端: sandboxApi.ts 添加新 API 调用**
15. **B12: 机型列表加载** — 调用 `model-types` API
16. **B2: 具体机型筛选** — 使用 `modelTypes` 数据
17. **B3: 机型选择器** — 编辑抽屉改用 `el-select`
18. **B1: 一键修复串机型** — 添加按钮 + 调用 API

---

## 文件变更清单

### 阶段 1（纯前端）
| 文件 | 变更 |
|------|------|
| `frontend/src/views/sandbox/PredictionSandbox.vue` | B4-B11 全部 |

### 阶段 2（Go + FastAPI + 前端）
| 文件 | 变更 |
|------|------|
| `server/internal/handler/*.go` | 新增 model-types / repair / insert-empty-slot / achievement handler |
| `server/internal/router/router.go` | 注册新路由 |
| `api/routes/sandbox.py` | 代理新路由 |
| `frontend/src/services/sandboxApi.ts` | 新增 API 函数 |
| `frontend/src/views/sandbox/PredictionSandbox.vue` | B1/B2/B3/B12 |

---

## 建议执行顺序

先做阶段 1（8 项纯前端改动，无需等 Go），再做阶段 2。

## Status Update (2026-05-04)

Completed:
- Added Go endpoint `POST /api/units/repair-family-mismatches` and exposed it through V7 proxy.
- Reworked slot reorder paths to use collision-safe two-phase slot reassignment to avoid `uq_units_batch_slot` conflicts.
- Startup script now builds Go binary first and checks Go health before launching dependent services.
- Sandbox proxy now enforces read/write permission split (`SANDBOX_VIEW` vs `SANDBOX_EDIT`) and standardizes Go-unavailable/timeout errors.
- Frontend recompute UX distinguishes lock-conflict (`409`) and timeout (`504`) messaging.

Not in this scope:
- Mobile sandbox migration (kept out-of-scope intentionally).
