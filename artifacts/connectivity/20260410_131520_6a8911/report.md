# 模块连通性测试报告

- Run ID: `20260410_131520_6a8911`
- Base URL: `http://127.0.0.1:8000`
- Time: `2026-04-10 13:15:21`
- 结论: **闭环完整**
- 阻断数: **0**
- 缺陷数: **0**

## 执行明细

| Step | Expected | Status | Elapsed(ms) | Result |
|---|---|---:|---:|---|
| unauthorized_guard_inventory | 401 | 401 | 109 | PASS |
| login_admin | 200+token | 200 | 3 | PASS |
| auto_generate_invalid_qty | 422 | 422 | 2 | PASS |
| auto_generate_one | 200 | 200 | 55 | PASS |
| import_staging_list | 200+find_serial | 200 | 22 | PASS |
| import_confirm_empty | 422 | 422 | 23 | PASS |
| import_confirm_valid | 200+success_count>=1 | 200 | 322 | PASS |
| verify_inventory_pending | state=待入库 | 200 | 16 | PASS |
| inbound_to_slot | 200+ok=true | 200 | 69 | PASS |
| verify_inventory_in_stock | state contains 库存中 | 200 | 19 | PASS |
| create_order | 200+order_id | 200 | 141 | PASS |
| allocate_empty | 422 | 422 | 2 | PASS |
| allocate_valid | 200 | 200 | 326 | PASS |
| verify_inventory_pending_shipping | state=待发货 and order match | 200 | 16 | PASS |
| shipping_pending_contains_serial | contains serial | 200 | 51 | PASS |
| shipping_confirm | 200 | 200 | 346 | PASS |
| verify_inventory_shipped | state=已出库 | 200 | 22 | PASS |
| logs_contains_serial | contains serial log | 200 | 24 | PASS |
| sales_forbidden_users_list | 403 | 403 | 1 | PASS |

## 缺陷清单

- 无

## 关键输入输出

### unauthorized_guard_inventory
- Request: `GET /api/v1/inventory/`
- Input: `null`
- Output: `{"detail": "Not authenticated"}`
- Elapsed: `109 ms`

### login_admin
- Request: `POST /api/v1/auth/login`
- Input: `{"username": "admin", "password": "888"}`
- Output: `{"access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJleHAiOjE3NzgzOTAxMjAsInN1YiI6ImFkbWluIiwibmFtZSI6Ilx1N2NmYlx1N2VkZlx1N2JhMVx1NzQwNlx1NTQ1OCIsInJvbGUiOiJBZG1pbiJ9.03qRuQUALysnVq6UO5a1Nirf6u_tRHAGh50e3XZ7O6I", "token_type": "bearer", "user": {"username": "admin", "role": "Admin", "name": "系统管理员"}}`
- Elapsed: `3 ms`

### auto_generate_invalid_qty
- Request: `POST /api/v1/inventory/import-staging/auto-generate`
- Input: `{"batch": "E2E26045B02", "model": "FR-400G", "qty": 0, "expected_inbound_date": "2026-04-10", "machine_note": ""}`
- Output: `{"detail": [{"type": "greater_than", "loc": ["body", "qty"], "msg": "Input should be greater than 0", "input": 0, "ctx": {"gt": 0}}]}`
- Elapsed: `2 ms`

### auto_generate_one
- Request: `POST /api/v1/inventory/import-staging/auto-generate`
- Input: `{"batch": "E2E26045B02", "model": "FR-400G", "qty": 1, "expected_inbound_date": "2026-04-10", "machine_note": "E2E-20260410_131520_6a8911"}`
- Output: `{"message": "已生成 1 条数据 (96-E2E26045B02-1 ~ 96-E2E26045B02-1)"}`
- Elapsed: `55 ms`

