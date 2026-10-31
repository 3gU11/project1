# V8 系统安全审计报告（2026-10-30）

> 审计对象：`F:\work\V8\project1`（FastAPI 业务中台 + Go 调度引擎 + Vue 管理端）
> 审计方式：代码审计 + 本地沙盘复现
> 审计结论：**确认 7 项真实安全问题，其中 2 项严重、4 项高危（含 1 项条件触发、1 项配置类）、1 项中危。**
> 说明：本报告只记录已在沙盘或本地运行实例中实际复现的问题；未复现的猜测不写入结论。

---

## 一、测试范围与方法

### 1.1 沙盘隔离措施

为避免影响现有业务数据，写操作全部在克隆环境中完成：

- 使用 `mysqldump` 将 `rjfinshed_v8_import` 克隆为 `rjfinshed_vuln_test`（104 张表）。
- FastAPI 以 `MYSQL_DB=rjfinshed_vuln_test` 在进程内通过 `TestClient` 启动；设置 `V8_DEMO_MODE=1`，关闭云端拉取/推送/同步。
- Go 调度服务以 `DB_NAME=rjfinshed_vuln_test`、`HTTP_ADDR=127.0.0.1:3002` 单独启动，验证写入能力。
- 读取类验证同时在本地运行实例 `127.0.0.1:8000` 上完成。
- 测试产生的订单、用户、合同记录和探针文件均在测试后清理；未修改生产库 `rjfinshed_v8_import` 的业务数据。

### 1.2 测试账号

| 账号 | 角色 | 权限 |
|---|---|---|
| `admin` / `888` | Admin | 全部管理权限（当前实例默认口令） |
| `inbound` / `123` | Inbound | 仅 `INBOUND`、`WAREHOUSE_MAP` |

`inbound` 被用作“低权限已登录用户”的基准，用来验证功能级权限是否真正生效。

### 1.3 结果摘要

| 编号 | 严重性 | 问题 | 状态 |
|---|---|---|---|
| F-01 | 严重 | Go 调度服务认证绕过，可未授权读写管理数据 | 已复现 |
| F-02 | 严重 | 机台档案路径穿越读取任意文件，泄露 JWT 密钥并可伪造管理员令牌 | 已复现 |
| F-03 | 高危 | 机台档案路径穿越删除项目根目录任意文件 | 已复现 |
| F-04 | 高危 | 计划/合同写接口缺少功能级权限，低权限用户可改业务数据 | 已复现 |
| F-05 | 高危（上传条件触发；删除当前可利用） | 合同附件上传/删除越权 + 文件名路径穿越写入 | 沙盘已复现；上传开关关闭，删除接口当前可直接调用 |
| F-06 | 中危 | 账号被拒绝或删除后，已签发令牌仍然有效 | 已复现 |
| F-07 | 高危（配置） | 默认/弱口令且默认账号会自动重新播种 | 已复现 |

---

## 二、详细发现

### F-01 严重：Go 调度服务认证绕过

#### 位置

- `server/internal/middleware/auth.go:13-31`：`AdminOnly` 直接信任请求头 `X-Username`、`X-Role`。
- `server/internal/middleware/auth.go:34-53`：没有请求头时，接受 `Authorization: Bearer user:role` 明文角色。
- `server/internal/middleware/auth.go:55-72`：解析 JWT 时只做 Base64 解码，**不校验签名、过期时间和算法**。
- `server/internal/router/router.go:42-45, 73`：`/api/v1` 管理路由和 `/api/*` 全部挂在该中间件下。
- `server/internal/config/config.go:40`：默认监听 `:3001`，即所有网卡。
- 实测 `netstat`：`TCP 0.0.0.0:3001 LISTENING`；`http://172.21.8.169:3001/api/health` 返回 200。

#### 复现

1. 未认证访问被拒绝（对照组）：

```http
GET /api/batches HTTP/1.1
Host: 127.0.0.1:3002
```

结果：`403 {"error":"forbidden: admin or boss role required"}`

2. 伪造两个请求头即可获得管理员身份：

