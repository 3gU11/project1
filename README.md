# V7ex 成品库存管理系统

> 面向制造业的机台库存全生命周期管理平台

## 项目概述

V7ex 是一个专为制造企业设计的成品库存管理系统，围绕 **"合同 → 订单 → 库存 → 入库 → 发货 → 档案"** 形成业务闭环，支持多角色协作、库位可视化、交易追溯等核心功能。

## 技术架构

| 层级 | 技术栈 |
|------|--------|
| **前端** | Vue 3 + TypeScript + Element Plus + Pinia + Vite |
| **后端** | FastAPI + Python 3.10+ |
| **数据库** | MySQL 8.0 (SQLAlchemy + pandas) |
| **文档解析** | PaddleOCR + pdfplumber + mammoth |
| **部署** | Uvicorn + 静态文件服务 |

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
| 🏭 合同管理 | 合同录入、附件上传、状态流转 | Boss, Sales |
| 📝 销售下单 | 创建销售订单、指定机型数量 | Sales |
| 📦 订单配货 | 从库存锁定机台、释放配货 | Sales |
| 📥 成品入库 | 跟踪单解析、待入库清单、按库位入库 | Prod, Inbound |
| 🚛 发货复核 | 确认发货、发货撤回 | Prod |
| 🔧 机台档案 | 机台文件上传、预览、下载 | Prod |
| 🗺️ 库位大屏 | 可视化库位占用情况 | 全角色 |
| 🔍 库存查询 | 多条件筛选、状态统计 | 全角色 |
| 🔍 汇总追溯 | 批次追溯、交易链路查询 | Boss, Sales |

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

前端开发服务器将运行在 `http://localhost:5173`

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
│   │   └── api/           # API 请求封装
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

### 库存机台状态

```
待入库 → 库存中(库位) → 待发货 → 已出库
            ↑___________________________↓
                    (发货撤回可回退)
```

### 订单状态

`active`（有效）→ `done`（完成）/ `deleted`（删除）

### 合同状态

`待规划` → `已规划` → `已下单` → `已转订单` → `已取消`

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
