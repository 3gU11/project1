# V8 本地启动与局域网访问

> 适用环境：Windows，项目根目录 `F:\work\V8\project1`
> 当前状态：**云端连接已全部关闭，只做本地测试**（见第五节）

---

## 一、一句话启动

在**你自己的 PowerShell 窗口**里执行：

```powershell
cd F:\work\V8\project1
powershell -NoProfile -ExecutionPolicy Bypass -File .\run_fullstack.ps1 -PythonExe D:\python\python.exe
```

启动完成后脚本会打印本机地址、局域网地址和防火墙自检结果。**这个窗口不要关**，关掉服务就停了。

---

## 二、启动了什么

| 服务 | 端口 | 说明 |
|---|---|---|
| PC 前端（vite） | 3000 | `frontend/` |
| 移动端（vite） | 5174 | `frontend-mobile/` |
| FastAPI | 8000 | `api/`，接口文档 `/docs` |
| Go 沙箱 | 3001 | `server/` |
| OCR | 8010 | 只绑 `127.0.0.1`，内部服务，不对局域网开放 |

启动脚本会自动完成：检查依赖（`node_modules` 缺失或损坏时重装并重试一次）→ 编译 Go → 依次起 OCR / Go / FastAPI / PC 端 / 移动端 → 逐个健康检查。

---

## 三、停止

```powershell
cd F:\work\V8\project1
powershell -NoProfile -ExecutionPolicy Bypass -File .\stop_fullstack.ps1
```

停止脚本会先按 `.fullstack.pids.json` 记录的 PID 停，再按端口兜底清理，所以即使 PID 文件过期也能停干净。

---

## 四、局域网访问

### 4.1 地址

本机当前 IP：**172.21.8.169**（WLAN）。手机/同事电脑用这个地址：

| 用途 | 地址 |
|---|---|
| PC 管理端 | http://172.21.8.169:3000 |
| 移动端（手机扫码/访问） | http://172.21.8.169:5174 |
| API 文档 | http://172.21.8.169:8000/docs |

IP 变化时以启动脚本打印的 `LAN access` 段为准。

### 4.2 为什么需要防火墙规则

服务本身监听 `0.0.0.0`，能不能被局域网访问只取决于 **Windows 防火墙入站规则**。本机网络类型是「公用(Public)」，默认拦截入站。

一次性放行（需要管理员，会弹 UAC）：

```powershell
cd F:\work\V8\project1
powershell -NoProfile -ExecutionPolicy Bypass -File .\enable_lan_access.ps1
```

脚本是幂等的，重复执行只更新不重复建。会添加 4 条 TCP 入站规则（Private + Public）：

```
V8 Fullstack 3000 (V8 Web Frontend (vite))
V8 Fullstack 5174 (V8 Mobile Frontend (vite))
V8 Fullstack 8000 (V8 FastAPI)
V8 Fullstack 3001 (V8 Go Backend)
```

规则持久保存在系统里，**只需执行一次**。之后每次启动，`run_fullstack.ps1` 末尾会自检并打印：

```
  Firewall  : OK (inbound allow rules present)
```

如果显示 `MISSING rules for port(s): ...`，说明规则被删了或被组策略覆盖，重新跑一次 `enable_lan_access.ps1`。

### 4.3 验证

在本机执行（确认监听与代理链路）：

```powershell
curl.exe -s -o NUL -w "%{http_code}`n" http://172.21.8.169:3000/
curl.exe -s -o NUL -w "%{http_code}`n" http://172.21.8.169:5174/
curl.exe -s -o NUL -w "%{http_code}`n" http://172.21.8.169:8000/health
```

期望都是 `200`。

前端代理链路（期望 `401`，表示请求确实穿透到了 FastAPI）：

```powershell
curl.exe -s -o NUL -w "%{http_code}`n" http://172.21.8.169:3000/api/v1/auth/me
```

### 4.4 手机连不上时按顺序排查

| 现象 | 原因 | 处理 |
|---|---|---|
| 手机完全打不开 | 不在同一网段 | 手机连同一个 Wi-Fi，确认 IP 前三位一致 |
| 电脑能开、手机不能 | 防火墙缺规则 | 跑 `enable_lan_access.ps1`，或看启动脚本的 Firewall 自检 |
| 规则都在还是不通 | 路由器开了 **AP 隔离/客户端隔离** | 办公网常见，需网管放开；可先用手机热点验证 |
| 手机能开但登录失败 | 用了 `127.0.0.1` 或 `localhost` | 必须用 `172.21.8.169` |
| 页面能开但接口 404/超时 | 前端代理目标不对 | 确认 8000 在跑；重启 vite |

> OCR（8010）只绑 `127.0.0.1`，是给 Go 后端调用的内部服务，**不需要也不应该**对局域网开放。

---

## 五、当前本地测试配置（云端已关）

`.env`（未纳入版本库，只影响本机）已关闭全部自动外发通道：

| 开关 | 值 | 关闭的通道 |
|---|---|---|
| `CONTRACT_INTEGRATION_ENABLED` | `false` | 合同云桥 |
| `V8_DEMO_MODE` | `1` | 微信库存快照推送 |
| `ENABLE_CLOUD_PULL` | `false` | 经销商订单拉取 |
| `V8_SYNC_ENABLED` | `false` | v8_sync 快照/事件桥 |

表现：启动日志出现 `V8 sync bridge startup result=demo_disabled`，`api-launcher.err.log` 不再刷 403。

**副作用**：云端小程序端的经销商订单不会同步进来，微信端库存快照也不会更新。恢复云端把这四项改回（合同 `true` / 删除 `V8_DEMO_MODE` / pull `true` / sync `true`）后重启 API 即可。

---

## 六、常见启动失败

| 报错 | 原因 | 处理 |
|---|---|---|
| `ENOTEMPTY` / `ENOENT`（npm） | `node_modules` 残留半删除目录 | 脚本已内置自动清理重试；仍失败就手动删 `node_modules` 再启动 |
| `Fail: ... dependency installation failed` | 同上，且自动重试也失败 | 检查网络/npm 源，删目录后重试 |
| `Port ... already in use` | 上次没停干净 | 先跑 `stop_fullstack.ps1` |
| `Go build failed` | Go 缓存或代码问题 | 看 `server/go-launcher.err.log` |
| FastAPI 起不来 | Python 依赖或数据库连接 | 看 `api-launcher.err.log`，确认 MySQL 可连 |
| 前端页面空白 | vite 依赖未装好 | 看 `frontend/web-launcher.err.log` |

日志位置（脚本末尾也会打印）：

```
server/go-launcher.out.log        server/go-launcher.err.log
server/ocr-launcher.out.log       server/ocr-launcher.err.log
api-launcher.out.log              api-launcher.err.log
frontend/web-launcher.out.log     frontend/web-launcher.err.log
frontend-mobile/mobile-launcher.out.log
frontend-mobile/mobile-launcher.err.log
```

---

## 七、注意

- **不要从 IDE 的 AI 会话里启动**：会话注入的 `NODE_OPTIONS` 会拦截 vite 清理缓存，导致前端假失败；会话结束时子进程还会被回收。
- 含中文的 `.ps1` 必须存为 **UTF-8 with BOM**，否则 PowerShell 5.1 会按 GBK 解析报语法错误。`run_fullstack.ps1` 目前是纯 ASCII，不要随意加中文注释。