```http
GET /api/batches HTTP/1.1
Host: 127.0.0.1:3002
X-Username: attacker
X-Role: admin
```

结果：`200`，返回批次、机型、产能、状态等完整排产数据。

3. 使用明文角色令牌同样通过：

```http
GET /api/batches HTTP/1.1
Authorization: Bearer attacker:admin
```

结果：`200`。

4. 使用**未签名**的 JWT（`alg=none`）同样通过：

```
header  = {"alg":"none","typ":"JWT"}
payload = {"sub":"attacker","role":"admin"}
token   = base64url(header) + "." + base64url(payload) + "."
```

结果：`200`。

5. 写入验证（在克隆库的 3002 沙盘上）：

```http
PATCH /api/capacity-ratio HTTP/1.1
X-Username: attacker
X-Role: admin
Content-Type: application/json

{ ...读取到的 ratio... }
```

结果：`200 {"success":true}`，管理配置被成功修改。

6. 通过局域网地址复验：

```http
GET http://172.21.8.169:3001/api/capacity-ratio
X-Username: attacker
X-Role: admin
```

结果：`200`，返回产能比例配置。

#### 影响

任何能访问 3001 端口的人（局域网内无需账号）都可以：

- 读取全部批次、机台、排产队列、产能配置、预测结果；
- 修改产能比例、批次、工位、急单、预测重算等核心生产数据；
- 触发批次确认/撤销、工位调整、急单插入、预测重算等会写业务数据的操作；
- 绕过 FastAPI 的业务权限模型，直接以 Admin 身份操作 Go 服务。

这是本次审计中最严重的问题，属于**认证完全绕过**，不是普通越权。

#### 修复建议

1. 删除对 `X-Username` / `X-Role` 的信任；身份只能来自经过签名校验的凭据。
2. JWT 必须校验签名、`exp`、`alg`，禁止 `none` 和无签名解析；密钥与 FastAPI 共用 `V8_JWT_SECRET` 或改用非对称密钥。
3. 删除 `Bearer user:role` 的兼容分支。
4. Go 服务默认只监听 `127.0.0.1`；如必须跨机部署，使用内网 ACL/mTLS，并在反向代理层剥离客户端传入的 `X-Username`、`X-Role`。
5. FastAPI 代理到 Go 时，使用独立的服务间凭据（如 `X-Internal-Token`）并让 Go 强制校验，不能只依赖 FastAPI 已校验。
6. 增加“无凭据/伪造头/`alg=none`”回归测试，防止以后重新引入。

---

### F-02 严重：机台档案路径穿越读取任意文件，并伪造管理员 JWT

#### 位置

- `api/routes/inventory.py:2244-2254`：

```python
def _safe_name(value: str) -> str:
    return re.sub(r'[\\/*?:"<>|]', "", str(value or "")).strip()

def _ensure_sn_dir(serial_no: str) -> str:
    safe_sn = _safe_name(serial_no)
    ...
    sn_dir = os.path.join(MACHINE_ARCHIVE_ABS_DIR, safe_sn)
    os.makedirs(sn_dir, exist_ok=True)
```

`_safe_name` 只去掉斜杠等字符，**没有拒绝 `.` 和 `..`**。传入 `serial_no=".."` 时，`sn_dir` 变成 `machine_archives/..`，即项目根目录。

- `api/routes/inventory.py:2353-2361`：下载时把 `file_name` 经 `_safe_name` 后直接拼到上述目录。
- 机台档案的列表、下载、缩略图、预览等读取路由只要求 `get_current_user_token`（`api/routes/inventory.py:51` 的 router 依赖），**不要求 ARCHIVE 权限**，任何已登录用户都可访问。

#### 复现

使用 `inbound`（只有 `INBOUND`、`WAREHOUSE_MAP`）登录后：

```http
GET /api/v1/inventory/machine-archive/%2E%2E/files HTTP/1.1
Authorization: Bearer <inbound token>
```

结果：`200`，返回项目根目录文件列表，其中包含 `.env`、`launcher.exe`、日志和备份文件。

