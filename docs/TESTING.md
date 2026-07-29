# 测试与发布检查

## Python 测试

```powershell
python -m pytest tests -q
```

重点覆盖库存布局、订单库存释放、入库完工通知、追溯、WebSocket、维修系统签名和幂等性。涉及 MySQL 的测试应使用隔离数据库，不要连接生产库。

## Go 测试

```powershell
cd server
go test ./...
cd ..
```

## 前端检查

```powershell
cd frontend
npm run build
npm run test:unit -- --run
cd ..

cd frontend-mobile
npm run build
cd ..
```

端到端测试依赖已启动的前后端，按需执行 `npm run test:e2e:run`。不要把 `test-results/`、浏览器 profile 或构建产物提交到仓库。

## 发布前清单

- [ ] `git diff --check` 无空白错误。
- [ ] 依赖锁文件与构建结果一致。
- [ ] `/health` 和 `/docs` 可访问。
- [ ] 登录、库存查询、排产、配货、发货和报表各走通一条主流程。
- [ ] MySQL 和归档目录已有可恢复备份。
- [ ] 生产 `.env`、内部 token 和云端 API key 未进入提交。
- [ ] WebSocket、Nginx Upgrade 和跨域策略已验证。
- [ ] Outbox 无持续增长或重复失败事件。
