# 模块连通性测试报告

- Run ID: `20260409_113145_489481`
- Base URL: `http://127.0.0.1:8000`
- Time: `2026-04-09 11:31:47`
- 结论: **闭环完整**
- 阻断数: **0**
- 缺陷数: **0**

## 执行明细

| Step | Expected | Status | Elapsed(ms) | Result |
|---|---|---:|---:|---|
| unauthorized_guard_inventory | 401 | 401 | 128 | PASS |
| login_admin | 200+token | 200 | 69 | PASS |
| auto_generate_invalid_qty | 422 | 422 | 24 | PASS |
| auto_generate_one | 200 | 200 | 69 | PASS |
| import_staging_list | 200+find_serial | 200 | 26 | PASS |
| import_confirm_empty | 422 | 422 | 27 | PASS |
| import_confirm_valid | 200+success_count>=1 | 200 | 337 | PASS |
| verify_inventory_pending | state=待入库 | 200 | 90 | PASS |
| inbound_to_slot | 200+ok=true | 200 | 33 | PASS |
| verify_inventory_in_stock | state contains 库存中 | 200 | 75 | PASS |
| create_order | 200+order_id | 200 | 142 | PASS |
| allocate_empty | 422 | 422 | 3 | PASS |
| allocate_valid | 200 | 200 | 292 | PASS |
| verify_inventory_pending_shipping | state=待发货 and order match | 200 | 90 | PASS |
| shipping_pending_contains_serial | contains serial | 200 | 17 | PASS |
| shipping_confirm | 200 | 200 | 309 | PASS |
| verify_inventory_shipped | state=已出库 | 200 | 75 | PASS |
| logs_contains_serial | contains serial log | 200 | 25 | PASS |
| sales_forbidden_users_list | 403 | 403 | 25 | PASS |

## 缺陷清单

- 无

## 关键输入输出

### unauthorized_guard_inventory
- Request: `GET /api/v1/inventory/`
- Input: `null`
- Output: `{"detail": "Not authenticated"}`
- Elapsed: `128 ms`

### login_admin
- Request: `POST /api/v1/auth/login`
- Input: `{"username": "admin", "password": "888"}`
- Output: `{"access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJleHAiOjE3NzgyOTc1MDYsInN1YiI6ImFkbWluIiwibmFtZSI6Ilx1N2NmYlx1N2VkZlx1N2JhMVx1NzQwNlx1NTQ1OCIsInJvbGUiOiJBZG1pbiJ9.IrysTMg47OPzCg9Wua29CRIKvLxaCCL4tjuE5Q2WBME", "token_type": "bearer", "user": {"username": "admin", "role": "Admin", "name": "系统管理员"}}`
- Elapsed: `69 ms`

### auto_generate_invalid_qty
- Request: `POST /api/v1/inventory/import-staging/auto-generate`
- Input: `{"batch": "E2E26046875", "model": "FR-400G", "qty": 0, "expected_inbound_date": "2026-04-09", "machine_note": ""}`
- Output: `{"detail": [{"type": "greater_than", "loc": ["body", "qty"], "msg": "Input should be greater than 0", "input": 0, "ctx": {"gt": 0}}]}`
- Elapsed: `24 ms`

### auto_generate_one
- Request: `POST /api/v1/inventory/import-staging/auto-generate`
- Input: `{"batch": "E2E26046875", "model": "FR-400G", "qty": 1, "expected_inbound_date": "2026-04-09", "machine_note": "E2E-20260409_113145_489481"}`
- Output: `{"message": "已生成 1 条数据 (96-E2E26046875-1 ~ 96-E2E26046875-1)"}`
- Elapsed: `69 ms`

### import_staging_list
- Request: `GET /api/v1/inventory/import-staging`
- Input: `null`
- Output: `{"data": [{"批次号": "E2E26046875", "机型": "FR-400G", "流水号": "96-E2E26046875-1", "预计入库时间": "2026-04-09", "机台备注/配置": "E2E-20260409_113145_489481", "f4": "", "状态": "待入库"}]}`
- Elapsed: `26 ms`

### import_confirm_empty
- Request: `POST /api/v1/inventory/import-staging/import-confirm`
- Input: `{"selected_track_nos": [], "expected_inbound_date": "2026-04-09"}`
- Output: `{"detail": "请先勾选至少 1 条数据"}`
- Elapsed: `27 ms`

### import_confirm_valid
- Request: `POST /api/v1/inventory/import-staging/import-confirm`
- Input: `{"selected_track_nos": ["96-E2E26046875-1"], "expected_inbound_date": "2026-04-09"}`
- Output: `{"success": [{"trackNo": "96-E2E26046875-1"}], "failed": [], "success_count": 1, "failed_count": 0}`
- Elapsed: `337 ms`

