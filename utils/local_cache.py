"""
TTL 本地缓存组件
替代 @lru_cache(maxsize=1) 的无过期时间问题
"""

import threading
import time
from functools import wraps
from typing import Any, Callable, Optional, TypeVar

T = TypeVar('T')


class TTLCache:
    """
    线程安全的 TTL 本地缓存
    替代无过期时间的 lru_cache
    """
    
    def __init__(self, ttl_seconds: float = 30.0):
        """
        Args:
            ttl_seconds: 缓存过期时间（秒）
        """
        self.ttl = ttl_seconds
        self._cache: dict[str, tuple[float, Any]] = {}
        self._lock = threading.RLock()
    
    def get(self, key: str) -> Optional[Any]:
        """
        获取缓存值，过期返回 None
        """
        with self._lock:
            if key not in self._cache:
                return None
            expire_time, value = self._cache[key]
            if time.time() > expire_time:
                del self._cache[key]
                return None
            return value
    
    def set(self, key: str, value: Any) -> None:
        """
        设置缓存值
        """
        with self._lock:
            self._cache[key] = (time.time() + self.ttl, value)
    
    def clear(self) -> None:
        """
        清空缓存
        """
        with self._lock:
            self._cache.clear()
    
    def delete(self, key: str) -> bool:
        """
        删除指定缓存键
        Returns:
            是否成功删除
        """
        with self._lock:
            if key in self._cache:
                del self._cache[key]
                return True
            return False
    
    def keys(self) -> list[str]:
        """
        获取所有缓存键（清理过期键）
        """
        with self._lock:
            now = time.time()
            expired_keys = [
                k for k, (expire_time, _) in self._cache.items() 
                if now > expire_time
            ]
            for k in expired_keys:
                del self._cache[k]
            return list(self._cache.keys())
    
    def info(self) -> dict:
        """
        获取缓存统计信息
        """
        with self._lock:
            now = time.time()
            total = len(self._cache)
            expired = sum(1 for expire_time, _ in self._cache.values() if now > expire_time)
            return {
                "total_keys": total,
                "expired_keys": expired,
                "valid_keys": total - expired,
                "ttl_seconds": self.ttl
            }


def ttl_cache(ttl_seconds: float = 30.0):
    """
    装饰器：为函数添加 TTL 缓存
    
    使用方式：
        @ttl_cache(ttl_seconds=60)
        def get_data():
            return expensive_query()
    
    清除缓存：
        get_data.cache_clear()
    
    Args:
        ttl_seconds: 缓存过期时间（秒）
    """
    cache = TTLCache(ttl_seconds)
    
    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @wraps(func)
        def wrapper(*args, **kwargs) -> T:
            # 构建缓存键（基于参数）
            key_parts = [func.__name__]
            if args:
                key_parts.append(str(args))
            if kwargs:
                key_parts.append(str(sorted(kwargs.items())))
            cache_key = "|".join(key_parts)
            
            # 尝试获取缓存
            result = cache.get(cache_key)
            if result is not None:
                return result
            
            # 执行函数并缓存
            result = func(*args, **kwargs)
            cache.set(cache_key, result)
            return result
        
        # 附加缓存操作方法
        wrapper.cache_clear = cache.clear
        wrapper.cache_info = cache.info
        wrapper._ttl_cache_instance = cache
        
        return wrapper
    
    return decorator


# 兼容性：提供与 functools.lru_cache 类似的接口
class CacheInfo:
    """缓存信息统计"""
    def __init__(self, hits: int, misses: int, maxsize: int, currsize: int):
        self.hits = hits
        self.misses = misses
        self.maxsize = maxsize
        self.currsize = currsize