```http
GET /api/v1/inventory/machine-archive/%2E%2E/files/.env/download HTTP/1.1
Authorization: Bearer <inbound token>
```

结果：`200`，返回项目 `.env` 全文（实测约 1.3 KB，1488 字节），其中包含：

- `MYSQL_PASSWORD` / `DB_PASSWORD`
- `V8_JWT_SECRET`
- `CONTRACT_BRIDGE_KEY`
- `V7_API_KEY`
- `V8_SYNC_SECRET`

进一步验证影响链：

1. 从 `.env` 读取 `V8_JWT_SECRET`（64 字符）。
2. 用该密钥签发 `HS256` JWT：`{"sub":"admin","role":"Admin"}`。
3. 访问管理员接口：

```http
GET /api/v1/users/ HTTP/1.1
Authorization: Bearer <forged admin token>
```

结果：`200`，返回全部用户数据；`GET /api/v1/roles/` 同样 `200`。

#### 影响

- 任意已登录用户（包括权限最低的 `Inbound`）可以读取项目根目录任意文件。
- `.env` 泄露后，攻击者可以：
  - 伪造管理员 JWT，完全接管 FastAPI 管理端；
  - 获取数据库口令、云端桥接密钥、V8 同步密钥，横向影响云端和同步链路；
  - 结合 F-03 删除关键文件，造成服务不可用。
- 由于 `machine_archives` 与项目根目录只隔一层，路径穿越只需一个 `..`，利用成本极低。

#### 修复建议

1. `_safe_name` 拒绝 `.`、`..`、空字符串、绝对路径和任何路径分隔符；更好的做法是使用白名单字符集。
2. 拼接后必须做真实路径校验：

```python
base = Path(MACHINE_ARCHIVE_ABS_DIR).resolve()
target = (base / safe_sn / safe_file).resolve()
if target == base or base not in target.parents:
    raise HTTPException(400, "非法路径")
```

3. 不要在用户可控路径上执行 `os.makedirs`；先校验目录是否已存在或由服务端生成。
4. 机台档案列表、下载、缩略图、预览、删除都应要求 `ARCHIVE` 权限；目前列表/下载只有登录校验。
5. 轮换 `.env` 中已经暴露的密钥（尤其是 `V8_JWT_SECRET`、数据库口令、云端密钥），并检查历史日志/备份是否已外泄。

---

### F-03 高危：机台档案路径穿越删除任意文件

#### 位置

- `api/routes/inventory.py:2451-2464`：`machine_archive_delete` 与 F-02 使用同一套 `_ensure_sn_dir` / `_safe_name`。
- 删除路由要求 `ARCHIVE` 权限，但拼接逻辑没有阻止 `..`。

#### 复现

在项目根目录创建探针文件 `security_delete_probe.txt`，使用 `admin`（具备 `ARCHIVE`）执行：

```http
DELETE /api/v1/inventory/machine-archive/%2E%2E/files/security_delete_probe.txt HTTP/1.1
Authorization: Bearer <admin token>
```

结果：`200`，探针文件被删除。

对照：`inbound` 没有 `ARCHIVE` 权限，同一请求返回 `403`，说明删除接口的权限本身有效，问题在于**有权限的用户可以越出档案目录删除任意文件**。

#### 影响

具备 `ARCHIVE` 的角色（Admin、Boss、Prod）可以删除项目根目录中的：

- `.env`（导致服务配置丢失/重启失败）；
- `launcher.exe`、启动脚本、日志；
- 其他根目录业务文件。

属于破坏性漏洞，可造成服务中断或证据销毁。

#### 修复建议

同 F-02：删除前必须做 `resolve()` + `relative_to()` 校验，拒绝 `.`/`..`，并只允许删除档案目录内、文件名合法的普通文件。

---

### F-04 高危：计划/合同写接口缺少功能级权限

#### 位置

`api/routes/planning.py` 的 router 只挂了 `get_current_user_token`（第 53 行），大量写接口只依赖 `get_current_user_context` 或 `get_current_operator_name`，**没有** `require_permissions(...)`：