### verify_inventory_pending
- Request: `GET /api/v1/inventory/`
- Input: `null`
- Output: `{"data": [{"批次号": "", "机型": "FR-400AUTO", "流水号": "93-10-01", "状态": "待入库", "更新时间": "2026-04-08T15:06:00", "占用订单号": "", "客户": "", "代理商": "", "订单备注": "", "预计入库时间": "NaT", "机台备注/配置": "", "Location_Code": ""}, {"批次号": "", "机型": "FR-400AUTO", "流水号": "93-12-217", "状态": "库存中", "更新时间": "NaT", "占用订单号": "", "客户": "", "代理商": "", "订单备注": "", "预计入库时间": "NaT", "机台备注/配置": "", "Location_Code": ""}, {"批次号": "", "机型": "FR-400AUTO", "流水号": "93-12-218", "状态": "库存中", "更新时间": "NaT", "占用订单号": "", "客户": "", "代理商": "", "订单备注": "", "预计入库时间": "NaT", "机台备注/配置": "", "Location_Code": ""}, {"批次号": "", "机型": "FR-400AUTO", "流水号": "93-12-220", "状态": "库存中", "更新时间": "NaT", "占用订单号": "", "客户": "", "代理商": "", "订单备注": "", "预计入库时间":`
- Elapsed: `90 ms`

### inbound_to_slot
- Request: `POST /api/v1/inventory/inbound-to-slot`
- Input: `{"serial_no": "96-E2E26046875-1", "slot_code": "E2E-A01"}`
- Output: `{"ok": true, "code": "OK", "message": "入库成功", "inbound_time": "2026-04-09 11:31:46", "slot_code": "E2E-A01"}`
- Elapsed: `33 ms`

### verify_inventory_in_stock
- Request: `GET /api/v1/inventory/`
- Input: `null`
- Output: `{"data": [{"批次号": "", "机型": "FR-400AUTO", "流水号": "93-10-01", "状态": "待入库", "更新时间": "2026-04-08T15:06:00", "占用订单号": "", "客户": "", "代理商": "", "订单备注": "", "预计入库时间": "NaT", "机台备注/配置": "", "Location_Code": ""}, {"批次号": "", "机型": "FR-400AUTO", "流水号": "93-12-217", "状态": "库存中", "更新时间": "NaT", "占用订单号": "", "客户": "", "代理商": "", "订单备注": "", "预计入库时间": "NaT", "机台备注/配置": "", "Location_Code": ""}, {"批次号": "", "机型": "FR-400AUTO", "流水号": "93-12-218", "状态": "库存中", "更新时间": "NaT", "占用订单号": "", "客户": "", "代理商": "", "订单备注": "", "预计入库时间": "NaT", "机台备注/配置": "", "Location_Code": ""}, {"批次号": "", "机型": "FR-400AUTO", "流水号": "93-12-220", "状态": "库存中", "更新时间": "NaT", "占用订单号": "", "客户": "", "代理商": "", "订单备注": "", "预计入库时间":`
- Elapsed: `75 ms`

### create_order
- Request: `POST /api/v1/planning/orders`
- Input: `{"客户名": "E2E客户", "代理商": "E2E代理", "需求机型": "FR-400Gx1", "需求数量": 1, "备注": "E2E闭环-20260409_113145_489481", "包装选项": "", "发货时间": "2026-04-09"}`
- Output: `{"message": "订单创建成功", "order_id": "SO-20260409-3DAD"}`
- Elapsed: `142 ms`

### allocate_empty
- Request: `POST /api/v1/planning/orders/SO-20260409-3DAD/allocate`
- Input: `{"selected_serial_nos": []}`
- Output: `{"detail": "请先选择要配货的机台"}`
- Elapsed: `3 ms`

### allocate_valid
- Request: `POST /api/v1/planning/orders/SO-20260409-3DAD/allocate`
- Input: `{"selected_serial_nos": ["96-E2E26046875-1"]}`
- Output: `{"message": "配货成功，已锁定 1 台机台"}`
- Elapsed: `292 ms`

### verify_inventory_pending_shipping
- Request: `GET /api/v1/inventory/`
- Input: `null`
- Output: `{"data": [{"批次号": "", "机型": "FR-400AUTO", "流水号": "93-10-01", "状态": "待入库", "更新时间": "2026-04-08T15:06:00", "占用订单号": "", "客户": "", "代理商": "", "订单备注": "", "预计入库时间": "NaT", "机台备注/配置": "", "Location_Code": ""}, {"批次号": "", "机型": "FR-400AUTO", "流水号": "93-12-217", "状态": "库存中", "更新时间": "NaT", "占用订单号": "", "客户": "", "代理商": "", "订单备注": "", "预计入库时间": "NaT", "机台备注/配置": "", "Location_Code": ""}, {"批次号": "", "机型": "FR-400AUTO", "流水号": "93-12-218", "状态": "库存中", "更新时间": "NaT", "占用订单号": "", "客户": "", "代理商": "", "订单备注": "", "预计入库时间": "NaT", "机台备注/配置": "", "Location_Code": ""}, {"批次号": "", "机型": "FR-400AUTO", "流水号": "93-12-220", "状态": "库存中", "更新时间": "NaT", "占用订单号": "", "客户": "", "代理商": "", "订单备注": "", "预计入库时间":`
- Elapsed: `90 ms`

