# V7STD1.0 成品库存管理系统

> 面向制造业的机台库存全生命周期管理平台

## 项目概述

V7STD1.0 是一个专为制造企业设计的成品库存管理系统，围绕 **"合同 → 排产 → 入库 → 订单配货 → 发货 → 档案"** 形成业务闭环，支持多角色协作、生产沙盘规划、库位可视化、交易追溯等核心功能。

系统由 **FastAPI（Python）** 与 **Go** 双后端协同驱动：FastAPI 负责库存、合同、用户等业务逻辑，Go 服务负责沙盘预测排产（Sandbox）与全量重算。

## 技术架构

| 层级 | 技术栈 |
|------|--------|
| **前端** | Vue 3 + TypeScript + Element Plus + Pinia + Vite |
| **业务后端** | FastAPI + Python 3.10+ |
| **沙盘后端** | Go 1.21+（独立服务，负责预测排产/全量重算/WebSocket 同步） |
| **数据库** | MySQL 8.0（SQLAlchemy 原生 SQL + pandas） |
| **文档解析** | PaddleOCR + pdfplumber + mammoth |
| **部署** | Uvicorn + Go binary + `launcher.exe` 一键启动 |

## 核心功能模块

```
┌─────────────────────────────────────────────────────────────┐
│                      V7ex 业务流程                           │
├─────────────────────────────────────────────────────────────┤
│  合同管理 → 生产统筹 → 销售下单 → 订单配货 → 发货复核 → 已出库 │
│                ↓                                            │
│         成品入库 ← 跟踪单解析 ← 自动生成待入库清单            │
│                ↓                                            │
│         库位入库 → 库存中 → 被订单占用 → 待发货              │
└─────────────────────────────────────────────────────────────┘
```

### 功能清单

| 模块 | 功能描述 | 对应角色 |
|------|----------|----------|
| 👑 生产统筹 | 订单规划、合同状态管理、生产排期 | Boss, Sales |
| 🏭 合同管理 | 合同录入（录入后自动触发沙盘全量重算）、附件上传、状态流转 | Boss, Sales |
| 🧩 生产沙盘 | 预测排产批次管理、拖拽调序、急单插入、批次审核、特殊机型管理 | Boss |
| 📝 销售下单 | 创建销售订单、指定机型数量 | Sales |
| 📦 订单配货 | 从库存锁定机台（直接 SQL 更新，避免缓存脏写）、释放配货 | Sales |
| 📥 成品入库 | 跟踪单解析、待入库清单（自动屏蔽「已绑定」机台）、按库位入库 | Prod, Inbound |
| 🚛 发货复核 | 确认发货、发货撤回 | Prod |
| 🔧 机台档案 | 机台文件上传、预览、下载 | Prod |
| 🗺️ 库位大屏 | 可视化库位占用情况 | 全角色 |
| 🔍 库存查询 | 多条件筛选、状态统计（含「已绑定」机台独立计数、加高机型统计） | 全角色 |
| 🔍 汇总追溯 | 批次追溯、交易链路查询 | Boss, Sales |
| 📊 操作日志 | 系统操作审计、数据变更记录 | Admin, Boss |
| 📖 机型字典 | 标准机型定义、族系归类管理 | Admin, Boss |

## 角色权限体系

| 角色 | 权限范围 |
|------|----------|
| **Boss** | 生产统筹、合同管理、查询、档案、库位大屏、追溯 |
| **Sales** | 生产统筹、合同管理、销售下单、订单配货、入库、查询、库位大屏 |
| **Prod** | 入库、发货确认、查询、机台编辑、档案、库位大屏 |
| **Inbound** | 入库、库位大屏 |
| **Admin** | 全部权限 + 用户管理 |

## 快速启动

### 环境要求

- Python 3.10+
- Node.js 18+
- MySQL 8.0+

### 1. 克隆与配置

```bash
cd V7STD

# 配置后端环境变量
cp .env.backend.example .env
# 编辑 .env 配置数据库连接信息
```

### 2. 后端启动

```bash
# 创建虚拟环境
python -m venv .venv
.venv\Scripts\activate  # Windows
# source .venv/bin/activate  # Linux/Mac

# 安装依赖
pip install -r requirements.txt

# 启动服务（开发模式）
python run_api.py
# 或
uvicorn api.main:app --reload --host 0.0.0.0 --port 8000
```

后端服务将运行在 `http://localhost:8000`

### 3. 前端启动

```bash
cd frontend
npm install
npm run dev
```

前端开发服务器将运行在 `http://localhost:3000`

### 4. 生产部署

```bash
# 前端构建
cd frontend
npm run build

# 启动生产服务（使用 run_fullstack.bat 或直接运行）
run_fullstack.bat
```

