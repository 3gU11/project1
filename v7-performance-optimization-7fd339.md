# V7ex 性能优化方案

针对 performance_issues.md 中识别的 11 个问题，制定全面优化方案，采用纯本地缓存策略（不使用 Redis）。

## 优化总览

| 优先级 | 问题数量 | 预计工时 | 风险等级 |
|--------|----------|----------|----------|
| P0 | 2 | 4-6h | 中 |
| P1 | 2 | 3-4h | 低 |
| P2 | 3 | 4-6h | 低 |
| 安全 | 3 | 2-3h | 中 |

---

## P0 - 必须优先处理

### 1. init_mysql_tables() 启动优化

**问题**：每次启动执行 15+ DDL、全表扫描 UPDATE、权限数据 DELETE+INSERT 重写

**方案**：引入 Schema 版本控制 + 数据迁移分离

```python
# 新增 schema_version 表，记录已执行的迁移版本
# 每次启动只检查版本，无需执行完整迁移

迁移脚本拆分：
- migrations/001_initial_schema.sql
- migrations/002_json_normalize.sql  
- migrations/003_add_indexes.sql
- migrations/004_data_cleanup.sql

启动时只执行当前版本之后的迁移
```

**关键修改**：
- `database.py`：新增 `schema_migrations` 表和版本检查逻辑
- `scripts/migrations/`：迁移脚本目录
- 权限数据改为 `INSERT IGNORE` 而非 DELETE+INSERT

---

### 2. save_data/orders/plan 全表删重写修复

**问题**：三个核心保存函数使用 `DELETE + INSERT` 模式，并发不安全、IO 压力大

**方案**：改为行级 UPSERT 策略

```python
# inventory.py - save_data 改为行级更新
# 区分新增、修改、删除三种操作

def save_data_optimized(df_new):
    df_old = get_data()
    
    # 1. 识别新增、修改、删除
    new_serials = set(df_new['流水号'])
    old_serials = set(df_old['流水号'])
    
    to_insert = df_new[df_new['流水号'].isin(new_serials - old_serials)]
    to_delete = old_serials - new_serials
    to_update = df_new[df_new['流水号'].isin(new_serials & old_serials)]
    
    # 2. 执行精准 SQL
    with engine.begin() as conn:
        if to_delete:
            conn.execute(delete_stmt, to_delete)
        if not to_insert.empty:
            conn.execute(insert_stmt, to_insert)
        for _, row in to_update.iterrows():
            conn.execute(update_stmt, row)
```

**关键修改**：
- `crud/inventory.py`：重构 `save_data()`
- `crud/orders.py`：重构 `save_orders()` 为 `INSERT ... ON DUPLICATE KEY UPDATE`
- `crud/planning.py`：重构 `save_factory_plan()`

---

## P1 - 高优先级

### 3. lru_cache 无 TTL 修复

**问题**：`@lru_cache(maxsize=1)` 无过期时间，脏数据风险

**方案**：使用带 TTL 的本地缓存（纯内存 + 线程安全）

```python
# utils/local_cache.py - 替代 lru_cache

import threading
import time
from collections import OrderedDict

class TTLCache:
    """带 TTL 的线程安全本地缓存"""
    def __init__(self, ttl_seconds=60):
        self.ttl = ttl_seconds
        self._cache = {}
        self._lock = threading.RLock()
    
    def get(self, key):
        with self._lock:
            if key not in self._cache:
                return None
            expire_time, value = self._cache[key]
            if time.time() > expire_time:
                del self._cache[key]
                return None
            return value
    
    def set(self, key, value):
        with self._lock:
            self._cache[key] = (time.time() + self.ttl, value)
    
    def clear(self):
        with self._lock:
            self._cache.clear()

# 使用装饰器模式
from functools import wraps

def ttl_cache(ttl_seconds=60):
    cache = TTLCache(ttl_seconds)
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            key = str(args) + str(sorted(kwargs.items()))
            result = cache.get(key)
            if result is None:
                result = func(*args, **kwargs)
                cache.set(key, result)
            return result
        wrapper.cache_clear = cache.clear
        return wrapper
    return decorator
```