### import_staging_list
- Request: `GET /api/v1/inventory/import-staging`
- Input: `null`
- Output: `{"data": [{"批次号": "E2E26045B02", "机型": "FR-400G", "流水号": "96-E2E26045B02-1", "预计入库时间": "2026-04-10T00:00:00", "机台备注/配置": "E2E-20260410_131520_6a8911", "f4": null, "状态": "待入库"}, {"批次号": "202604第4批", "机型": "FR-600AUTO", "流水号": "96-04-99", "预计入库时间": "NaT", "机台备注/配置": "", "f4": null, "状态": "待入库"}, {"批次号": "202604第4批", "机型": "FR-600AUTO", "流水号": "96-04-98", "预计入库时间": "NaT", "机台备注/配置": "", "f4": null, "状态": "待入库"}, {"批次号": "202604第4批", "机型": "FR-600AUTO", "流水号": "96-04-97", "预计入库时间": "NaT", "机台备注/配置": "", "f4": null, "状态": "待入库"}, {"批次号": "202604第4批", "机型": "FR-600AUTO", "流水号": "96-04-96", "预计入库时间": "NaT", "机台备注/配置": "", "f4": null, "状态": "待入库"}, {"批次号": "202604第4批", "机型": "FR-600AUTO", "流水号": "96`
- Elapsed: `22 ms`

### import_confirm_empty
- Request: `POST /api/v1/inventory/import-staging/import-confirm`
- Input: `{"selected_track_nos": [], "expected_inbound_date": "2026-04-10"}`
- Output: `{"detail": "请先勾选至少 1 条数据"}`
- Elapsed: `23 ms`

### import_confirm_valid
- Request: `POST /api/v1/inventory/import-staging/import-confirm`
- Input: `{"selected_track_nos": ["96-E2E26045B02-1"], "expected_inbound_date": "2026-04-10"}`
- Output: `{"success": [{"trackNo": "96-E2E26045B02-1"}], "failed": [], "success_count": 1, "failed_count": 0}`
- Elapsed: `322 ms`

### verify_inventory_pending
- Request: `GET /api/v1/inventory/`
- Input: `null`
- Output: `{"data": [{"批次号": "E2E26045B02", "机型": "FR-400G", "流水号": "96-E2E26045B02-1", "状态": "待入库", "更新时间": "2026-04-10T13:15:00", "占用订单号": null, "客户": "", "代理商": "", "订单备注": "", "预计入库时间": "2026-04-10T00:00:00", "机台备注/配置": "E2E-20260410_131520_6a8911", "Location_Code": ""}, {"批次号": "02-09", "机型": "FR-600XS(PRO)", "流水号": "96-02-252", "状态": "待发货", "更新时间": "2026-04-10T13:06:57", "占用订单号": "SO-20260409-AB0C", "客户": "优德路（苏州迅科模具）", "代理商": "王晓枫", "订单备注": "合同HT202603196699自动生成；", "预计入库时间": "2026-03-21T00:00:00", "机台备注/配置": "", "Location_Code": ""}, {"批次号": "", "机型": "FR-400AUTO", "流水号": "93-12-221", "状态": "待发货", "更新时间": "2026-04-10T10:08:10", "占用订单号": "SO-20260408-EFEA", "客户": "宁海锐盛模具厂宁海西店", "代理商": "陈利春", "订单备`
- Elapsed: `16 ms`

### inbound_to_slot
- Request: `POST /api/v1/inventory/inbound-to-slot`
- Input: `{"serial_no": "96-E2E26045B02-1", "slot_code": "E2E-A01"}`
- Output: `{"ok": true, "code": "OK", "message": "入库成功", "inbound_time": "2026-04-10 13:15:20", "slot_code": "E2E-A01"}`
- Elapsed: `69 ms`