| 接口 | 行号 | 应需要的权限 |
|---|---|---|
| `POST /planning/orders` | 2821 | `SALES_CREATE` |
| `PUT /planning/orders/{order_id}` | 3496 | `SALES_CREATE` |
| `POST /planning/orders/{order_id}/allocate` | 3660 | `SALES_ALLOC` |
| `POST /planning/orders/{order_id}/complete-allocation` | 3773 | `SALES_ALLOC` |
| `POST /planning/orders/{order_id}/release` | 3847 | `SALES_ALLOC` |
| `POST /planning/contract/{contract_id}/status` | 3899 | `CONTRACT` |
| `POST /planning/contract/{contract_id}/link-order` | 3996 | `CONTRACT` |
| `POST /planning/contracts/batch-create` | 4179 | `CONTRACT` |
| `PUT /planning/contract/{contract_id}` | 4309 | `CONTRACT` |
| `POST /planning/contract/{contract_id}/save-plan` | 4532 | `CONTRACT` |
| `POST /planning/contract/{contract_id}/files` | 4400 | `CONTRACT` |
| `DELETE /planning/contract/{contract_id}/files/{file_name}` | 4427 | `CONTRACT` |

`GET /planning/orders`、`GET /planning/orders/{id}/allocations` 等读接口反而正确要求了 `SALES_ALLOC`，说明这是写接口遗漏，而不是有意放开。

#### 复现

使用 `inbound`（无 `SALES_CREATE`、`SALES_ALLOC`、`CONTRACT`）：

1. 创建销售订单：

```http
POST /api/v1/planning/orders HTTP/1.1
Authorization: Bearer <inbound token>
Content-Type: application/json

{"客户名":"SEC-AUDIT-CUSTOMER","需求机型":"FH-300C","需求数量":1}
```

结果：`200`，返回 `order_id=SO-20261030-9590`，订单成功写入克隆库。

2. 修改合同状态：

```http
POST /api/v1/planning/contract/CODEX-TEST-20261014-001/status HTTP/1.1
Authorization: Bearer <inbound token>
Content-Type: application/json

{"status":"生产中"}
```

结果：`200`，合同状态被成功修改（测试后已恢复原状态）。

3. 其余接口按同一模式缺少权限依赖；其中 `DELETE /planning/orders/{order_id}` 已用 `409` 强制走逆向审批，不属于可利用项。

#### 影响

低权限的入库员可以：

- 创建、修改销售订单；
- 修改合同状态、绑定订单、批量创建合同、编辑合同、保存排产计划；
- 配货、完成配货、释放库存；
- 上传/删除合同附件（上传开关见 F-05）。

这会直接破坏订单、合同、排产和库存数据的完整性和审计可信度，且可被用于伪造业务记录或释放/占用库存。

#### 修复建议

1. 为每个写接口增加明确的 `Depends(require_permissions("..."))`：
   - 订单创建/修改：`SALES_CREATE`
   - 配货/释放/完成配货：`SALES_ALLOC`
   - 合同状态/编辑/批量创建/绑定/排产/附件：`CONTRACT`
2. 不要只在 Vue 前端隐藏按钮；服务端必须独立校验。
3. 建立“路由 → 所需权限”的集中映射，并在启动时检查所有写路由是否声明了权限，防止新增接口再次遗漏。
4. 增加低权限角色（Inbound/AfterSales）调用写接口应返回 403 的回归测试。

---

### F-05 高危：合同附件删除越权（当前可利用）+ 上传条件触发 + 文件名路径穿越写入

> 当前运行实例未设置 `V8_UPLOADS_ENABLED`，**上传**接口返回 `503`；但**删除**接口没有上传开关依赖，当前即可被低权限用户调用。沙盘中上传和删除均已完整复现，线上删除接口也已验证可达。

#### 位置

- `api/routes/planning.py:4399-4416`：上传接口只依赖 `get_current_operator_name` 和 `require_uploads_enabled`，没有 `CONTRACT` 权限。
- `api/routes/planning.py:4426-4434`：删除接口只依赖 `get_current_operator_name`，没有 `CONTRACT` 权限。
- `core/file_manager.py:38-57`：

