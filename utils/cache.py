import os
import hashlib
import logging
import io
import time
import fnmatch
from threading import Lock
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
from sqlalchemy import text

from database import get_engine

try:
    import redis
    REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
    REDIS_PORT = int(os.getenv("REDIS_PORT", 6379))
    redis_client = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, db=0, socket_timeout=1)
    redis_client.ping()
    REDIS_AVAILABLE = True
except Exception as e:
    logging.warning(f"Redis not available, falling back to local cache: {e}")
    REDIS_AVAILABLE = False


_LOCAL_CACHE: dict[str, tuple[float, pd.DataFrame]] = {}
_LOCAL_CACHE_LOCK = Lock()


def fetch_data_with_cache(query: str, params: dict = None, ttl: int = 30) -> pd.DataFrame:
    """
    带缓存的 SQL 查询封装。
    优先使用 Redis (Parquet序列化压缩)，降级使用 st.cache_data
    """
    params = params or {}
    key_str = f"{query}_{sorted(params.items())}"
    cache_key = f"sql_cache:{hashlib.md5(key_str.encode()).hexdigest()}"

    if not REDIS_AVAILABLE:
        now = time.time()
        with _LOCAL_CACHE_LOCK:
            item = _LOCAL_CACHE.get(cache_key)
            if item and item[0] > now:
                return item[1].copy()

    if REDIS_AVAILABLE:
        try:
            cached_data = redis_client.get(cache_key)
            if cached_data:
                buf = io.BytesIO(cached_data)
                table = pq.read_table(buf)
                return table.to_pandas()
        except Exception as e:
            logging.error(f"Redis read error: {e}")

    try:
        with get_engine().connect() as conn:
            result = conn.execute(text(query), params)
            df = pd.DataFrame(result.mappings().all())
        if df.empty:
            # 确保即使没有数据也返回正确的列结构（如果可能），
            # 或者至少返回一个带列名但没行的 DF。
            # 这里简单返回空 DF。
            return pd.DataFrame()
    except Exception as e:
        logging.error(f"SQL fetch error: {e}")
        return pd.DataFrame()

    try:
        if REDIS_AVAILABLE:
            if not df.empty:
                table = pa.Table.from_pandas(df)
                buf = io.BytesIO()
                pq.write_table(table, buf, compression='snappy')
                redis_client.setex(cache_key, ttl, buf.getvalue())
        else:
            with _LOCAL_CACHE_LOCK:
                _LOCAL_CACHE[cache_key] = (time.time() + max(int(ttl), 1), df.copy())
    except Exception as e:
        logging.error(f"Cache write error: {e}")

    return df

def clear_cache_pattern(pattern: str = "sql_cache:*"):
    """清除特定的 Redis 缓存和本地内存缓存"""
    with _LOCAL_CACHE_LOCK:
        for key in list(_LOCAL_CACHE.keys()):
            if fnmatch.fnmatch(key, pattern):
                _LOCAL_CACHE.pop(key, None)
    if REDIS_AVAILABLE:
        try:
            keys = redis_client.keys(pattern)
            if keys:
                redis_client.delete(*keys)
        except Exception:
            pass
