"""
TTL 本地缓存组件测试
"""

import time
import pytest
from utils.local_cache import TTLCache, ttl_cache


class TestTTLCache:
    """测试 TTLCache 类"""
    
    def test_basic_set_get(self):
        """测试基本的 set/get 操作"""
        cache = TTLCache(ttl_seconds=60)
        cache.set("key1", "value1")
        assert cache.get("key1") == "value1"
    
    def test_get_nonexistent_key(self):
        """测试获取不存在的键"""
        cache = TTLCache(ttl_seconds=60)
        assert cache.get("nonexistent") is None
    
    def test_ttl_expiration(self):
        """测试 TTL 过期"""
        cache = TTLCache(ttl_seconds=0.1)  # 100ms 过期
        cache.set("key1", "value1")
        assert cache.get("key1") == "value1"
        
        time.sleep(0.15)  # 等待过期
        assert cache.get("key1") is None
    
    def test_clear(self):
        """测试清空缓存"""
        cache = TTLCache(ttl_seconds=60)
        cache.set("key1", "value1")
        cache.set("key2", "value2")
        
        cache.clear()
        assert cache.get("key1") is None
        assert cache.get("key2") is None
    
    def test_delete(self):
        """测试删除指定键"""
        cache = TTLCache(ttl_seconds=60)
        cache.set("key1", "value1")
        cache.set("key2", "value2")
        
        assert cache.delete("key1") is True
        assert cache.get("key1") is None
        assert cache.get("key2") == "value2"
        
        # 删除不存在的键
        assert cache.delete("nonexistent") is False
    
    def test_keys_cleanup_expired(self):
        """测试 keys() 方法清理过期键"""
        cache = TTLCache(ttl_seconds=0.1)
        cache.set("key1", "value1")
        cache.set("key2", "value2")
        
        time.sleep(0.15)
        cache.set("key3", "value3")  # 未过期
        
        keys = cache.keys()
        assert "key1" not in keys
        assert "key2" not in keys
        assert "key3" in keys
    
    def test_info(self):
        """测试缓存信息统计"""
        cache = TTLCache(ttl_seconds=0.1)
        cache.set("key1", "value1")
        cache.set("key2", "value2")
        
        time.sleep(0.15)
        cache.set("key3", "value3")
        
        info = cache.info()
        assert info["total_keys"] == 3
        assert info["expired_keys"] == 2
        assert info["valid_keys"] == 1
        assert info["ttl_seconds"] == 0.1
    
    def test_thread_safety(self):
        """测试线程安全"""
        import threading
        
        cache = TTLCache(ttl_seconds=60)
        results = []
        
        def writer():
            for i in range(100):
                cache.set(f"key{i}", f"value{i}")
        
        def reader():
            for i in range(100):
                val = cache.get(f"key{i}")
                results.append(val)
        
        threads = []
        for _ in range(3):
            t = threading.Thread(target=writer)
            threads.append(t)
            t = threading.Thread(target=reader)
            threads.append(t)
        
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        
        # 不应抛出异常
        assert len(results) > 0


class TestTTLCacheDecorator:
    """测试 ttl_cache 装饰器"""
    
    def test_basic_caching(self):
        """测试基本缓存功能"""
        call_count = 0
        
        @ttl_cache(ttl_seconds=60)
        def get_data():
            nonlocal call_count
            call_count += 1
            return {"data": f"call_{call_count}"}
        
        # 第一次调用
        result1 = get_data()
        assert call_count == 1
        assert result1 == {"data": "call_1"}
        
        # 第二次调用（应命中缓存）
        result2 = get_data()
        assert call_count == 1  # 未增加
        assert result2 == {"data": "call_1"}
    
    def test_cache_expiration(self):
        """测试缓存过期"""
        call_count = 0
        
        @ttl_cache(ttl_seconds=0.1)
        def get_data():
            nonlocal call_count
            call_count += 1
            return {"data": f"call_{call_count}"}
        
        get_data()
        assert call_count == 1
        
        time.sleep(0.15)
        get_data()  # 缓存过期
        assert call_count == 2
    
    def test_cache_clear(self):
        """测试缓存清除"""
        call_count = 0
        
        @ttl_cache(ttl_seconds=60)
        def get_data():
            nonlocal call_count
            call_count += 1
            return {"data": f"call_{call_count}"}
        
        get_data()
        assert call_count == 1
        
        get_data.cache_clear()
        get_data()
        assert call_count == 2
    
    def test_cache_info(self):
        """测试缓存信息"""
        @ttl_cache(ttl_seconds=60)
        def get_data():
            return {"data": "test"}
        
        get_data()
        info = get_data.cache_info()
        assert info["valid_keys"] >= 1
        assert info["ttl_seconds"] == 60
    
    def test_with_arguments(self):
        """测试带参数的函数缓存"""
        call_count = 0
        
        @ttl_cache(ttl_seconds=60)
        def get_data_by_id(id: int, extra: str = "default"):
            nonlocal call_count
            call_count += 1
            return {"id": id, "extra": extra}
        
        # 不同参数应有不同缓存
        get_data_by_id(1)
        get_data_by_id(2)
        assert call_count == 2
        
        # 相同参数应命中缓存
        get_data_by_id(1)
        assert call_count == 2
        
        # 不同关键字参数应有不同缓存
        get_data_by_id(1, extra="other")
        assert call_count == 3


class TestCRUDIntegration:
    """测试与 CRUD 函数的集成场景"""
    
    def test_cache_clear_on_write(self):
        """测试写入后清除缓存"""
        data = {"value": 1}
        
        @ttl_cache(ttl_seconds=60)
        def get_data():
            return data.copy()
        
        # 读取缓存
        result1 = get_data()
        assert result1["value"] == 1
        
        # 修改数据
        data["value"] = 2
        
        # 清除缓存
        get_data.cache_clear()
        
        # 再次读取
        result2 = get_data()
        assert result2["value"] == 2
    
    def test_short_ttl_for_data_consistency(self):
        """测试短 TTL 保证数据一致性"""
        data = {"timestamp": time.time()}
        
        @ttl_cache(ttl_seconds=0.05)  # 50ms TTL
        def get_timestamp():
            return data["timestamp"]
        
        t1 = get_timestamp()
        time.sleep(0.1)
        
        # 修改数据
        data["timestamp"] = time.time()
        
        # 缓存过期后应获取新值
        t2 = get_timestamp()
        assert t2 != t1