```python
fname = getattr(uploaded_file, "name", None) or getattr(uploaded_file, "filename", None) or "upload.bin"
...
safe_cust = re.sub(r'[\/*?:"<>|]', "", str(customer_name)).strip() or "Unknown"
if contract_id:
    folder_name = re.sub(r'[\/*?:"<>|]', "", str(contract_id)).strip()
...
save_path = os.path.join(abs_dir, fname)
```

`fname` 完全没有经过 `Path(...).name` 或 `..` 过滤，攻击者可以提交 `../../任意文件名.pdf`。

#### 复现（沙盘 `V8_UPLOADS_ENABLED=true`）

使用 `inbound`：

1. 路径穿越上传：

```http
POST /api/v1/planning/contract/SEC-AUDIT/files HTTP/1.1
Authorization: Bearer <inbound token>
Content-Type: multipart/form-data

file=("../../security_upload_probe.pdf", <PDF bytes>)
```

结果：`200 {"message":"上传成功"}`，文件实际写入：

```
F:\work\V8\project1\security_upload_probe.pdf
```

数据库记录中的 `file_path` 为：

```
data\SEC-AUDIT\../../security_upload_probe.pdf
```

2. 普通上传后，使用同一低权限账号删除：

```http
DELETE /api/v1/planning/contract/SEC-AUDIT/files/sec_delete_me.pdf HTTP/1.1
Authorization: Bearer <inbound token>
```

结果：`200 {"message":"文件已删除"}`，文件从磁盘删除。

3. 线上（未开启上传）验证删除接口仍然可达，但未删除任何真实文件：

```http
GET /api/v1/planning/contract/<真实合同号>/files
Authorization: Bearer <inbound token>
```

结果：`200`，返回该合同全部附件名、路径和上传人——低权限用户可先枚举目标文件名。

```http
DELETE /api/v1/planning/contract/<真实合同号>/files/not-exist.pdf
Authorization: Bearer <inbound token>
```

结果：`422 {"detail":"文件记录未找到"}`，而不是 `403` 或 `503`，说明删除接口已通过权限/开关检查；只要文件名存在即可删除。

#### 影响

低权限用户当前即可：

- 枚举任意合同的附件名、路径、上传人；
- 删除任意合同附件记录及对应文件（当前删除接口无上传开关、无 `CONTRACT` 权限校验）。

开启上传后，还可：

- 在项目任意位置写入 `.pdf/.doc/.docx/.jpg/.jpeg` 文件（可覆盖已有附件、写满磁盘、投放恶意文档）；
- 配合合同附件下载/预览接口，形成“上传—记录—下载”的完整滥用链。

#### 修复建议

1. 上传和删除都增加 `require_permissions("CONTRACT")`。
2. `fname = Path(str(fname)).name`，拒绝包含 `..`、路径分隔符、绝对路径和控制字符的名称；最终文件名使用服务端 UUID。
3. `contract_id` 必须先查询 `contract_records`/合同表确认存在，并限制字符集；不要直接把用户输入拼进目录。
4. 上传目录做 `resolve()` 校验，确保最终路径位于服务端生成的 `data/<合同目录>` 白名单目录内。
5. 对上传内容做类型/魔数校验，而不仅看扩展名。

---

### F-06 中危：账号被拒绝或删除后，已签发令牌仍然有效

#### 位置

- `api/routes/auth.py:75-83`：`get_current_user_token` 只做 JWT 解码，**不查数据库、不检查 `status`**。
- `api/routes/auth.py:86-103`：`get_current_user_context` 查了用户，但**没有检查 `status` 是否为 active**。
- `api/routes/users.py:194-248`：管理员可以把用户状态改为 `rejected` 或删除用户，但没有吊销已签发令牌。
- JWT 有效期 30 天（`api/routes/auth.py:23`）。

#### 复现

1. 创建并登录一个 `Sales` 测试用户。
2. 用其令牌访问受 `SALES_ALLOC` 保护的 `GET /api/v1/planning/orders`：`200`。
3. 将该用户状态改为 `rejected`，等待 5 秒让 5 秒用户缓存过期。
4. 再次访问：
   - `GET /api/v1/auth/me` → `200`
   - `GET /api/v1/planning/orders` → `200`