### verify_inventory_in_stock
- Request: `GET /api/v1/inventory/`
- Input: `null`
- Output: `{"data": [{"批次号": "E2E26045B02", "机型": "FR-400G", "流水号": "96-E2E26045B02-1", "状态": "库存中（E2E-A01）", "更新时间": "2026-04-10T13:15:20", "占用订单号": null, "客户": "", "代理商": "", "订单备注": "", "预计入库时间": "2026-04-10T00:00:00", "机台备注/配置": "E2E-20260410_131520_6a8911", "Location_Code": "E2E-A01"}, {"批次号": "02-09", "机型": "FR-600XS(PRO)", "流水号": "96-02-252", "状态": "待发货", "更新时间": "2026-04-10T13:06:57", "占用订单号": "SO-20260409-AB0C", "客户": "优德路（苏州迅科模具）", "代理商": "王晓枫", "订单备注": "合同HT202603196699自动生成；", "预计入库时间": "2026-03-21T00:00:00", "机台备注/配置": "", "Location_Code": ""}, {"批次号": "", "机型": "FR-400AUTO", "流水号": "93-12-221", "状态": "待发货", "更新时间": "2026-04-10T10:08:10", "占用订单号": "SO-20260408-EFEA", "客户": "宁海锐盛模具厂宁海西店", "代`
- Elapsed: `19 ms`

### create_order
- Request: `POST /api/v1/planning/orders`
- Input: `{"客户名": "E2E客户", "代理商": "E2E代理", "需求机型": "FR-400Gx1", "需求数量": 1, "备注": "E2E闭环-20260410_131520_6a8911", "包装选项": "", "发货时间": "2026-04-10"}`
- Output: `{"message": "订单创建成功", "order_id": "SO-20260410-6706"}`
- Elapsed: `141 ms`

### allocate_empty
- Request: `POST /api/v1/planning/orders/SO-20260410-6706/allocate`
- Input: `{"selected_serial_nos": []}`
- Output: `{"detail": "请先选择要配货的机台"}`
- Elapsed: `2 ms`

### allocate_valid
- Request: `POST /api/v1/planning/orders/SO-20260410-6706/allocate`
- Input: `{"selected_serial_nos": ["96-E2E26045B02-1"]}`
- Output: `{"message": "配货成功，已锁定 1 台机台"}`
- Elapsed: `326 ms`

### verify_inventory_pending_shipping
- Request: `GET /api/v1/inventory/`
- Input: `null`
- Output: `{"data": [{"批次号": "E2E26045B02", "机型": "FR-400G", "流水号": "96-E2E26045B02-1", "状态": "待发货", "更新时间": "2026-04-10T13:15:21", "占用订单号": "SO-20260410-6706", "客户": "E2E客户", "代理商": "E2E代理", "订单备注": "E2E闭环-20260410_131520_6a8911", "预计入库时间": "2026-04-10T00:00:00", "机台备注/配置": "E2E-20260410_131520_6a8911", "Location_Code": "E2E-A01"}, {"批次号": "02-09", "机型": "FR-600XS(PRO)", "流水号": "96-02-252", "状态": "待发货", "更新时间": "2026-04-10T13:06:57", "占用订单号": "SO-20260409-AB0C", "客户": "优德路（苏州迅科模具）", "代理商": "王晓枫", "订单备注": "合同HT202603196699自动生成；", "预计入库时间": "2026-03-21T00:00:00", "机台备注/配置": "", "Location_Code": ""}, {"批次号": "", "机型": "FR-400AUTO", "流水号": "93-12-221", "状态": "待发货", "更新时间": "2026-04-10T10:08:10", "占用订单号": `
- Elapsed: `16 ms`

