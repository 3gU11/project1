"""
测试 v1 (lru_cache) 和 v2 (ttl_cache) 版本函数输出一致性
确保优化不改变功能
"""

import pytest
import pandas as pd
from unittest.mock import MagicMock, patch

from crud.inventory import get_data, get_data_v2
from crud.orders import get_orders, get_orders_v2
from crud.planning import get_factory_plan, get_factory_plan_v2, get_planning_records, get_planning_records_v2


class TestCacheV2Consistency:
    """验证 v2 版本与 v1 版本输出一致"""

    @pytest.fixture(autouse=True)
    def clear_caches(self):
        """每个测试前清除所有缓存"""
        get_data.cache_clear()
        get_data_v2.cache_clear()
        get_orders.cache_clear()
        get_orders_v2.cache_clear()
        get_factory_plan.cache_clear()
        get_factory_plan_v2.cache_clear()
        get_planning_records.cache_clear()
        get_planning_records_v2.cache_clear()
        yield

    def test_inventory_get_data_v1_v2_consistency(self, monkeypatch):
        """测试 inventory get_data v1/v2 输出一致"""
        mock_df = pd.DataFrame({
            "批次号": ["B001", "B002"],
            "机型": ["M1", "M2"],
            "流水号": ["SN001", "SN002"],
            "状态": ["库存中", "待发货"],
        })

        def mock_read_sql(*args, **kwargs):
            return mock_df.copy()

        monkeypatch.setattr("pandas.read_sql", mock_read_sql)

        # 清除缓存后调用
        get_data.cache_clear()
        get_data_v2.cache_clear()

        result_v1 = get_data()
        result_v2 = get_data_v2()

        # 验证列一致
        assert list(result_v1.columns) == list(result_v2.columns)
        # 验证数据一致
        pd.testing.assert_frame_equal(result_v1, result_v2)

    def test_orders_get_orders_v1_v2_consistency(self, monkeypatch):
        """测试 orders get_orders v1/v2 输出一致"""
        mock_df = pd.DataFrame({
            "订单号": ["SO001", "SO002"],
            "客户名": ["客户A", "客户B"],
            "需求数量": [10, 20],
            "status": ["active", "active"],
        })

        def mock_read_sql(*args, **kwargs):
            return mock_df.copy()

        monkeypatch.setattr("pandas.read_sql", mock_read_sql)

        get_orders.cache_clear()
        get_orders_v2.cache_clear()

        result_v1 = get_orders()
        result_v2 = get_orders_v2()

        assert list(result_v1.columns) == list(result_v2.columns)
        pd.testing.assert_frame_equal(result_v1, result_v2)

    def test_planning_get_factory_plan_v1_v2_consistency(self, monkeypatch):
        """测试 planning get_factory_plan v1/v2 输出一致"""
        mock_df = pd.DataFrame({
            "合同号": ["C001", "C002"],
            "机型": ["M1", "M2"],
            "排产数量": [100, 200],
            "状态": ["进行中", "已完成"],
        })

        def mock_read_sql(*args, **kwargs):
            return mock_df.copy()

        monkeypatch.setattr("pandas.read_sql", mock_read_sql)

        get_factory_plan.cache_clear()
        get_factory_plan_v2.cache_clear()

        result_v1 = get_factory_plan()
        result_v2 = get_factory_plan_v2()

        assert list(result_v1.columns) == list(result_v2.columns)
        pd.testing.assert_frame_equal(result_v1, result_v2)

    def test_planning_get_planning_records_v1_v2_consistency(self, monkeypatch):
        """测试 planning get_planning_records v1/v2 输出一致"""
        mock_df = pd.DataFrame({
            "order_id": ["SO001", "SO002"],
            "model": ["M1", "M2"],
            "plan_info": ["info1", "info2"],
            "updated_at": ["2024-01-01", "2024-01-02"],
        })

        def mock_read_sql(*args, **kwargs):
            return mock_df.copy()

        monkeypatch.setattr("pandas.read_sql", mock_read_sql)

        get_planning_records.cache_clear()
        get_planning_records_v2.cache_clear()

        result_v1 = get_planning_records()
        result_v2 = get_planning_records_v2()

        assert list(result_v1.columns) == list(result_v2.columns)
        pd.testing.assert_frame_equal(result_v1, result_v2)

    def test_v2_cache_clear_works(self, monkeypatch):
        """测试 v2 版本的 cache_clear 有效"""
        call_count = 0

        def mock_read_sql(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            return pd.DataFrame({"流水号": [f"SN{call_count}"]})

        monkeypatch.setattr("pandas.read_sql", mock_read_sql)

        get_data_v2.cache_clear()

        # 第一次调用
        result1 = get_data_v2()
        assert call_count == 1
        assert result1.iloc[0]["流水号"] == "SN1"

        # 第二次调用（应命中缓存）
        result2 = get_data_v2()
        assert call_count == 1  # 未增加

        # 清除缓存
        get_data_v2.cache_clear()

        # 第三次调用（应重新执行）
        result3 = get_data_v2()
        assert call_count == 2
        assert result3.iloc[0]["流水号"] == "SN2"

    def test_v2_independent_cache_from_v1(self, monkeypatch):
        """测试 v2 缓存与 v1 缓存独立"""
        call_count = 0

        def mock_read_sql(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            return pd.DataFrame({"流水号": [f"SN{call_count}"]})

        monkeypatch.setattr("pandas.read_sql", mock_read_sql)

        get_data.cache_clear()
        get_data_v2.cache_clear()

        # 调用 v1
        get_data()
        v1_count = call_count

        # 调用 v2（应独立执行，因为缓存不同）
        get_data_v2()
        v2_count = call_count

        # 两个缓存独立，所以应该都执行了 SQL
        assert v1_count >= 1
        assert v2_count >= 2
