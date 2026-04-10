# V7ex 架构与代码库综合解析指南 (For Claude Code)

这是一份为 AI 编码助手（如 Claude Code）准备的 V7ex 系统架构与代码库深度解析文档。请在开始任何重构、功能新增或 Bug 修复前，仔细阅读本指南，以确保你的修改符合系统现有的架构规范、数据流向和安全策略。

---

## 1. 系统整体架构概览

V7ex 是一个专注于**成品库存与生产统筹管理**的现代化 Web 应用，采用前后端分离架构。
- **前端技术栈**：Vue 3 (Composition API) + Vite + TypeScript + Pinia + Vue Router + Element Plus。
- **后端技术栈**：Python 3.10+ + FastAPI + SQLAlchemy + MySQL + PyJWT。
- **核心业务闭环**：覆盖成品入库、库位管理、生产排产、合同与销售订单跟进、订单配货出库、机台档案管理以及全生命周期的数据追溯。

---

## 2. 后端架构 (FastAPI)

后端代码组织遵循领域驱动设计（DDD）的变体，按职责严格分层。

### 2.1 核心目录结构
- **`api/`**：包含入口应用实例 `main.py` 和 `routes/` 目录。路由严格按业务领域划分（如 `auth.py`, `inventory.py`, `planning.py`, `users.py`, `logs.py`, `traceability.py`）。
- **`core/`**：存放业务核心与基础设施逻辑，如鉴权中间件 (`auth.py`)、文件管理 (`file_manager.py`)、OCR 引擎接口以及性能指标收集 (`metrics.py`)。
- **`crud/`**：数据库访问层，隔离所有 SQLAlchemy 的数据库增删改查逻辑（如 `contracts.py`, `orders.py`, `inventory.py`）。**注意：路由层绝对不允许直接写 SQL 或操作 ORM Session。**
- **`database.py`**：负责 MySQL 引擎配置、连接池初始化，并在系统首次启动时幂等创建所有数据库表及约束 DDL。
- **`utils/`**：通用工具模块，包含缓存装饰器 (`cache.py`)、数据格式化及解析器 (`parsers.py`)。
- **`scripts/` & `tests/`**：包含性能基线测试脚本、健康检查脚本、WinSW 部署配置以及基于 Pytest 的测试用例。

### 2.2 核心数据模型 (Data Models)
数据库表结构主要在 `database.py` 中定义：
- **`finished_goods_data` (成品库存数据)**：核心资产表。记录机台流水号（主键）、批次号、机型、当前状态（待入库/库存中/待发货/已出库）、占用订单号及物理库位 (`Location_Code`)。
- **`sales_orders` (销售订单)**：记录订单号、客户、需求机型/数量、下单及发货时间、指定的配货批次/来源 (JSON 格式存储)。
- **`factory_plan` (生产计划)**：记录合同排产关联，包含排产数量、要求交期及关联的销售订单。
- **`contract_records` & `machine_archives`**：分别用于管理合同附件的解析记录，与单个机台（基于流水号）的相关图片/文件档案元数据。
- **`users` & `role_permissions`**：存储系统用户、密码哈希、角色定义及细粒度功能权限映射。
- **`transaction_log` & `audit_log`**：记录核心资产状态流转与用户敏感操作的流水审计日志。

### 2.3 核心 API 端点
- **Auth**: `POST /api/v1/auth/login` 提供基于 OAuth2 的 JWT 令牌颁发。
- **Inventory**: `/api/v1/inventory/*` 处理库存查询、库位更新 (`/layout`, `/inbound-to-slot`)、机台信息编辑、发货复核 (`/shipping/confirm`) 及机台档案附件上传与预览。
- **Planning**: `/api/v1/planning/*` 处理销售订单创建、订单配货分配 (`/orders/{id}/allocate`)、合同批量导入 (`/contracts/batch-create`) 与解析。
- **Traceability**: `/api/v1/traceability/{target_id}/timeline` 提供基于流水号或订单号的生命周期时间轴溯源。
- **Users**: `/api/v1/users/*` 处理用户注册、角色审批及状态变更。

---

## 3. 前端架构 (Vue 3)

前端采用标准的 Vue 3 Setup 语法糖组织，强调组件复用与状态的集中管理。