### shipping_pending_contains_serial
- Request: `GET /api/v1/inventory/shipping/pending`
- Input: `null`
- Output: `{"data": [{"批次号": "", "机型": "FR-400AUTO", "流水号": "93-12-221", "状态": "待发货", "更新时间": "2026-04-10T10:08:10", "占用订单号": "SO-20260408-EFEA", "客户": "宁海锐盛模具厂宁海西店", "代理商": "陈利春", "订单备注": "合同HT202602058339自动生成；", "预计入库时间": "NaT", "机台备注/配置": "", "Location_Code": "", "发货时间": "2026-01-31"}, {"批次号": "", "机型": "FR-400XS(PRO)", "流水号": "95-09-126", "状态": "待发货", "更新时间": "2026-04-08T09:33:05", "占用订单号": "SO-20260120-E84E", "客户": "东莞市南城蛤地草塘路7号工业区（宏轩机械）", "代理商": "卢振彪", "订单备注": "", "预计入库时间": "NaT", "机台备注/配置": "", "Location_Code": "", "发货时间": ""}, {"批次号": "", "机型": "FR-500XS(PRO)", "流水号": "95-09-139", "状态": "待发货", "更新时间": "2026-04-08T10:02:00", "占用订单号": "SO-20260120-AF51", "客户": "余姚模具城（余姚市天擎模具厂）", "代理商": "陈利春", "订单`
- Elapsed: `51 ms`

### shipping_confirm
- Request: `POST /api/v1/inventory/shipping/confirm`
- Input: `{"serial_nos": ["96-E2E26045B02-1"]}`
- Output: `{"message": "发货完成，共 1 台"}`
- Elapsed: `346 ms`

### verify_inventory_shipped
- Request: `GET /api/v1/inventory/`
- Input: `null`
- Output: `{"data": [{"批次号": "E2E26045B02", "机型": "FR-400G", "流水号": "96-E2E26045B02-1", "状态": "已出库", "更新时间": "2026-04-10T13:15:00", "占用订单号": "SO-20260410-6706", "客户": "E2E客户", "代理商": "E2E代理", "订单备注": "E2E闭环-20260410_131520_6a8911", "预计入库时间": "2026-04-10T00:00:00", "机台备注/配置": "E2E-20260410_131520_6a8911", "Location_Code": "E2E-A01"}, {"批次号": "02-09", "机型": "FR-600XS(PRO)", "流水号": "96-02-252", "状态": "待发货", "更新时间": "2026-04-10T13:06:57", "占用订单号": "SO-20260409-AB0C", "客户": "优德路（苏州迅科模具）", "代理商": "王晓枫", "订单备注": "合同HT202603196699自动生成；", "预计入库时间": "2026-03-21T00:00:00", "机台备注/配置": "", "Location_Code": ""}, {"批次号": "", "机型": "FR-400AUTO", "流水号": "93-12-221", "状态": "待发货", "更新时间": "2026-04-10T10:08:10", "占用订单号": `
- Elapsed: `22 ms`

### logs_contains_serial
- Request: `GET /api/v1/logs/transactions?limit=1000`
- Input: `null`
- Output: `{"data": [{"时间": "2026-04-10T13:15:22", "操作类型": "正式发货", "流水号": "96-E2E26045B02-1", "操作员": "系统管理员"}, {"时间": "2026-04-10T13:15:21", "操作类型": "配货锁定-SO-20260410-6706", "流水号": "96-E2E26045B02-1", "操作员": "系统管理员"}, {"时间": "2026-04-10T13:06:57", "操作类型": "配货锁定-SO-20260409-AB0C", "流水号": "96-02-252", "操作员": "系统管理员"}, {"时间": "2026-04-10T10:08:10", "操作类型": "配货锁定-SO-20260408-EFEA", "流水号": "93-12-221", "操作员": "系统管理员"}, {"时间": "2026-04-09T15:05:49", "操作类型": "正式发货", "流水号": "96-01-585", "操作员": "系统管理员"}, {"时间": "2026-04-09T15:04:00", "操作类型": "正式发货", "流水号": "96-03-369", "操作员": "系统管理员"}, {"时间": "2026-04-09T15:03:37", "操作类型": "配货锁定-SO-20260409-6FDA", "流水号": "96-01-585", "操作员": "系统管理员"}, {"时间": "2026-04-09T15:03:37`
- Elapsed: `24 ms`

### sales_forbidden_users_list
- Request: `GET /api/v1/users/`
- Input: `null`
- Output: `{"detail": "没有操作权限"}`
- Elapsed: `1 ms`
