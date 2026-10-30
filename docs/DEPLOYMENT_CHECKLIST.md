# V8 部署到公司主机的注意事项

> 适用：把当前开发态（`run_fullstack.ps1` 一键起五个进程）迁到公司一台常驻主机，供局域网/内网使用。
> 结论先行：**代码能跑，但不能直接照搬开发启动方式**。下面按"必须改 → 必须配 → 建议做"排序。

---

## 一、上线前必须改（安全硬伤）

### 1. JWT 密钥必须由部署环境提供（已修复硬编码）

`api/routes/auth.py` 现在读取 `V8_JWT_SECRET`（兼容 `JWT_SECRET`），并强制要求长度 ≥ 32；未配置时启动失败，不再回退到源码固定值。

任何拿到源码或反编译产物的人都不应能伪造账号（包括 admin）的 token；Token 有效期仍为 **30 天**，上线时建议同步缩短。

**处理**：在部署环境设置 ≥ 32 位随机 `V8_JWT_SECRET`；上线前让所有旧 token 失效（换密钥即可）。

### 2. 默认账号密码写死

`config.py:77-81`：

```
boss/888   admin/888   sales/123   prod/123   inbound/123   ...
```

首次建库会自动写入。上线后必须**逐个改密码**，并删掉不用的测试账号。

### 3. 内部接口默认不鉴权

`api/routes/planning.py:3274`：

```python
def _assert_internal_token(request):
    config_token = (GO_INTERNAL_TOKEN or "").strip()
    if config_token and provided_token != config_token:   # ← 为空时直接放行
        raise HTTPException(403)
```

`GO_INTERNAL_TOKEN` 默认空 → `/internal/planning/*`（改机台备注、合同取消同步等）**任何能访问 8000 的人都能调**。

**处理**：生产必须设置 `GO_INTERNAL_TOKEN`，并让 Go 服务用同一个值。

### 4. CORS 配置自相矛盾

`api/main.py:220`：

```python
allow_origins=["*"], allow_credentials=True
```

浏览器规范下"通配来源 + 携带凭据"会被拒绝，实际效果是前端带 cookie 的请求可能失败；同时配置过于开放。

**处理**：改成明确域名列表（如 `https://v8.公司内网域名`），或用相对路径同源部署后收紧为同源。

### 5. 没有 HTTPS

JWT 走明文 HTTP，内网抓包即可拿到 30 天有效的 token。

**处理**：nginx 终止 TLS，只对外暴露 443；8000/3001 只对本机或 nginx 开放。

---

## 二、必须配置（否则功能缺失或起不来）

### 6. 两套数据库环境变量，容易配一半

| 服务 | 变量 |
|---|---|
| FastAPI / Python | `MYSQL_HOST`、`MYSQL_PORT`、`MYSQL_USER`、`MYSQL_PASSWORD`、`MYSQL_DB` |
| Go 沙箱 | `DB_DSN` 或 `DB_HOST`/`DB_PORT`/`DB_USER`/`DB_PASSWORD`/`DB_NAME` |

只配一套会出现"前端能开、沙箱报错"或反之。建议在 `.env` 里两套都写全。

### 7. 上传功能默认关闭

`api/upload_guard.py`：`V8_UPLOADS_ENABLED` 默认 `false`，所有上传接口直接 `503 V8 文件上传功能暂时关闭`。

拍照、机台档案图片等功能需要显式设 `V8_UPLOADS_ENABLED=true`。

### 8. OCR 默认关闭

Go 侧 `OCR_ENABLED` 默认 `false`（`OCR_SERVICE_URL` 默认 `http://127.0.0.1:8010/ocr`）。
需要识别功能就打开，并确保 OCR 进程（`server/ocr_service.py`）常驻。

### 9. Go 的允许来源默认只写了本机

`ALLOW_ORIGINS` 默认 `http://127.0.0.1:5173`。生产域名要加进去，否则看板相关接口会被拦。

### 10. 云端开关要按实际情况决定

`.env` 里四个开关（合同桥、快照推送、订单拉取、v8_sync）当前是**全关**（本地测试状态）。
上线要同步云端就必须打开，并保证：

- `WECHAT_CLOUD_API_BASE` 有值（**当前是空的**）
- `V8_SYNC_SECRET` 与云端一致（否则 403「V8桥接签名校验失败」）
- 网络能出公网 443

如果暂时不同步，保持关闭即可，但要接受"云端小程序订单进不来、微信端库存不更新"。

---

## 三、部署形态：不能直接用开发脚本

### 11. 前端必须构建，不能用 vite dev

`run_fullstack.ps1` 起的是 vite 开发服务器（HMR、无压缩、单线程），不能作为生产服务。

```powershell
cd frontend;        npm ci; npm run build     # 产物 frontend/dist，由 FastAPI 直接托管
cd frontend-mobile; npm ci; npm run build     # 产物 frontend-mobile/dist
```

注意：`frontend/dist` 是提交进仓库的旧产物，**必须重新构建**再用。

### 12. 移动端没有现成的托管方式

FastAPI 只托管 `frontend/dist`（PC 端）。移动端：

- 没有 `frontend-mobile/dist`（当前未构建）
- 代码里 `baseURL: '/api/v1'` 是**相对路径**，必须同源或反代

**处理**：nginx 单独一个 server（或 location）指向 `frontend-mobile/dist`，并把 `/api/` 反代到 `http://127.0.0.1:8000`。

### 13. 进程守护

现在只有 `.bat` 和 `run_fullstack.ps1`，没有服务化：进程崩了不会自动拉起，主机重启也不会自启。

