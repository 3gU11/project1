"""
缓存适配模块 - 根据 feature flag 自动切换 v1/v2 缓存实现
提供统一的接口，上层代码无需关心底层缓存实现
"""

import logging
from functools import wraps

from config import USE_TTL_CACHE, TTL_CACHE_SECONDS

logger = logging.getLogger(__name__)

# 导入 v1 和 v2 函数
from crud.inventory import get_data, get_data_v2, save_data, save_data_v2
from crud.inventory import inbound_to_slot, inbound_to_slot_v2
from crud.orders import get_orders, get_orders_v2, save_orders
from crud.planning import get_factory_plan, get_factory_plan_v2, save_factory_plan
from crud.planning import get_planning_records, get_planning_records_v2, save_planning_record
from config import USE_INBOUND_SQL_OPTIMIZED, USE_UPSERT_OPTIMIZED


class CacheAdapter:
    """
    缓存适配器 - 根据 USE_TTL_CACHE 配置自动选择 v1 或 v2 实现

    使用方式：
        from utils.cache_adapter import cache

        # 读取数据
        df = cache.inventory.get_data()

        # 保存数据（自动清除缓存）
        cache.inventory.save_data(df)
    """

    def __init__(self):
        self._mode = "v2" if USE_TTL_CACHE else "v1"
        logger.info(f"CacheAdapter initialized with mode: {self._mode}")

    @property
    def mode(self) -> str:
        return self._mode

    @property
    def is_v2(self) -> bool:
        return self._mode == "v2"

    class InventoryCache:
        """库存数据缓存接口"""

        @staticmethod
        def get_data():
            if USE_TTL_CACHE:
                return get_data_v2()
            return get_data()

        @staticmethod
        def save_data(df):
            """保存数据，自动根据配置选择 UPSERT 或 DELETE+INSERT"""
            if USE_UPSERT_OPTIMIZED:
                return save_data_v2(df)
            return save_data(df)

        @staticmethod
        def cache_clear():
            get_data.cache_clear()
            get_data_v2.cache_clear()

        @staticmethod
        def inbound_to_slot(serial_no, slot_code, is_transfer=False):
            """入库/调拨，自动根据配置选择优化版本"""
            if USE_INBOUND_SQL_OPTIMIZED:
                return inbound_to_slot_v2(serial_no, slot_code, is_transfer)
            return inbound_to_slot(serial_no, slot_code, is_transfer)

    class OrdersCache:
        """订单数据缓存接口"""

        @staticmethod
        def get_orders():
            if USE_TTL_CACHE:
                return get_orders_v2()
            return get_orders()

        @staticmethod
        def save_orders(df):
            return save_orders(df)

        @staticmethod
        def cache_clear():
            get_orders.cache_clear()
            get_orders_v2.cache_clear()

    class PlanningCache:
        """排产数据缓存接口"""

        @staticmethod
        def get_factory_plan():
            if USE_TTL_CACHE:
                return get_factory_plan_v2()
            return get_factory_plan()

        @staticmethod
        def get_planning_records():
            if USE_TTL_CACHE:
                return get_planning_records_v2()
            return get_planning_records()

        @staticmethod
        def save_factory_plan(df):
            return save_factory_plan(df)

        @staticmethod
        def save_planning_record(order_id, model, plan_info):
            return save_planning_record(order_id, model, plan_info)

        @staticmethod
        def cache_clear():
            get_factory_plan.cache_clear()
            get_factory_plan_v2.cache_clear()
            get_planning_records.cache_clear()
            get_planning_records_v2.cache_clear()

    # 提供属性访问
    inventory = InventoryCache()
    orders = OrdersCache()
    planning = PlanningCache()


# 全局适配器实例
cache = CacheAdapter()


def get_cache_info() -> dict:
    """
    获取当前缓存状态信息
    """
    info = {
        "mode": cache.mode,
        "use_ttl_cache": USE_TTL_CACHE,
        "ttl_seconds": TTL_CACHE_SECONDS,
        "use_inbound_sql_optimized": USE_INBOUND_SQL_OPTIMIZED,
        "use_upsert_optimized": USE_UPSERT_OPTIMIZED,
        "functions": {
            "inventory": "get_data_v2" if USE_TTL_CACHE else "get_data",
            "orders": "get_orders_v2" if USE_TTL_CACHE else "get_orders",
            "planning_factory": "get_factory_plan_v2" if USE_TTL_CACHE else "get_factory_plan",
            "planning_records": "get_planning_records_v2" if USE_TTL_CACHE else "get_planning_records",
            "inbound_to_slot": "inbound_to_slot_v2" if USE_INBOUND_SQL_OPTIMIZED else "inbound_to_slot",
            "save_data": "save_data_v2 (UPSERT)" if USE_UPSERT_OPTIMIZED else "save_data (DELETE+INSERT)",
        }
    }

    # 如果可能，获取 TTL 缓存的统计信息
    if USE_TTL_CACHE:
        try:
            info["v2_cache_stats"] = {
                "inventory": get_data_v2.cache_info(),
                "orders": get_orders_v2.cache_info(),
            }
        except Exception:
            pass

    return info
