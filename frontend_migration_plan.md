# V7ex 成品管理系统：前后端分离重构计划

## 1. 现状评估与重构背景

### 1.1 当前架构痛点 (Streamlit)
- **渲染性能瓶颈**：Streamlit 基于 Python 后端渲染，每次用户交互（如点击、输入）都会触发整个页面的重新执行。随着业务逻辑变复杂、数据量增加，系统出现明显的卡顿和白屏。
- **冷启动缓慢**：应用启动时需加载大量 Python 库和执行复杂的初始化逻辑（如全表扫描），导致用户首次打开登录页耗时过长。
- **UI 交互受限**：受限于 Streamlit 自身的组件库，难以实现复杂的业务级交互（如复杂的拖拽排产、多级联动的表格数据展示、丝滑的动画过渡）。
- **状态管理困难**：全局状态（Session State）管理复杂，容易出现状态混乱，特别是对于像“30 天免登录”这样的基础功能，实现起来既麻烦又存在性能损耗。
- **资源浪费严重**：所有的视图渲染压力集中在服务器端，并发访问时 CPU 和内存占用飙升。

### 1.2 重构目标
- **彻底的前后端分离**：前端负责所有 UI 渲染和交互逻辑，后端退化为纯净的数据接口（API）服务。
- **极致的加载速度**：登录页实现毫秒级首屏秒开，页内操作零延迟刷新。
- **灵活的 UI 扩展**：释放前端潜力，能够接入成熟的商业级组件库，满足未来复杂的业务需求。
- **平滑迁移**：采用渐进式重构策略，最大程度复用现有的核心业务代码（如 `crud/`、`database.py`）。

---

## 2. 技术选型与架构设计

### 2.1 前端技术栈 (Vue 3 体系)
- **核心框架**：**Vue 3 (Composition API) + TypeScript**
  - 理由：性能优异、响应式系统强大、类型安全，适合构建大型后台管理系统。
- **构建工具**：**Vite**
  - 理由：冷启动极快，热更新(HMR)瞬间完成，显著提升开发体验。
- **UI 组件库**：**Element Plus**
  - 理由：国内生态最好、组件最全的 Vue 3 组件库，极度契合后台管理系统的设计需求。
- **状态管理**：**Pinia**
  - 理由：Vue 官方推荐的新一代状态管理库，轻量、类型安全、无冗余的 mutations。
- **路由管理**：**Vue Router 4**
  - 理由：Vue 官方路由，支持动态路由和路由守卫（用于权限拦截）。
- **网络请求**：**Axios**
  - 理由：支持拦截器，方便统一处理 Token 注入和全局错误提示。

### 2.2 后端技术栈 (Python API 体系)
- **核心框架**：**FastAPI**
  - 理由：基于 Starlette 和 Pydantic，极高的运行性能，原生支持异步（Async），自动生成交互式 API 文档（Swagger UI）。
- **ORM 与数据库**：**SQLAlchemy + PyMySQL** (保留现有)
  - 理由：最大程度复用现有的 `database.py` 和 `crud/` 层代码。
- **认证与授权**：**JWT (JSON Web Tokens)**
  - 理由：无状态的认证方式，完美适配前后端分离架构，前端将 Token 存在 localStorage/SessionStorage 中。

### 2.3 整体架构图
```mermaid
graph TD
    Client[浏览器 (Vue 3 SPA)]
    subgraph 前端
        UI[Element Plus 组件]
        Store[Pinia 状态管理]
        Router[Vue Router]
        Axios[Axios 请求拦截]
    end
    
    API[FastAPI (后端接口)]
    subgraph 后端
        Auth[JWT 鉴权层]
        Routes[API 路由层]
        Services[业务逻辑层]
        CRUD[数据访问层 SQLAlchemy]
    end
    
    DB[(MySQL 数据库)]
    
    Client -->|1. 加载静态资源| UI
    UI -->|2. 用户交互触发| Store
    Store -->|3. 发起请求| Axios
    Axios -->|4. HTTP 请求带 Token| Auth
    Auth -->|5. 路由分发| Routes
    Routes -->|6. 调用服务| Services
    Services -->|7. 执行 SQL| CRUD
    CRUD <-->|8. 读写数据| DB
```

---

## 3. 渐进式实施路径

为了降低重构风险，保证业务不中断，建议分三个阶段进行。

### 阶段一：基础设施搭建与登录模块打通 (1-2 周)
**目标**：跑通前后端分离的最基本骨架，实现新前端的登录。

1. **后端 API 初始化**
   - 引入 FastAPI 依赖。
   - 创建 `api/main.py` 作为新入口。
   - 实现全局的 JWT 生成与验证中间件。
   - 开发基础 API：
     - `POST /api/auth/login` (返回 JWT Token)
     - `POST /api/auth/register`
     - `GET /api/users/me` (获取当前登录用户信息及权限)

2. **前端工程初始化**
   - 使用 Vite 创建 Vue 3 项目 (例如在根目录创建 `frontend/` 文件夹)。
   - 配置 Element Plus、TailwindCSS (可选)、Pinia、Vue Router。
   - 封装 Axios，添加 Request 拦截器（自动附带 Token）和 Response 拦截器（统一处理 401/403 等错误）。