5. 删除该用户，等待缓存过期：
   - `GET /api/v1/inventory/machine-archive/serials` → `200`
   - `GET /api/v1/auth/me` → `401`

#### 影响

- 被拒绝、停用、离职的账号在令牌过期前仍可访问系统；`rejected` 用户甚至保留完整业务访问能力。
- 删除用户只对“查数据库的接口”生效；所有只用 `get_current_user_token` 的接口（库存、机台档案、计划等）仍接受旧令牌。
- 与 F-02 组合时，已删除账号仍可读取 `.env`，进而伪造管理员令牌。

#### 修复建议

1. `get_current_user_token` 也必须加载用户并校验 `status == 'active'`；或统一改用 `get_current_user_context`。
2. 在用户表增加 `token_version`/`session_version`，签发时写入 JWT，校验时比对；改密、拒绝、删除时递增。
3. 缩短访问令牌有效期，配合刷新令牌；或使用服务端会话表/撤销列表。
4. 删除/拒绝/改密时清理 `_user_cache` 并吊销该用户所有会话。
5. WebSocket 握手同样要走完整的用户状态校验。

---

### F-07 高危（配置）：默认/弱口令，且默认账号会自动重新播种

#### 位置

- `config.py:76-82`：默认账号与明文口令：

```python
DEFAULT_USERS = {
    "boss": {"password": "888", ...},
    "admin": {"password": "888", ...},
    "sales": {"password": "123", ...},
    "prod": {"password": "123", ...},
    "inbound": {"password": "123", ...},
}
```

- `database.py:863-868`：启动时 `INSERT IGNORE` 自动创建上述账号，口令直接取 `DEFAULT_USERS`：

```python
for uid, info in DEFAULT_USERS.items():
    conn.execute(text(
        "INSERT IGNORE INTO users (...) VALUES (:u, :p, ...)"
    ), {"u": uid, "p": info["password"], ...})
```

- `.env:12`：`ADMIN_PASSWORD=888`；`.env:16`：`GO_INTERNAL_TOKEN=`（空）。
- 当前启动配置（`.env` 的 `UVICORN_HOST=0.0.0.0` / `run_fullstack.ps1`）将 API 监听在 `0.0.0.0:8000`，局域网可访问。

#### 复现

本地运行实例：

```http
POST http://127.0.0.1:8000/api/v1/auth/login
Content-Type: application/x-www-form-urlencoded

username=admin&password=888
```

结果：`200`，返回 Admin 权限的访问令牌。

通过局域网地址同样成功：

```http
POST http://172.21.8.169:8000/api/v1/auth/login
username=admin&password=888
```

结果：`200`。

`inbound/123` 也可直接登录（本次审计即使用该账号验证低权限场景）。

#### 影响

- 局域网内任何人可用默认口令直接获得 Admin 权限，完全绕过应用权限模型。
- 默认账号由启动逻辑自动播种；即使管理员删除了 `admin`，下次启动仍可能重新创建 `admin/888`。
- 结合 `.env` 中的空 `GO_INTERNAL_TOKEN` 和 Go 服务的认证绕过（F-01），攻击面进一步放大。
- 口令在数据库中为明文存储（`core/auth.py:38` 直接字符串比较），一旦数据库泄露，所有账号口令直接暴露。

#### 修复建议

1. 移除生产环境的默认账号播种逻辑；首次部署通过一次性初始化命令创建管理员，并强制修改初始口令。
2. 删除 `DEFAULT_USERS` 中的弱口令，或仅在显式 `V8_DEV_SEED=1` 时启用。
3. 使用 bcrypt/argon2 等带盐哈希存储口令，禁止明文比较与明文入库。
4. 登录增加速率限制、失败锁定和验证码；避免通过“用户不存在/密码错误”枚举账号。
5. 生产部署前强制检查：默认口令已改、`V8_JWT_SECRET` 已轮换、`GO_INTERNAL_TOKEN` 已设置、3001 不对局域网开放。

