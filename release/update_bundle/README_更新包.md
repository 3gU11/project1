## 目标

在 Windows 服务机上本地执行一键更新：备份 -> 停服务 -> 部署后端/前端 -> 数据库升级（inplace/newdb）-> 启动 -> 健康检查。

## 目录结构

- update.bat：双击入口
- update.ps1：更新主脚本
- rollback.ps1：回滚脚本
- package\
  - backend\：后端代码包（由 build_update_package.ps1 生成）
  - frontend-dist\：前端 dist（由 build_update_package.ps1 生成）
- scripts\
  - db_migrate_inplace.py：原库就地升级（幂等）
  - db_migrate_newdb.py：新库迁移（创建新库并拷贝数据）

## 服务机准备

- Python 可用（建议与旧系统一致）
- MySQL 客户端工具可用（建议 PATH 中有 mysqldump、mysql）
- 旧系统目录存在，并包含 .env

## 使用方式（服务机）

1. 将整个 update_bundle 目录拷贝到服务机任意位置（例如 D:\deploy\update_bundle）。
2. 确保 package\backend 与 package\frontend-dist 已包含新版本内容。
3. 双击 update.bat，或在 PowerShell 执行：

   powershell -ExecutionPolicy Bypass -File .\update.ps1 -InstallDir "D:\antigraveity_pj\V7ex" -DbMode inplace

可选参数示例：

- 新库迁移切换：

  powershell -ExecutionPolicy Bypass -File .\update.ps1 -InstallDir "D:\antigraveity_pj\V7ex" -DbMode newdb

- 指定服务名（用 Windows 服务方式停启）：

  powershell -ExecutionPolicy Bypass -File .\update.ps1 -InstallDir "D:\antigraveity_pj\V7ex" -ServiceName "V7exApi" -DbMode inplace

## 回滚（服务机）

update.ps1 会在备份目录输出本次备份路径。回滚示例：

powershell -ExecutionPolicy Bypass -File .\rollback.ps1 -InstallDir "D:\antigraveity_pj\V7ex" -BackupDir "D:\backup\V7ex_updates\2026-04-13_120000"

## 生成更新包（开发机）

在项目目录 V7ex\release 下执行：

powershell -ExecutionPolicy Bypass -File .\build_update_package.ps1

执行完成后会生成一个 zip，拷贝到服务机解压后双击 update.bat 即可。