## 项目结构

```
V7STD/
├── api/                    # FastAPI 后端
│   ├── main.py            # 应用入口
│   └── routes/            # API 路由模块
│       ├── auth.py        # 认证
│       ├── inventory.py   # 库存/入库/发货
│       ├── planning.py    # 订单/合同/统筹
│       ├── users.py       # 用户管理
│       └── ...
├── core/                  # 核心逻辑
│   ├── auth.py            # JWT 认证
│   └── file_manager.py    # 文件管理
├── crud/                  # 数据库操作层
│   ├── inventory.py
│   ├── orders.py
│   └── ...
├── database.py            # 数据库连接与表定义
├── config.py              # 全局配置、角色权限
├── run_api.py             # 后端启动脚本
├── run_fullstack.bat      # 全栈启动脚本
├── frontend/              # Vue3 前端
│   ├── src/
│   │   ├── views/         # 页面组件 (17个功能页面)
│   │   ├── router/        # 路由配置
│   │   ├── store/         # Pinia 状态管理
│   ├── services/      # 业务逻辑服务 (Sandbox API/WS)
│   ├── utils/         # 通用工具 (Request 封装, 过滤器)
│   └── assets/        # 样式与静态资源
│   └── package.json
└── data/                  # 数据文件存储
    └── contracts/         # 合同附件
```

## API 文档

启动后端后，访问以下地址查看 API 文档：

- Swagger UI: `http://localhost:8000/docs`
- ReDoc: `http://localhost:8000/redoc`

### 核心接口

| 接口 | 说明 |
|------|------|
| `POST /api/v1/auth/login` | 用户登录，返回 JWT |
| `GET /api/v1/inventory/` | 库存查询 |
| `POST /api/v1/inventory/import-staging/upload` | 上传跟踪单解析 |
| `POST /api/v1/inventory/inbound-to-slot` | 按库位入库 |
| `GET /api/v1/planning/orders` | 订单列表 |
| `POST /api/v1/planning/orders` | 创建订单 |
| `POST /api/v1/planning/orders/{id}/allocate` | 订单配货 |
| `POST /api/v1/inventory/shipping/confirm` | 发货确认 |


## 默认账号

| 用户名 | 密码 | 角色 |
|--------|------|------|
| boss | 888 | Boss |
| admin | 888 | Admin |
| sales | 123 | Sales |
| prod | 123 | Prod |
| inbound | 123 | Inbound |

## 状态流转说明

```
待入库 / 已绑定 → 库存中(库位) → 待发货 → 已出库
            ↑___________________________↓
                    (发货撤回可回退)
```

> **注：** `已绑定` 状态用于跟踪已在排产计划中指派合同、但尚未实物入库的机台。
> - 沙盘批次写入（`api/routes/sandbox.py`）与跟踪单导入（`utils/parsers.py`）时，检测到合同号则状态记为 `已绑定`，否则为 `待入库`。
> - 入库审核待入库清单（`Inbound.vue`）通过 `includes('待入库')` 过滤，`已绑定` 机台不出现在该列表中。
> - 库存查询（`InventoryQuery.vue`）新增「🔗 已绑定」独立计数块与筛选选项卡。

### 订单状态

`active`（有效）→ `done`（完成）/ `deleted`（删除）

### 合同状态

`待规划` → `已规划` → `已下单` → `已转订单` → `已取消`

> **合同录入触发重算：** 非急单合同录入成功后，FastAPI 在后台线程自动向 Go 服务发起 `POST /api/forecast/recompute`，无需手动点击全量重算，约 1~2 秒后沙盘卡片即可见。

## 文档

- [工作流总览](./工作流总览.md) - 系统端到端流程说明
- [部署文档](./部署文档.md) - 详细部署指南
- [系统操作日志设计方案](./系统操作日志设计方案.md) - 日志系统设计
- [技术改造实施计划与验收](./技术改造实施计划与验收.md) - 技术升级计划

## 开发规范

- 后端采用 **FastAPI** 异步框架，路由按业务模块拆分
- 前端采用 **Vue3 Composition API** + **Element Plus** 组件库
- 数据库使用 **SQLAlchemy** 原生 SQL，配合 **pandas** 数据处理
- 权限控制采用 **JWT Token** + 前端动态路由守卫

## 许可证

MIT License

---

**V7ex** - 让库存管理更简单 🚀

## Boss Plan (FastAPI + Go)