3. **重写登录模块**
   - 开发全新的 Vue 3 登录/注册页面。
   - 实现“30 天免登录”逻辑（将 Token 持久化到 localStorage）。
   - 实现路由守卫，未登录自动跳转到 `/login`。

### 阶段二：核心业务模块逐个迁移 (3-6 周)
**目标**：将现有的 Streamlit 页面按模块逐步改写为 API + Vue 组件。期间，新老系统可共存。

1. **基础布局开发**
   - 开发带有左侧动态菜单、顶部导航栏的 `Layout.vue` 组件。
   - 菜单应根据用户的 Role 权限动态渲染。

2. **模块迁移优先级建议**
   - **高优 (相对独立、基础的数据)**：
     - 用户管理 (`user_management`)
     - 基础数据查询 (`query`)
     - 成品入库/出库 (`inbound` / `ship_confirm`)
   - **中优 (带一定复杂交互)**：
     - 销售分配 (`sales_alloc`)
     - 生产管理 (`production`)
   - **低优 (极度复杂或依赖重)**：
     - 老板排产看板 (`boss_planning`) -> 这将是 Vue 3 优势最大的地方，可设计更复杂的拖拽交互。
     - 机器档案/文件管理 (`machine_archive`) -> 涉及文件上传下载 API 的改造。

3. **后端 API 开发规范**
   - 针对每个迁移的模块，在后端新建对应的 `router` 文件（如 `api/routes/inventory.py`）。
   - 严格定义 Pydantic Schema（Request/Response 模型），享受 FastAPI 自动校验的红利。
   - 将原 `views/` 中的 Python 业务逻辑下沉到 API 的 Service 层。

### 阶段三：全面割接与优化上线 (1-2 周)
**目标**：下线 Streamlit，进行全站性能压测和细节打磨。

1. **全面割接**
   - 确认所有 `views/*.py` 模块已完全在前端复刻。
   - 停止运行 `streamlit run app.py`。
   - 配置 Nginx/Caddy 等 Web 服务器，将前端静态文件托管，并将 `/api` 前缀的请求反向代理到 FastAPI 后端。

2. **细节优化**
   - **权限细化**：利用 Vue 的自定义指令（如 `v-auth`）实现按钮级别的权限控制。
   - **状态持久化**：使用 `pinia-plugin-persistedstate` 处理刷新页面丢失状态的问题。
   - **打包优化**：Vite 构建优化，路由懒加载，组件按需引入，减少首屏 JS 体积。

---

## 4. 风险评估与应对策略

| 风险点 | 影响程度 | 应对策略 |
| :--- | :--- | :--- |
| **API 开发量过大** | 高 | 尽可能复用原有的 `crud/` 层函数，仅在外面包一层 FastAPI 的路由和 Pydantic 校验。 |
| **前端组件库学习成本** | 中 | 统一团队规范，首选 Element Plus 现成的 ProTable、Form 组件，避免手写复杂样式。 |
| **新旧系统切换期间数据不一致** | 低 | 只要保证新旧系统连接同一个 MySQL 数据库实例，且核心的 DML (增删改) 逻辑不变更，数据即可保持一致。 |
| **文件上传/下载接口重构复杂** | 中 | FastAPI 对 `UploadFile` 和 `FileResponse` 的支持非常完善，需注意在前端使用 FormData 格式提交，并在 Nginx 中调整最大上传体积限制。 |

## 5. 前端无缝更新方案设计 (打扰最小化)

在前后端分离架构下，前端 SPA（单页应用）的每次构建部署都会生成新的带 hash 值的文件名，老文件会被覆盖。如果用户一直停留在老页面上未刷新，点击菜单跳转时，Vue Router 会因为找不到老文件而报错（`ChunkLoadError`）导致白屏。为了解决这一痛点，我们设计了如下**无感知更新机制**：

### 5.1 方案原理
1. **打包植入版本标识**：通过自定义 Vite 插件，在每次执行 `npm run build` 时，自动在 `dist` 目录下生成一个包含当前时间戳的 `version.json` 文件。
2. **前端静默轮询**：应用启动后，在后台每隔固定时间（如 5 分钟），以及每次页面重新获得焦点（`visibilitychange`）时，静默请求一次服务端的 `version.json`。
3. **路由级延迟刷新（核心）**：一旦检测到服务端版本号发生变化，**不立即强制刷新**（防止打断用户正在进行的表单填写或弹窗操作）。而是将应用标记为“已过期”。
4. **平滑更替**：当且仅当用户**下一次点击侧边栏菜单进行路由跳转时**，拦截该跳转，将其替换为一次对目标页面的 `window.location.href` 硬跳转。用户只会感受到一次极快的页面加载，而在这一瞬间，新版本代码已生效。
5. **防白屏兜底**：在 Vue Router 的 `onError` 钩子中全局捕获 `ChunkLoadError`。如果发生该错误（通常是由于缓存或手速过快），自动执行一次 `window.location.reload()` 兜底。

### 5.2 实施步骤（代码参考）

