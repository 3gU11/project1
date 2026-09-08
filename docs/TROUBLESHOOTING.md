# 故障排查

## FastAPI 无法启动

执行 `python -m uvicorn api.main:app --host 0.0.0.0 --port 8000` 查看首个异常。常见原因是 Python 依赖未安装、MySQL 不可达、`.env` 配置错误或端口被占用。检查 `python -c "import fastapi, sqlalchemy"` 和 `/health`。

## Go 沙盘或照片接口失败

确认 Go 服务监听 3001，`GO_SANDBOX_URL`/`VITE_PHOTO_API_TARGET` 与实际地址一致，并检查 Python 和 Go 的 `GO_INTERNAL_TOKEN` 完全相同。生产环境还要检查网关是否转发相关路径和 WebSocket。

## MySQL 连接失败

核对主机、端口、用户、密码和数据库名；确认账号有 schema 迁移和业务表所需权限。不要使用 root 作为长期生产账号。

## 登录失败或权限不足

确认用户存在、角色已分配且 token 未过期。权限错误通常是角色缺少权限，不要删除鉴权依赖解决。

## 云端同步积压

查看同步状态和 `cloud_sync_outbox` 错误信息，确认 `WECHAT_CLOUD_API_BASE`、`V7_API_KEY` 和网络连通性。先修复根因，再执行重试；状态冲突需人工核对云端状态。

## 报表为空或与库存不一致

核对日期时区、过滤条件和统计口径。入库报表统计历史事件，库存查询统计当前状态；必要时检查 `inbound_history` 和审计日志。

## 发货或配货冲突

刷新订单和库存详情，确认机台未被锁定、订单状态仍允许操作、数量没有超配。禁止重复点击或直接改数据库。

## 文件上传/预览失败

检查归档目录权限、文件大小、磁盘空间和文件名。缩略图损坏时可清理缩略图缓存后重新生成，但不要删除原始档案。