### 3.1 核心目录结构
- **`src/components/`**：包含 `Layout.vue`（全局带侧边栏与顶栏布局）、`VirtualScrollList.vue`（处理大数据量列表渲染）、`PageHeader.vue` 等复用 UI 组件。
- **`src/views/`**：承载按路由划分的页面级业务组件（详见下文路由映射）。
- **`src/store/`**：基于 Pinia 的状态管理，划分了 `user.ts` (带 localStorage/sessionStorage 身份持久化)、`inventory.ts`（库存大列表状态）、`planning.ts`（排产与订单状态）等模块。
- **`src/router/`**：Vue Router 实例 (`index.ts`)，结合用户角色实现动态路由注册与全局导航守卫。
- **`src/utils/`**：包含 Axios 请求拦截器封装 (`request.ts`)、权限校验工具 (`roles.ts`) 与通用表单校验规则 (`formRules.ts`)。
- **`src/composables/`**：存放 Vue 组合式函数，如处理表单草稿和防抖提交状态的 `useFormDraft.ts`。

### 3.2 路由与页面组件映射
系统基于五大角色 (`Admin`, `Boss`, `Sales`, `Prod`, `Inbound`) 严格限制页面访问：
- **生产与订单模块**：
  - `/planning` -> 生产统筹 (`BossPlanning.vue`)
  - `/contracts` -> 合同管理 (`ContractManage.vue`)
  - `/sales-orders` -> 销售下单 (`SalesOrder.vue`)
  - `/order-allocation` -> 订单配货 (`OrderAllocation.vue`)
- **仓储与发货模块**：
  - `/inbound` -> 成品入库 (`Inbound.vue`)
  - `/warehouse-dashboard` -> 库位大屏可视化 (`WarehouseDashboard.vue`)
  - `/shipping-review` -> 发货复核 (`ShippingReview.vue`)
- **查询与档案模块**：
  - `/inventory` -> 库存查询 (`InventoryQuery.vue`)
  - `/machine-archive` -> 机台档案 (`MachineArchive.vue`)
  - `/traceability` -> 汇总与追溯 (`Traceability.vue`)
- **系统管理**：
  - `/users` -> 用户管理 (`UserManagement.vue`)
  - `/logs` -> 交易日志 (`LogViewer.vue`)

---

## 4. 权限控制与安全体系 (Auth & RBAC)

V7ex 实现了从前端 UI 到后端数据库的**全链路安全控制**。

### 4.1 前端路由守卫与菜单动态注入
- **鉴权**：用户登录成功后，前端解析并保存 JWT。
- **动态路由**：Vue Router 的全局前置守卫拦截路由跳转，根据 JWT 载荷中的 `role`，调用 `ensureDynamicRoutes()` 动态注入该角色有权访问的菜单和路由。
- **越权处理**：若用户尝试手工输入无权限的路径，将被拦截并重定向至 `/403` (`Forbidden.vue`)；若 Token 过期，Axios 响应拦截器捕获 `401` 后强制登出并跳回 `/login`。

### 4.2 后端接口级细粒度拦截
- **依赖注入**：利用 FastAPI 的 `Depends` 体系，在路由层强制要求携带 Token。
- **角色白名单**：敏感写接口（POST/PUT/DELETE）或特定域（如 `/api/v1/users/`）使用 `Depends(require_roles('Admin', 'Boss'))` 进行校验。当前请求上下文的 JWT Role 若不在白名单内，直接抛出 HTTP `403 Forbidden`。

---

## 5. 开发与重构注意事项 (Guidelines for AI)

1. **遵守分层架构**：不要在路由层 (`api/routes/`) 混入 SQL 拼接逻辑，所有数据库交互必须下沉至 `crud/` 层；不要在 CRUD 层抛出 HTTP 异常 (`HTTPException`)，这属于路由层的职责。
2. **性能优先**：在处理 `finished_goods_data` 等可能包含数万条记录的大表时，必须警惕全表扫描。前端大列表渲染应优先使用 `VirtualScrollList.vue`；在 Pinia 中存储大数组时，优先考虑使用 `shallowRef` 代替 `ref` 避免深度 Proxy 导致的内存泄漏。
3. **状态流转严格性**：机台的核心状态（`待入库` -> `库存中` -> `待发货` -> `已出库`）变更必须记录在 `transaction_log` 中，确保操作可追溯。
4. **代码风格对齐**：前端统一使用 `<script setup lang="ts">` 语法；后端遵循 PEP 8 规范并使用 Type Hints（类型注解）。