---

## 三、已排除项与未确认项

为避免误报，以下内容经过检查后**未列为确认漏洞**：

| 项目 | 结论 |
|---|---|
| SQL 注入 | 抽查 `api/routes`、`crud` 中动态 SQL，值均通过绑定参数传入；未发现可注入点。`users.py` 的动态 `WHERE` 只拼接固定列名。 |
| 工作流审批 IDOR | `crud/workflows.py:1217-1332` 已校验审批人/发起人；转交也校验目标角色。未发现可越权审批。 |
| 发货撤回/退回 | `inventory.py:1841-1853`、`1987-2003` 已用 `409` 强制走逆向审批，不属于可直接利用项。 |
| 订单硬删除 | `planning.py:3594-3601` 已用 `409` 阻止，无法直接删除订单。 |
| 机型字典删除 | `model_dictionary.py:101-108` 已用 `409` 阻止。 |
| MySQL 远程 root | 3306 监听 `0.0.0.0`，但 `root` 账号不允许从非本机主机连接（实测 `1130 Host ... is not allowed`），因此未列为远程数据库接管漏洞；仍建议只监听内网/本机并收紧账号。 |
| FastAPI CORS | `api/main.py:232-238` 使用 `allow_origins=["*"]` 且 `allow_credentials=True`；当前认证使用 Bearer 头而非 Cookie，未复现直接跨站读取，建议改为白名单。 |
| Go WebSocket `/ws` | 未做认证，但广播内容主要为批次/工位 ID；未复现敏感数据批量泄露，建议仍加上鉴权。 |
| `/logs/transactions` | 仅要求登录、未要求 `LOG_VIEW`，低权限用户可读交易日志；是否属于预期需产品确认，暂列为“待确认的读取范围问题”，未计入确认漏洞。 |

---

## 四、修复优先级建议

1. **立即（P0）**
   - 关闭 3001 对局域网/公网的访问，修复 Go 身份校验（F-01）。
   - 修复机台档案 `..` 路径穿越，轮换 `.env` 中所有已暴露密钥（F-02/F-03）。
   - 修改默认管理员口令，禁用/删除默认账号播种（F-07）。

2. **尽快（P1）**
   - 给计划/合同全部写接口补权限（F-04）。
   - 修复合同附件文件名穿越，补 `CONTRACT` 权限（F-05，开启上传前必须完成）。
   - 统一令牌校验，拒绝/删除/改密后立即失效（F-06）。

3. **加固（P2）**
   - 数据库口令改为密钥管理/环境隔离，禁止明文入库。
   - 增加登录限速、失败锁定、口令复杂度。
   - 为所有路由建立权限矩阵和自动化回归测试。
   - 对 `.env`、备份、日志做密钥扫描；确认历史提交中无泄露。

---

## 五、附：关键复现请求汇总（脱敏）

```http
# F-02 读取 .env（inbound 低权限）
GET /api/v1/inventory/machine-archive/%2E%2E/files/.env/download
Authorization: Bearer <inbound>

# F-03 删除项目根目录文件（admin/ARCHIVE）
DELETE /api/v1/inventory/machine-archive/%2E%2E/files/security_delete_probe.txt
Authorization: Bearer <admin>

# F-04 低权限创建订单
POST /api/v1/planning/orders
Authorization: Bearer <inbound>
{"客户名":"SEC-AUDIT-CUSTOMER","需求机型":"FH-300C","需求数量":1}

# F-04 低权限修改合同状态
POST /api/v1/planning/contract/<contract_id>/status
Authorization: Bearer <inbound>
{"status":"生产中"}

# F-01 Go 认证绕过（局域网 3001）
GET http://<host>:3001/api/batches
X-Username: attacker
X-Role: admin

# F-01 或使用明文角色令牌
GET http://<host>:3001/api/batches
Authorization: Bearer attacker:admin
```

> 报告中不包含任何生产口令、JWT 或密钥值；文中的 `admin/888`、`inbound/123` 是代码内置的默认口令，仅用于说明配置问题。复现时请使用沙盘账号与克隆库。
