# 最新系统深度性能诊断与优化指南 (v2)

通过对系统最新代码（包括后端的 FastAPI 路由、CRUD 数据操作层、数据库表结构以及文件处理逻辑）的深度遍历和分析，我发现目前系统在**内存使用**、**接口设计**、**异步并发机制**以及**数据库索引**等方面仍然存在显著的性能瓶颈。

以下是详细的性能分析与优化方案，您可以直接将这份 Markdown 文档提供给 AI IDE 进行针对性的重构和修复。

---

## 1. 致命的内存爆炸风险：全量拉取与无分页 API (Critical)

**瓶颈位置**：
*   **后端 CRUD 层**：
    *   [crud/inventory.py](file:///workspace/crud/inventory.py) 中的 `get_data()`、`get_import_staging()`。
    *   [crud/orders.py](file:///workspace/crud/orders.py) 中的 `get_orders()`。
    *   [crud/contracts.py](file:///workspace/crud/contracts.py) 中的 `get_contract_files()`。
*   **后端 API 路由层 (FastAPI)**：
    *   [api/routes/inventory.py](file:///workspace/api/routes/inventory.py) 的 `GET /api/v1/inventory/`。
    *   [api/routes/planning.py](file:///workspace/api/routes/planning.py) 的 `GET /api/v1/planning/` 和 `GET /api/v1/planning/orders`。
    *   [api/routes/users.py](file:///workspace/api/routes/users.py) 的 `GET /api/v1/users/`。

**问题分析**：
整个系统的数据读取逻辑几乎全部采用了 `SELECT * FROM table` 的全表扫描模式。更危险的是，在对外暴露的 RESTful API 中，没有任何一个接口实现了**分页 (Pagination)** 或**增量加载 (Lazy Loading)**。
当外部系统（如前端大屏或第三方对接系统）调用 `GET /api/v1/inventory/` 时，后端会将所有几十万条历史库存记录全部读入 Pandas，再通过 `df.to_dict(orient="records")` 全量序列化为巨大的 JSON 字符串返回。这不仅会导致极端的网络拥堵，还会让服务器内存瞬间暴涨，引发频繁的垃圾回收 (GC) 甚至 OOM 崩溃。此外，像 `api/routes/inventory.py` 里的批量保存接口接收全量列表覆盖保存，写库开销极大。

**优化方案**：
1.  **实现分页机制**：重构所有的 `GET` 列表接口，强制引入 `skip` (或 `page`) 和 `limit` 参数。
2.  **按需查询**：对于不需要展示全量数据的场景（如只需看“待入库”的机器），必须在接口层提供过滤参数，并在底层的 SQL 语句中拼接 `WHERE` 条件，实现真正的**数据库计算下推**。
3.  **增量更新**：重构保存/更新接口，改为仅接收并处理发生变动的记录（Delta Update），而非全量覆盖。

---

## 2. 并发杀手：异步路由中的同步阻塞调用 (High)

**瓶颈位置**：
*   [api/routes/inventory.py](file:///workspace/api/routes/inventory.py) -> `async def machine_archive_upload(...)`
*   [api/routes/inventory.py](file:///workspace/api/routes/inventory.py) -> `async def upload_tracking_sheet(...)`
*   [api/routes/planning.py](file:///workspace/api/routes/planning.py) -> `async def upload_contract_file_api(...)`

**问题分析**：
FastAPI 的核心优势在于基于 `asyncio` 的高并发处理能力。但上述路由被错误地声明为 `async def`，并在其内部直接执行了**耗时的同步操作**：
1.  **同步磁盘 I/O**：`machine_archive_upload` 中使用了 `with open(save_path, "wb") as f: f.write(content)`。
2.  **同步 CPU 密集型计算**：`upload_tracking_sheet` 中同步调用了 `parse_tracking_xls`（涉及复杂的 Excel 解析和 Pandas 运算）；`upload_contract_file_api` 同步调用了 `save_contract_file` 甚至文档格式转换。
在 `async def` 中执行这些同步阻塞操作，会直接**挂起（Block）整个事件循环 (Event Loop)**。在这几百毫秒甚至几秒内，FastAPI 无法处理任何其他并发请求，并发性能直接降为单线程水平。

**优化方案**：
*   **方法一：利用 FastAPI 内部线程池**：如果不想改写底层逻辑，只需去掉路由定义前面的 `async` 关键字（即改为 `def machine_archive_upload(...)`），FastAPI 会自动将其放入后台线程池运行，从而不阻塞主事件循环。
*   **方法二：全面异步化**：保留 `async def`，但将文件写入改为 `aiofiles` 流式写入；将 CPU 密集型任务放入 `asyncio.to_thread()` 甚至专用的后台任务队列（如 Celery 或 FastAPI 的 `BackgroundTasks`）中异步执行。

---

## 3. 性能退化的根源：缺失的高频查询索引 (High)

**瓶颈位置**：
*   [database.py](file:///workspace/database.py) 的 `init_mysql_tables` 初始化 DDL 脚本。

**问题分析**：
虽然之前在 `database.py` 中补充了一些外键和基本索引，但对于业务中最核心、最高频的检索条件，依然缺乏**复合索引 (Composite Index)** 的支持。随着数据积累，这会导致大量的慢查询：
1.  `finished_goods_data`（库存表）：缺少 `(状态, 机型)` 和 `(状态, Location_Code)` 的复合索引。导致聚合分组统计（如库位看板、机型分布）时产生全表扫描。
2.  `sales_orders`（订单表）：缺少 `(客户名)` 和 `(客户名, 下单时间)` 索引，严重拖慢按客户维度的模糊搜索和历史订单检索。
3.  `transaction_log`（日志表）：缺少单纯针对 `(时间)` 字段的单列索引。由于日志总是按时间倒序拉取（`ORDER BY 时间 DESC`），无索引会导致极其昂贵的 Filesort 排序开销。
4.  `contract_records`（合同记录表）：缺少 `(contract_id)` 和 `(upload_time)` 索引，影响附件的关联查找效率。

**优化方案**：
在 `database.py` 的迁移脚本部分，使用 `ALTER TABLE ... ADD INDEX ...` 补充上述缺失的关键索引。这能将绝大多数的统计和列表查询的耗时从秒级降低到几毫秒。

---

## 4. 隐蔽的性能陷阱：大文件的全量内存读取 (Medium)

**瓶颈位置**：
*   文件上传相关的 API（如机台档案、合同附件上传）。

**问题分析**：
在处理文件上传时，代码中使用了类似 `content = await up.read()` 的方式，这会将用户上传的整个文件（可能是几十 MB 的图纸或 PDF）**全量加载到服务器的物理内存中**。如果有多个用户同时上传大文件，极易触发操作系统的 OOM-Killer 强制杀掉 Python 进程。

**优化方案**：
改用流式分块读取并写入磁盘：
```python
import aiofiles

async with aiofiles.open(save_path, 'wb') as out_file:
    while content := await up.read(1024 * 1024):  # 每次只读 1MB
        await out_file.write(content)
```
这样不论文件多大，内存占用始终保持在几 MB 级别。