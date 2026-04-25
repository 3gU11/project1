# V7STD 性能问题清单

> 生成日期：2026-04-22  
> 分析范围：后端 Python（FastAPI + SQLAlchemy + MySQL）

---

## P0 - 必须优先处理

### 1. `init_mysql_tables()` 每次启动全量迁移

- **文件**：`database.py`
- **问题**：每次服务重启都会执行 15+ 条 DDL、全表扫描 `sales_orders` 和 `factory_plan` 并逐行 UPDATE JSON 字段、多条数据清洗 UPDATE、权限数据 DELETE + INSERT 重写
- **影响**：每次重启后首个请求耗时数秒甚至十几秒；数据量越大越严重
- **建议**：
  - 引入 `schema_version` 表，只在版本号变化时执行迁移
  - JSON 规范化、数据清洗改为一次性迁移脚本，不放在热启动路径
  - 权限数据改为 UPSERT，不每次全量重写

---

### 2. `save_data()` / `save_orders()` / `save_factory_plan()` 全表删除再重写

- **文件**：`crud/inventory.py`、`crud/orders.py`、`crud/planning.py`
- **问题**：三个核心保存函数均采用 `DELETE FROM table` + 全量 `INSERT` 模式
- **影响**：
  - 并发写入存在竞态条件（两个请求同时保存会丢数据）
  - 数据量大时事务锁时间长、IO 压力大
  - 外键约束下 DELETE 触发级联检查，进一步拉长事务
- **建议**：
  - `crud/inventory.py` 已有 `update_inventory_rows()` 支持行级 UPDATE，应扩大使用范围
  - `save_orders` / `save_factory_plan` 改为 `INSERT ... ON DUPLICATE KEY UPDATE`（UPSERT）
  - API 层避免调用全表重写方法，改为精准增删改

---

## P1 - 高优先级

### 3. `lru_cache` 无 TTL，缓存失效依赖手动清理

- **文件**：`crud/inventory.py`（`get_data`）、`crud/orders.py`（`get_orders`）、`crud/planning.py`（`get_factory_plan`、`get_planning_records`）
- **问题**：`@lru_cache(maxsize=1)` 无过期时间，只能靠 `cache_clear()` 手动失效；若任何写路径遗漏清缓存，用户将看到脏数据
- **影响**：数据一致性风险，难以排查的"数据不刷新"问题
- **建议**：
  - 改用项目已有的 `fetch_data_with_cache()`（支持 TTL + Redis 降级）
  - 或统一在所有写路径加缓存清理，并做覆盖测试

---

### 4. `inbound_to_slot()` 内全表扫描做库位容量检查

- **文件**：`crud/inventory.py`
- **问题**：
  ```python
  stats_df = pd.read_sql(
      "SELECT `流水号`, `Location_Code`, `状态`, `更新时间` FROM finished_goods_data",
      conn,
  )
  ```
  每次入库一台机器，先把整张库存表读入内存再用 Python 过滤
- **影响**：库存量大时单次入库操作延迟明显，且持有连接时间长
- **建议**：改为 SQL 聚合查询：
  ```sql
  SELECT COUNT(*) FROM finished_goods_data
  WHERE `Location_Code` = :slot_code AND `状态` LIKE '库存中%'
  ```

---

## P2 - 中优先级

### 5. `_reconcile_completed_orders()` 频繁触发全量写回

- **文件**：`api/routes/planning.py`
- **问题**：函数遍历所有订单，查已出库数量，若有变化则调用 `save_orders()`（全表删除重写）；若被高频路由调用，产生严重写放大
- **影响**：不必要的写 IO，加剧锁竞争
- **建议**：
  - 改为事件驱动：发货确认时直接更新对应订单状态
  - 或改为后台定期任务，不在请求路径上同步执行

---

### 6. 缩略图每次请求动态生成，无缓存

- **文件**：`api/routes/inventory.py`（`machine_archive_thumbnail`）
- **问题**：每次请求都用 Pillow 打开原图、等比缩放、编码返回，不做任何缓存
- **影响**：图片多时重复计算，CPU 和 IO 浪费
- **建议**：首次生成后缓存到磁盘（如 `{sn_dir}/.thumbs/{file_name}`），后续命中缓存直接返回

---

### 7. 合同 DOCX 预览每次重新转换，无缓存

- **文件**：`api/routes/planning.py`（`preview_contract_file_api`）
- **问题**：每次请求都调 `mammoth.convert_to_html()`，转换结果不缓存
- **影响**：重复 CPU 开销，对大文件体感明显
- **建议**：将转换结果缓存到磁盘或内存（可用文件 mtime 做失效判断）

---

### 8. Redis 对小结果集使用 Parquet 序列化开销过大

- **文件**：`utils/cache.py`（`fetch_data_with_cache`）
- **问题**：所有结果统一用 Parquet + Snappy 压缩写入 Redis；对几十行的小结果集，序列化/反序列化开销可能高于直接查 SQL
- **影响**：缓存效率下降，小查询反而更慢
- **建议**：按结果集大小选择序列化策略：
  - 小结果集（< 100 行）：JSON
  - 大结果集：Parquet + Snappy

---

## 安全 / 架构提示（非性能，供参考）

### 9. CORS 全开

- **文件**：`api/main.py`
- `allow_origins=["*"]` 在生产环境应限制为前端实际域名

### 10. JWT 30 天有效期无撤销机制

- **文件**：`api/routes/auth.py`
- `ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24 * 30`，签发后无法主动失效
- 建议：加 token 黑名单，或缩短有效期 + 引入 refresh token

### 11. 密码哈希升级失败无重试

- **文件**：`core/auth.py`
- 明文密码升级为哈希时，`update_user_password` 失败只记 warning，存在密码永远无法升级的风险
- 建议：失败时下次登录再重试，或给 admin 提供手动触发升级接口

---

## 优先级汇总

| 优先级 | 编号 | 问题 | 主要影响 |
|--------|------|------|----------|
| P0 | 1 | `init_mysql_tables` 全量迁移 | 启动耗时 |
| P0 | 2 | `save_data/orders/plan` 全表删重写 | 并发安全 + 写 IO |
| P1 | 3 | `lru_cache` 无 TTL | 数据一致性风险 |
| P1 | 4 | `inbound_to_slot` 全表扫描 | 入库请求延迟 |
| P2 | 5 | 订单完结检查写放大 | 不必要写 IO |
| P2 | 6 | 缩略图无缓存 | 重复 CPU/IO |
| P2 | 7 | DOCX 预览无缓存 | 重复 CPU |
| P2 | 8 | Redis 小结果集 Parquet 开销 | 缓存效率 |