**关键修改**：
- 新增 `utils/local_cache.py`
- `crud/inventory.py`、`crud/orders.py`、`crud/planning.py` 替换 `@lru_cache` 为 `@ttl_cache(ttl=30)`

---

### 4. inbound_to_slot() 全表扫描修复

**问题**：每次入库读取全表到内存过滤

**方案**：改为 SQL 聚合查询

```python
# 原代码（性能差）
stats_df = pd.read_sql("SELECT ... FROM finished_goods_data", conn)
slot_df = stats_df[stats_df["Location_Code"] == slot_code]

# 优化后（性能好）
count_result = conn.execute(text("""
    SELECT COUNT(*) as cnt 
    FROM finished_goods_data 
    WHERE `Location_Code` = :slot_code 
    AND `状态` LIKE '库存中%'
"""), {"slot_code": slot_code}).scalar()

if count_result >= WAREHOUSE_MAX_CAPACITY:
    return {"ok": False, "code": "E_SLOT_FULL", ...}
```

**关键修改**：
- `crud/inventory.py:328-334` 替换为 SQL COUNT 查询
- 确保有复合索引 `idx_fg_status_location`

---

## P2 - 中优先级

### 5. _reconcile_completed_orders() 写放大修复

**问题**：遍历所有订单后全表重写

**方案**：改为事件驱动 + 精准更新

```python
# 方案 A：发货确认时直接更新订单状态（推荐）
# 在 shipping_confirm API 中：
if shipped_count >= order_qty:
    conn.execute(text(
        "UPDATE sales_orders SET status='done' WHERE 订单号=:oid"
    ), {"oid": order_id})

# 方案 B：后台定期任务（备选）
# 使用 APScheduler 每 5 分钟执行一次，不在请求路径上
```

**关键修改**：
- `api/routes/planning.py`：移除或重构 `_reconcile_completed_orders()`
- `api/routes/inventory.py`：发货确认时直接更新订单状态

---

### 6. 缩略图无缓存修复

**问题**：每次请求动态生成缩略图

**方案**：磁盘缓存（首次生成后缓存到 `.thumbs/`）

```python
import os
from pathlib import Path

def machine_archive_thumbnail(serial_no: str, file_name: str):
    sn_dir = _ensure_sn_dir(serial_no)
    safe_file = _safe_name(file_name)
    abs_path = os.path.join(sn_dir, safe_file)
    
    # 检查缩略图缓存
    thumb_dir = os.path.join(sn_dir, ".thumbs")
    thumb_path = os.path.join(thumb_dir, f"{safe_file}.thumb.jpg")
    
    if os.path.exists(thumb_path):
        # 检查原图是否修改
        if os.path.getmtime(thumb_path) >= os.path.getmtime(abs_path):
            return FileResponse(thumb_path)
    
    # 生成新缩略图
    os.makedirs(thumb_dir, exist_ok=True)
    with Image.open(abs_path) as img:
        img.thumbnail((400, 400))
        img.convert('RGB').save(thumb_path, 'JPEG', quality=85)
    
    return FileResponse(thumb_path)
```

**关键修改**：
- `api/routes/inventory.py:859-893` 重构缩略图逻辑

---

### 7. DOCX 预览无缓存修复

**问题**：每次请求重新转换 DOCX

**方案**：转换结果缓存（使用文件 mtime 判断失效）

```python
import hashlib

def preview_contract_file_api(contract_id: str, file_name: str):
    file_path = ...
    cache_dir = os.path.join(CONTRACT_ABS_DIR, ".preview_cache")
    cache_key = hashlib.md5(f"{file_path}:{os.path.getmtime(file_path)}".encode()).hexdigest()
    cache_file = os.path.join(cache_dir, f"{cache_key}.html")
    
    if os.path.exists(cache_file):
        with open(cache_file, 'r', encoding='utf-8') as f:
            return {"html": f.read()}
    
    # 执行转换
    with open(file_path, 'rb') as f:
        result = mammoth.convert_to_html(f)
    
    os.makedirs(cache_dir, exist_ok=True)
    with open(cache_file, 'w', encoding='utf-8') as f:
        f.write(result.value)
    
    return {"html": result.value}
```

**关键修改**：
- `api/routes/planning.py` 添加转换缓存逻辑

---

### 8. 小结果集序列化优化（Redis 未启用时）

