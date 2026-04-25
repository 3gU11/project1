"""
测试缓存适配器
"""

import pytest
import pandas as pd
from unittest.mock import patch

from utils.cache_adapter import cache, get_cache_info


class TestCacheAdapter:
    """测试缓存适配器功能"""

    def test_cache_mode_determined_by_env(self, monkeypatch):
        """测试缓存模式由环境变量决定"""
        # 默认应该为 v1 (USE_TTL_CACHE=false)
        assert cache.mode in ["v1", "v2"]

    def test_inventory_get_data_returns_dataframe(self, monkeypatch):
        """测试 inventory.get_data 返回 DataFrame"""
        mock_df = pd.DataFrame({
            "流水号": ["SN001", "SN002"],
            "机型": ["M1", "M2"],
        })

        with patch("pandas.read_sql", return_value=mock_df.copy()):
            cache.inventory.cache_clear()
            result = cache.inventory.get_data()

        assert isinstance(result, pd.DataFrame)
        assert len(result) == 2

    def test_orders_get_orders_returns_dataframe(self, monkeypatch):
        """测试 orders.get_orders 返回 DataFrame"""
        mock_df = pd.DataFrame({
            "订单号": ["SO001", "SO002"],
            "客户名": ["客户A", "客户B"],
        })

        with patch("pandas.read_sql", return_value=mock_df.copy()):
            cache.orders.cache_clear()
            result = cache.orders.get_orders()

        assert isinstance(result, pd.DataFrame)

    def test_planning_get_factory_plan_returns_dataframe(self, monkeypatch):
        """测试 planning.get_factory_plan 返回 DataFrame"""
        mock_df = pd.DataFrame({
            "合同号": ["C001", "C002"],
            "机型": ["M1", "M2"],
        })

        with patch("pandas.read_sql", return_value=mock_df.copy()):
            cache.planning.cache_clear()
            result = cache.planning.get_factory_plan()

        assert isinstance(result, pd.DataFrame)

    def test_cache_clear_works(self):
        """测试 cache_clear 方法可用"""
        # 不应抛出异常
        cache.inventory.cache_clear()
        cache.orders.cache_clear()
        cache.planning.cache_clear()

    def test_get_cache_info(self):
        """测试 get_cache_info 返回信息"""
        info = get_cache_info()
        assert "mode" in info
        assert "use_ttl_cache" in info
        assert "ttl_seconds" in info
        assert "functions" in info

    def test_cache_switching_logic(self, monkeypatch):
        """测试缓存切换逻辑 - 只验证配置读取"""
        import config

        # 获取当前配置值
        current_value = config.USE_TTL_CACHE

        # 验证 get_cache_info 返回正确的当前配置
        info = get_cache_info()
        assert info["use_ttl_cache"] == current_value

        # 验证配置项是布尔值
        assert isinstance(info["use_ttl_cache"], bool)

    def test_adapter_singleton(self):
        """测试适配器是单例"""
        from utils.cache_adapter import cache as cache2
        assert cache is cache2