**建议**：用 NSSM 把 4 个进程注册成 Windows 服务（FastAPI、Go、OCR、nginx），或至少用任务计划程序 + 开机启动。

### 14. FastAPI 单进程

`uvicorn api.main:app` 默认单 worker。报表/Excel 类接口是 pandas CPU 密集，会阻塞其他请求。

可以加 `--workers N`，但要先确认：进程内缓存（`@lru_cache` 的 engine、planning 缓存）和多进程之间不共享，**Go 在无 Redis 时用进程内锁**——多实例/多 worker 下锁会失效。

**结论**：先单实例跑稳；要扩多实例，先把 Redis 上起来。

---

## 四、数据与备份

### 15. 没有版本化迁移

建表靠启动时的 `ensure_*_tables()` / `init_mysql_tables()` 隐式执行 DDL，升级只能"往前"，没有回滚脚本。

**上线前必做**：`mysqldump` 全库备份，并保留至少 7 天。

### 16. 排序规则不统一

- 流程表（`workflow_*`）：`utf8mb4_0900_ai_ci`
- 业务表（`finished_goods_data`、`sales_orders` 等）：`utf8mb4_general_ci`

代码里已经手写 `COLLATE utf8mb4_general_ci` 处理，但**运维写临时报表 SQL 时跨表 JOIN 会报 1267**，需要知道这一点。

### 17. 备份与恢复演练

目前只有 `data_repair_backups/` 这种临时目录，没有定期备份。建议：

- 每日 `mysqldump --single-transaction` 到独立磁盘/NAS
- 保留 30 天，每月抽一次恢复演练

---

## 五、运行时稳定性（上线后会暴露的问题）

### 18. 没有后台调度

流程的租约回收、outbox 重试、待派生超时提醒**全靠人工**。生产环境建议加计划任务，定期调管理接口（admin 权限）：

- `POST /api/v1/workflows/instances/close-stale`（关闭审批后长期未执行的实例）
- `POST /api/v1/workflows/outbox/claim` 等（消费/清理事件）

### 19. `workflow_outbox_events` 无消费者

每次流程执行完成都会写一条事件，但没有进程消费，会一直堆积（当前 42 条）。要么补消费者，要么定期归档/清理。

### 20. 日志无轮转

启动脚本把 stdout/stderr 重定向到固定文件，没有按天切分。之前云端 403 刷屏，13 分钟就 156KB。

**建议**：日志按天切分 + 保留 30 天，或用 nginx/服务管理器接管日志。

### 21. 磁盘与缓存目录

- Go 编译缓存 `server/.gocache` 很大，生产机建议**只部署编译好的 `go.exe`**，不要在生产机上现场编译
- 上传文件、导出文件所在目录要有足够空间和备份策略

---

## 六、网络与端口

| 端口 | 服务 | 生产建议 |
|---|---|---|
| 443 | nginx（HTTPS） | **对外唯一入口** |
| 8000 | FastAPI | 仅 127.0.0.1 或 nginx 可访问 |
| 3001 | Go 沙箱 | 仅 127.0.0.1 |
| 8010 | OCR | 仅 127.0.0.1（本来就是这样） |
| 3000 / 5174 | vite dev | **生产不要开**，用构建产物 |

防火墙只需放行 443；3000/5174/8000/3001/8010 都不应对局域网开放。
（开发阶段加的 4 条 `V8 Fullstack` 规则，上线后应删除或禁用。）

---

## 七、上线检查清单（可直接照着做）

**准备**
- [ ] 安装 MySQL 8（字符集 `utf8mb4`）、Python 3.13、Node 20+（仅构建用）、nginx
- [ ] 建库建账号，确认 Python 与 Go 两套 DB 变量都指向同一实例
- [ ] 准备 `.env`（不要放进共享目录）：`MYSQL_*`、`DB_*`、`V8_JWT_SECRET`、`GO_INTERNAL_TOKEN`、`V8_UPLOADS_ENABLED`、`OCR_ENABLED`、云端开关
- [ ] `pip install -r requirements.txt`（独立虚拟环境）

**构建**
- [ ] `frontend` 与 `frontend-mobile` 都执行 `npm ci && npm run build`
- [ ] 部署编译好的 `server/go.exe`（不要在生产机编译）

**安全（最容易漏）**
- [ ] 替换 JWT 密钥并重启（让旧 token 失效）
- [ ] 修改所有默认账号密码，删除测试账号
- [ ] 设置 `GO_INTERNAL_TOKEN`
- [ ] CORS 收紧到实际域名
- [ ] nginx 配 HTTPS，只暴露 443
- [ ] 删除开发期的 4 条防火墙放行规则

**运行**
- [ ] 4 个进程注册为服务并设置开机自启
- [ ] 移动端 dist 由 nginx 托管，`/api` 反代到 8000
- [ ] 日志按天切分
- [ ] 每日数据库备份 + 恢复演练

**上线后首日**
- [ ] 用真实账号走一遍：登录 → 合同 → 下单 → 配货 → 发货 → 退回审批
- [ ] 确认云端同步是否符合预期（关闭 or 正常拉取）
- [ ] 观察 24 小时日志有无异常堆积

---

## 八、一句话总结

**代码层面能上，但有 5 个安全项必须先处理**（JWT 密钥、默认密码、内部接口 token、CORS、HTTPS）；
**运维层面必须补 3 件事**（进程守护、日志轮转、数据库备份）；
**移动端要单独构建和托管**，不能沿用 vite 开发服务器。