- **Vite 插件 (`vite.config.ts`)**:
  ```typescript
  import fs from 'fs'
  import path from 'path'
  
  const versionUpdatePlugin = () => ({
    name: 'version-update-plugin',
    writeBundle() {
      const distPath = path.resolve(__dirname, 'dist')
      if (!fs.existsSync(distPath)) fs.mkdirSync(distPath)
      fs.writeFileSync(path.resolve(distPath, 'version.json'), JSON.stringify({ version: Date.now() }))
    }
  })
  ```
- **后台检测逻辑 (`src/utils/updater.ts`)**:
  利用 `fetch('/version.json?t=' + Date.now())` 对比版本号，并维护一个全局变量 `isOutdated`。
- **路由拦截 (`src/router/index.ts`)**:
  ```typescript
  router.beforeEach((to, from, next) => {
    if (hasNewVersion() && to.fullPath !== from.fullPath) {
      window.location.href = to.fullPath // 触发浏览器硬重载加载新版本
      return
    }
    // ... 原有逻辑
  })
  
  router.onError((error, to) => {
    if (error.message.match(/Failed to fetch dynamically imported module/i)) {
      window.location.href = to.fullPath // 兜底策略
    }
  })
  ```

## 6. 部署与上线策略 (一键覆盖)

为了确保重构上线过程的平稳和最小化运维成本，我们采用**本地试运行成功后，直接在服务器进行完全覆盖**的部署策略。

### 6.1 本地全量试运行 (Pre-flight Check)
在正式部署到生产服务器之前，必须在本地完成前后端联合测试：
1. **本地环境对齐**：确保本地运行的 MySQL 数据库表结构、Python 环境依赖（`requirements.txt`）、Node.js 环境与服务器保持一致。
2. **全链路验证**：
   - 启动本地 FastAPI 后端：`uvicorn api.main:app --reload`
   - 启动本地 Vite 前端：`npm run dev`
   - 走通核心业务流：登录验证 -> 菜单权限控制 -> 报表查询 -> 表单提交与文件上传。
3. **前端生产包构建测试**：在本地执行 `npm run build`，使用本地 Nginx 或简单的 HTTP Server 代理 `dist` 目录，验证生产包（特别是打包后的 Chunk 路径和无缝更新插件）是否工作正常。

### 6.2 服务器完全覆盖上线 (Server Override)
本地测试通过后，执行直接覆盖的上线动作：

1. **前端部署 (Nginx 托管)**
   - 在本地执行 `npm run build` 生成最终的 `dist` 文件夹。
   - 将 `dist` 文件夹打包上传到服务器。
   - 清空服务器原有前端目录（如果有），解压新 `dist` 到 Nginx 配置的 `root` 路径。
   - **重要**：由于我们已经实现了**前端无缝更新方案 (第 5 节)**，直接覆盖前端文件**不会**导致在线用户白屏报错，用户会在下一次点击菜单时自动平滑过渡到新版本。

2. **后端部署 (服务替换)**
   - 将最新的 Python 后端代码同步到服务器。
   - 停止旧的 Streamlit 服务进程（如 `systemctl stop streamlit` 或 kill 进程）。
   - 安装新的 Python 依赖（如果引入了 FastAPI 等新库）。
   - 启动新的 FastAPI 服务，推荐使用 Uvicorn + Gunicorn 组合以获得更好的并发性能：
     ```bash
     gunicorn api.main:app -w 4 -k uvicorn.workers.UvicornWorker -b 0.0.0.0:8000
     ```

3. **Nginx 路由配置更新**
   - 确保 Nginx 将前端路由的回退交给 `index.html`，并将 `/api` 请求代理到 FastAPI：
     ```nginx
     server {
         listen 80;
         server_name yourdomain.com;
         
         # 托管前端 Vue 打包后的静态文件
         location / {
             root /path/to/your/dist;
             index index.html;
             try_files $uri $uri/ /index.html; # Vue Router 必须配置
         }
         
         # 代理后端 API
         location /api/ {
             proxy_pass http://127.0.0.1:8000/;
             proxy_set_header Host $host;
             proxy_set_header X-Real-IP $remote_addr;
         }
     }
     ```
   - 重载 Nginx 配置：`nginx -s reload`。

### 6.3 回滚预案
虽然采用直接覆盖策略，但仍需保留快速回退能力：
- 覆盖前，对服务器的原代码目录进行完整压缩备份。
- 若上线后发现严重 Bug 且短时间无法修复，立即停止 FastAPI，重启 Streamlit 进程，并还原 Nginx 配置，即可在 1 分钟内恢复到原 Streamlit 版本。

---

## 7. 预期收益总结
实施此计划后，V7ex 系统将脱胎换骨：
1. **彻底告别白屏和卡顿**，用户体验达到现代 Web 应用标准。
2. **服务器负载显著降低**，可以支持更多的并发用户访问。
3. **前端交互能力解除封印**，排产、报表等核心业务场景可以进行更深度的定制开发。
4. **架构清晰，易于维护**，前端和后端团队可以独立并行开发，提升迭代效率。
5. **零感知版本升级**，发布新功能再也无需通知业务人员“清理浏览器缓存”。