- `run_fullstack.bat` now builds Go binary (`server/smart-scheduling-server-go.exe`) first, then starts Go (port 3001), FastAPI (port 8000), and Frontend (port 3000).
- It waits for Go health (`/api/health`) and FastAPI health (`/health`) before declaring success.
- Key available sandbox APIs:
  - `POST /api/v1/sandbox/units/repair-family-mismatches`
  - `POST /api/v1/sandbox/forecast/recompute`
  - `GET /api/v1/sandbox/model-types`
  - `GET /api/v1/sandbox/forecast/achievement`
- Permission model:
  - Read APIs require `SANDBOX_VIEW`
  - Write APIs require `SANDBOX_EDIT`
  - `Admin`/`Boss` remain compatible through role permissions.
- The sandbox automatically synchronizes (triggers background recompute) when new contracts are imported, ensuring real-time visibility without manual refreshes.
- Mobile note: `frontend-mobile` remains lightweight warehouse-facing; Boss Plan sandbox is not included by default.

### 沙盘与数据完整性优化（2026-05-14）

| 类别 | 改动摘要 |
|------|----------|
| **急单插入修复** | 修复手动急单插入 400 错误；逻辑优化为使用目标槽位的实际机型进行产线链式查找，解决急单机型不匹配导致找不到插入点的问题 |
| **数据标准化** | 执行生产中批次（In_Production）机型标准化清理，将原始机型名（如 FR-400XS）统一为族系代码（G/XS/AUTO/SPECIAL），确保调度引擎逻辑一致 |
| **同步脚本增强** | `sync_batch_app.py` 增加 `_normalize_model_family` 自动转换逻辑，所有从 ERP 同步的批次在入库前自动完成族系代码归类 |
| **产线看板增强** | `ProductionKanban.vue` 批次号与预计入库时间增大加粗显示，强化视觉反差；预计入库时间改为高对比度 Badge 样式 |
| **加高机型统计** | 「预测沙盘」目标比例表与「库存查询」机型统计表均新增「加高」列；支持非零数值高亮显示，辅助生产计划快速识别特殊配置机型 |
| **列表布局优化** | 拓宽库存查询机型统计表宽度，增加机型列最小宽度（160px），防止长机型名称换行错位 |

### 沙盘近期重要改动（2026-05-07 / 2026-05-09）

| 类别 | 改动摘要 |
|------|----------|
| **特殊机型列修复** | 信息强改抽屉中特殊列只显示归属「特殊」的具体机型，过滤 `SPECIAL/AUTO/XS/G` 大类占位值；保存时校验机型与批次系列匹配 |
| **拖拽规则修复** | 普通批次内限同系列、同大小机列拖拽；增加混放数量提示「混放 N」；拖拽后临时锁定排序，手动刷新后恢复自动排序 |
| **急单字段一致性** | 卡片增加合同备注展示；已确认/生产中卡片显示流水号；急单插入携带 `remark/order_remark/sales_id` 等字段 |
| **老板计划同步** | 批次分配产线时按「合同号+机型」将 `factory_plan` 状态从 `待规划` 更新为 `已规划`；急单插入后同步更新 |
| **成品库同步** | 急单插入/内容交换后同步 `finished_goods_data`；有合同号→`待发货`，无合同号→`待入库` |
| **批次顺延规则** | `enforceFamilyGapDays` 顺延时寻找相同容量批次，避免大小机跨列错位 |
| **合同取消联动** | 标记现货 / 合同管理取消时同步将 `rush_order_queue` 中对应急单置为 `deleted` |
| **配货双向同步** | 配货成功后通过流水号匹配将 `customer/dealer_name` 写入 `units` 表；撤回配货时清空归属信息但保留 `order_remark` |
| **移除 lru_cache** | `crud/inventory.py` 的 `get_data()` 移除 `@lru_cache`，改为每次直接查数据库，彻底消除缓存脏写覆盖机台真实状态的 Bug |
| **合同录入自动重算** | `create_contracts_batch` 录入成功后通过 `BackgroundTasks` 异步触发 Go 全量重算，无需手动点击 |
| **Vite 代理修复** | `frontend/vite.config.ts` 补充 `ws: true`，修复开发环境 WebSocket 升级请求代理失败问题 |

## Launcher EXE

- One-click startup now uses `launcher.exe` (built from `tools/launcher/main.go`).
- You can still run `run_fullstack.bat`; it bootstraps and executes `launcher.exe`.

Examples:

```bat
launcher.exe
launcher.exe --dry-run
launcher.exe --no-mobile
launcher.exe --ports go=3001,api=8000,web=3000,mobile=5174
launcher.exe --python "C:\Users\zc123\python-sdk\python3.13.2\python.exe"
```

Exit codes:
- `0` success
- `1` precheck failed
- `2` go build failed
- `3` go health check failed
- `4` process start failed