### shipping_pending_contains_serial
- Request: `GET /api/v1/inventory/shipping/pending`
- Input: `null`
- Output: `{"data": [{"批次号": "", "机型": "FR-400XS(PRO)", "流水号": "95-09-126", "状态": "待发货", "更新时间": "2026-04-08T09:33:05", "占用订单号": "SO-20260120-E84E", "客户": "东莞市南城蛤地草塘路7号工业区（宏轩机械）", "代理商": "卢振彪", "订单备注": "", "预计入库时间": "NaT", "机台备注/配置": "", "Location_Code": "", "发货时间": ""}, {"批次号": "", "机型": "FR-500XS(PRO)", "流水号": "95-09-139", "状态": "待发货", "更新时间": "2026-04-08T10:02:00", "占用订单号": "SO-20260120-AF51", "客户": "余姚模具城（余姚市天擎模具厂）", "代理商": "陈利春", "订单备注": "配单滤水箱", "预计入库时间": "NaT", "机台备注/配置": "", "Location_Code": "", "发货时间": "2026-01-24"}, {"批次号": "08-5附加", "机型": "FR-400XS(PRO)", "流水号": "95-08-183", "状态": "待发货", "更新时间": "2026-04-08T09:33:05", "占用订单号": "SO-20260120-E84E", "客户": "东莞市南城蛤地草塘路7号工业区（宏轩机械）", "代理商": "卢振彪", `
- Elapsed: `17 ms`

### shipping_confirm
- Request: `POST /api/v1/inventory/shipping/confirm`
- Input: `{"serial_nos": ["96-E2E26046875-1"]}`
- Output: `{"message": "发货完成，共 1 台"}`
- Elapsed: `309 ms`

### verify_inventory_shipped
- Request: `GET /api/v1/inventory/`
- Input: `null`
- Output: `{"data": [{"批次号": "", "机型": "FR-400AUTO", "流水号": "93-10-01", "状态": "待入库", "更新时间": "2026-04-08T15:06:00", "占用订单号": "", "客户": "", "代理商": "", "订单备注": "", "预计入库时间": "NaT", "机台备注/配置": "", "Location_Code": ""}, {"批次号": "", "机型": "FR-400AUTO", "流水号": "93-12-217", "状态": "库存中", "更新时间": "NaT", "占用订单号": "", "客户": "", "代理商": "", "订单备注": "", "预计入库时间": "NaT", "机台备注/配置": "", "Location_Code": ""}, {"批次号": "", "机型": "FR-400AUTO", "流水号": "93-12-218", "状态": "库存中", "更新时间": "NaT", "占用订单号": "", "客户": "", "代理商": "", "订单备注": "", "预计入库时间": "NaT", "机台备注/配置": "", "Location_Code": ""}, {"批次号": "", "机型": "FR-400AUTO", "流水号": "93-12-220", "状态": "库存中", "更新时间": "NaT", "占用订单号": "", "客户": "", "代理商": "", "订单备注": "", "预计入库时间":`
- Elapsed: `75 ms`

### logs_contains_serial
- Request: `GET /api/v1/logs/transactions?limit=1000`
- Input: `null`
- Output: `{"data": [{"时间": "2026-04-09T11:31:48", "操作类型": "正式发货", "流水号": "96-E2E26046875-1", "操作员": "系统管理员"}, {"时间": "2026-04-09T11:31:47", "操作类型": "配货锁定-SO-20260409-3DAD", "流水号": "96-E2E26046875-1", "操作员": "系统管理员"}, {"时间": "2026-04-08T15:57:22", "操作类型": "正式发货", "流水号": "96-02-06", "操作员": "系统管理员"}, {"时间": "2026-04-08T15:43:18", "操作类型": "正式发货", "流水号": "96-01-600", "操作员": "系统管理员"}, {"时间": "2026-04-08T15:40:22", "操作类型": "正式发货", "流水号": "96-01-378", "操作员": "%E7%B3%BB%E7%BB%9F%E7%AE%A1%E7%90%86%E5%91%98"}, {"时间": "2026-04-08T15:15:05", "操作类型": "配货锁定-SO-20260325-2855", "流水号": "96-02-131", "操作员": "Unknown"}, {"时间": "2026-04-08T15:15:05", "操作类型": "直接配货-自动入库", "流水号": "96-02-131", "操作员": "Unknown"}, {"时间": "2026-`
- Elapsed: `25 ms`

### sales_forbidden_users_list
- Request: `GET /api/v1/users/`
- Input: `null`
- Output: `{"detail": "没有操作权限"}`
- Elapsed: `25 ms`
