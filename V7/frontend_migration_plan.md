# 前端重构迁移计划：从 Streamlit 到 Vue 3 + Vite + TypeScript

## 1. 现状分析
当前前端采用 Python 的 **Streamlit** 框架构建，页面结构在 `views/` 目录下：
- **核心模块**：包括生产统筹 (`boss_planning`)、合同管理 (`production`)、库存查询 (`query`)、机台档案 (`machine_archive`)、销售下单 (`sales_create`)、成品入库 (`inbound`)、订单配货 (`sales_alloc`)、发货复核 (`ship_confirm`)、机台编辑 (`machine_edit`) 和用户管理 (`user_management`)。
- **状态管理**：目前依赖于 Streamlit 的 `st.session_state`，全局状态与页面生命周期耦合紧密。
- **UI交互**：由 Python 后端驱动渲染，响应速度受限，难以实现复杂的客户端交互和动态校验。
- **架构瓶颈**：随着功能增加，单一 Streamlit 应用的性能和扩展性受限，无法很好地分离前后端职责。

## 2. 目标架构
- **核心框架**：Vue 3 (Composition API, `<script setup>`) + Vite
- **语言**：TypeScript (严格的类型安全)
- **状态管理**：Pinia (替换 `st.session_state` 的全局用户权限和共享数据管理)
- **路由管理**：Vue Router 4 (支持动态路由、权限拦截和页面缓存)
- **UI 组件库**：推荐使用 Element Plus 或 Ant Design Vue (企业级中后台组件库)
- **HTTP 客户端**：Axios (对接 FastAPI 后端)
- **测试框架**：Vitest (单元测试) + Cypress (E2E测试)

## 3. 阶段性迁移计划

### 第一阶段：基础设施建设与脚手架搭建 (当前)
- [x] 初始化 Vite + Vue 3 + TS 项目 (`frontend/`)。
- [x] 配置目录结构 (`src/views`, `src/components`, `src/store`, `src/router`, `src/api`)。
- [x] 引入 Vue Router、Pinia、Axios 及测试工具链 (Vitest)。
- [x] 制定 ESLint + Prettier 代码规范。

### 第二阶段：核心布局与公共组件开发
- 开发应用主骨架（Layout）：侧边栏导航 (Sidebar)、顶部状态栏 (Header)。
- 开发登录页面 (Login View)，对接鉴权 API。
- 在 Pinia 中实现 UserStore，接管用户登录状态和基于角色的权限控制 (RBAC)。
- 封装通用的数据表格组件、表单组件、图表容器。

### 第三阶段：业务模块逐步迁移 (敏捷迭代)
按照业务相关度分组迁移，逐步替换原有的 Streamlit 视图：
1. **基础查询类**：库存查询 (`query`)、机台档案 (`machine_archive`)。
2. **入库与生产类**：成品入库 (`inbound`)、合同管理 (`production`)、生产统筹 (`boss_planning`)。
3. **出库与销售类**：销售下单 (`sales_create`)、订单配货 (`sales_alloc`)、发货复核 (`ship_confirm`)。
4. **管理后台**：用户管理 (`user_management`)、系统日志。

*策略：并行运行*
在过渡期，可以让 FastAPI 后端同时支持 Vue SPA 和旧版 Streamlit，确保平滑过渡，最终下线 Streamlit。

### 第四阶段：测试、优化与发布
- 为核心业务逻辑 (如数据转换、验证规则) 编写 Vitest 单元测试。
- 使用 Cypress 编写核心业务流 (如：入库 -> 配货 -> 发货) 的 E2E 测试。
- 进行移动端适配和响应式样式调整 (CSS Modules / TailwindCSS)。
- 性能优化：路由懒加载、组件异步加载、打包体积优化。
- 自动化 CI/CD 部署。
