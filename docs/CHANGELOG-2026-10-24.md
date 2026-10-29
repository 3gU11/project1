# 2026-10-24 更新说明

## Go 服务启动配置修复

- 启动脚本现在也加载 `server/.env`，确保 Go 后端能够读取所需的 `DB_*` 配置。
- 使用项目当前 Go 源码构建并启动服务，`GET /api/health` 返回 HTTP 200。

## 配货接口空值序列化修复

- 修复订单配货接口把 Pandas `NaN` / `NaT` 作为 JSON 返回，导致 Starlette 序列化失败并返回 HTTP 500 的问题。
- 对接口返回的 DataFrame 先转为 object 类型，再把所有缺失值转成 JSON `null`。
- 增加回归测试，覆盖数值空值、日期空值和库存扩展字段缺失。

## 验证

- 配货相关 Python 测试：10 项通过。
- `git diff --check`：通过。