**问题**：缓存统一使用 Parquet + Snappy，小数据集开销大

**方案**：纯本地缓存时改用 JSON（已无需 Redis 相关代码）

```python
# utils/local_cache.py - 针对小结果集优化

def cache_dataframe(df: pd.DataFrame, ttl: int = 30):
    """小结果集直接缓存 DataFrame 对象"""
    if len(df) < 100:
        # 直接缓存对象（内存中）
        return df
    else:
        # 大结果集可考虑 pickle 或 feather
        pass
```

**关键修改**：
- 无需修改，使用 P1 中新建的 `TTLCache` 替代现有缓存

---

## 安全/架构修复

### 9. CORS 配置收紧

**问题**：`allow_origins=["*"]` 生产环境不安全

**方案**：从环境变量读取允许的域名

```python
# api/main.py
from config import ALLOWED_ORIGINS

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,  # 从 .env 读取
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["Authorization", "Content-Type"],
)
```

**关键修改**：
- `config.py` 添加 `ALLOWED_ORIGINS` 配置
- `api/main.py` 更新 CORS 配置
- `.env.example` 添加模板

---

### 10. JWT 有效期与撤销机制

**问题**：30 天有效期无撤销机制

**方案**：缩短有效期 + 数据库 token 黑名单

```python
# api/routes/auth.py
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 8  # 8 小时

# 新增撤销表
def revoke_token(token: str):
    jti = get_token_jti(token)  # 解析 JWT ID
    conn.execute(text(
        "INSERT INTO token_blacklist (jti, expires_at) VALUES (:jti, :exp)"
    ), {"jti": jti, "exp": token_exp})

def is_token_revoked(jti: str) -> bool:
    result = conn.execute(text(
        "SELECT 1 FROM token_blacklist WHERE jti=:jti"
    ), {"jti": jti}).fetchone()
    return result is not None
```

**关键修改**：
- `database.py`：新增 `token_blacklist` 表
- `api/routes/auth.py`：缩短有效期，增加撤销逻辑

---

### 11. 密码哈希升级

**问题**：明文存储密码，无哈希升级机制

**方案**：逐步迁移到 bcrypt，支持自动升级

```python
# core/auth.py
from passlib.context import CryptContext

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def verify_login(username, password):
    user = get_user(username)
    stored_hash = user.get('password', '')
    
    # 检查是否是明文（旧数据）
    if not stored_hash.startswith('$2'):
        if stored_hash == password:
            # 验证成功，升级为哈希
            new_hash = pwd_context.hash(password)
            update_password(username, new_hash)
            return True
        return False
    
    # 验证哈希
    if pwd_context.verify(password, stored_hash):
        return True
    return False
```

**关键修改**：
- `requirements.txt`：添加 `passlib[bcrypt]`
- `core/auth.py`：重构登录验证逻辑
- `crud/users.py`：密码创建/更新使用哈希

---

## 实施顺序建议

### 阶段 1：P1 缓存修复（最快见效）
1. 创建 `utils/local_cache.py`
2. 替换所有 `@lru_cache` 为 `@ttl_cache`
3. 修复 `inbound_to_slot()` 全表扫描

### 阶段 2：P0 核心修复（风险较高，需测试）
4. 实现 Schema 版本控制
5. 重构 `save_data/orders/plan` 为 UPSERT

### 阶段 3：P2 优化（提升体验）
6. 缩略图磁盘缓存
7. DOCX 预览缓存
8. 订单状态事件驱动更新

### 阶段 4：安全加固
9. CORS 收紧
10. JWT 有效期与撤销
11. 密码哈希升级

---

## 测试要点

| 测试项 | 验证内容 |
|--------|----------|
| 并发写入 | 多线程同时 save_data 是否丢数据 |
| 缓存 TTL | 30 秒后缓存是否自动失效 |
| 启动时间 | init_mysql_tables 执行时间 < 1s |
| 入库性能 | 1000 台机器入库时间 < 5s |
| 缩略图缓存 | 二次访问是否命中缓存 |
| JWT 撤销 | 登出后 token 是否失效 |

---

## 回滚策略

- 每个阶段独立分支开发
- 保留原函数作为 `xxx_legacy()` 备用
- 通过 feature flag 控制切换
