# 项目文档

本目录是 V7STD1.0 智能生产排产与成品库存管理系统的维护文档，按“先运行、再理解、后运维”的顺序组织。

## 文档导航

| 文档 | 用途 |
| --- | --- |
| [项目总览](PROJECT_OVERVIEW.md) | 产品边界、模块和业务闭环 |
| [系统架构](ARCHITECTURE.md) | Python、Go、PC、移动端和 MySQL 的关系 |
| [开发与启动](DEVELOPMENT.md) | 安装、环境变量和启动命令 |
| [部署指南](DEPLOYMENT.md) | Windows、Docker 和反向代理部署 |
| [接口目录](API.md) | 路由分组、鉴权和联调入口 |
| [业务操作手册](OPERATIONS.md) | 订单、排产、库存、发货和报表 |
| [数据与备份](DATA_AND_BACKUP.md) | 数据库、文件归档、迁移和恢复 |
| [测试与发布](TESTING.md) | 测试、构建和发布检查 |
| [故障排查](TROUBLESHOOTING.md) | 启动、连接、同步和导出问题 |
| [安全基线](SECURITY.md) | 密钥、权限、网络和日志安全 |

## 推荐阅读路径

1. 新开发者：`PROJECT_OVERVIEW.md` -> `ARCHITECTURE.md` -> `DEVELOPMENT.md`。
2. 部署人员：`DEVELOPMENT.md` -> `DEPLOYMENT.md` -> `DATA_AND_BACKUP.md`。
3. 业务用户：`PROJECT_OVERVIEW.md` -> `OPERATIONS.md`。
4. 发布前：`TESTING.md` -> `SECURITY.md`。

文档中的命令默认在项目根目录执行：`F:\V8\project1`。Linux 或容器环境请替换为实际路径。
