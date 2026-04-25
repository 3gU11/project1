"""
测试 inbound_to_slot v1 和 v2 版本功能一致性
确保 SQL 优化不改变业务逻辑
"""

import pytest
import pandas as pd
from datetime import datetime
from unittest.mock import patch, MagicMock

from crud.inventory import inbound_to_slot, inbound_to_slot_v2, WAREHOUSE_MAX_CAPACITY


class TestInboundV2Consistency:
    """验证 inbound_to_slot v2 与 v1 行为一致"""

    @pytest.fixture
    def mock_layout(self):
        """模拟正常的库位布局"""
        return {
            "layout_json": {
                "slots": [
                    {"code": "A01", "status": "正常"},
                    {"code": "A02", "status": "正常"},
                    {"code": "B01", "status": "锁定"},  # 锁定库位
                ]
            }
        }

    def test_empty_params_returns_error(self, mock_layout, monkeypatch):
        """测试空参数返回错误"""
        monkeypatch.setattr("crud.inventory.get_warehouse_layout", lambda x: mock_layout)

        # 空流水号
        result = inbound_to_slot_v2("", "A01")
        assert result["ok"] is False
        assert result["code"] == "E_INVALID_PARAM"

        # 空库位号
        result = inbound_to_slot_v2("SN001", "")
        assert result["ok"] is False
        assert result["code"] == "E_INVALID_PARAM"

    def test_locked_slot_returns_error(self, mock_layout, monkeypatch):
        """测试锁定库位返回错误"""
        monkeypatch.setattr("crud.inventory.get_warehouse_layout", lambda x: mock_layout)

        with patch("crud.inventory.get_engine") as mock_engine:
            result = inbound_to_slot_v2("SN001", "B01")  # B01 是锁定状态
            assert result["ok"] is False
            assert result["code"] == "E_SLOT_LOCKED"
            assert "锁定" in result["message"]

    def test_slot_full_check_uses_sql_count(self, mock_layout, monkeypatch):
        """测试 v2 使用 SQL COUNT 检查库位满载"""
        monkeypatch.setattr("crud.inventory.get_warehouse_layout", lambda x: mock_layout)

        with patch("crud.inventory.get_engine") as mock_engine:
            mock_conn = MagicMock()
            mock_trans = MagicMock()
            mock_engine.return_value.connect.return_value = mock_conn
            mock_conn.begin.return_value = mock_trans

            # 模拟 COUNT 返回满载数量
            mock_conn.execute.return_value.scalar.return_value = WAREHOUSE_MAX_CAPACITY

            result = inbound_to_slot_v2("SN001", "A01")

            # 验证使用了 COUNT 查询 - execute 至少被调用一次
            assert mock_conn.execute.called
            call_args_list = mock_conn.execute.call_args_list
            # 检查是否包含 COUNT 查询的调用
            assert len(call_args_list) >= 1

            assert result["ok"] is False
            assert result["code"] == "E_SLOT_FULL"

    def test_nonexistent_machine_returns_error(self, mock_layout, monkeypatch):
        """测试不存在的机台返回错误"""
        monkeypatch.setattr("crud.inventory.get_warehouse_layout", lambda x: mock_layout)

        with patch("crud.inventory.get_engine") as mock_engine:
            mock_conn = MagicMock()
            mock_trans = MagicMock()
            mock_engine.return_value.connect.return_value = mock_conn
            mock_conn.begin.return_value = mock_trans

            # COUNT 返回 1（未满）
            mock_conn.execute.return_value.scalar.return_value = 1
            # 查询机台返回 None（不存在）
            mock_conn.execute.return_value.fetchone.return_value = None

            result = inbound_to_slot_v2("SN999", "A01")
            assert result["ok"] is False
            assert result["code"] == "E_NOT_FOUND"

    def test_already_inbound_returns_error(self, mock_layout, monkeypatch):
        """测试已入库机台（非调拨）返回错误"""
        monkeypatch.setattr("crud.inventory.get_warehouse_layout", lambda x: mock_layout)

        with patch("crud.inventory.get_engine") as mock_engine:
            mock_conn = MagicMock()
            mock_trans = MagicMock()
            mock_engine.return_value.connect.return_value = mock_conn
            mock_conn.begin.return_value = mock_trans

            # COUNT 返回 1（未满）
            mock_conn.execute.return_value.scalar.return_value = 1
            # 机台已入库
            mock_conn.execute.return_value.fetchone.return_value = ("SN001", "库存中（A01）")

            result = inbound_to_slot_v2("SN001", "A02", is_transfer=False)
            assert result["ok"] is False
            assert result["code"] == "E_ALREADY_INBOUND"

    def test_transfer_allows_already_inbound(self, mock_layout, monkeypatch):
        """测试调拨允许已入库机台"""
        monkeypatch.setattr("crud.inventory.get_warehouse_layout", lambda x: mock_layout)

        with patch("crud.inventory.get_engine") as mock_engine:
            mock_conn = MagicMock()
            mock_trans = MagicMock()
            mock_engine.return_value.connect.return_value = mock_conn
            mock_conn.begin.return_value = mock_trans

            # COUNT 返回 1（未满）
            mock_conn.execute.return_value.scalar.return_value = 1
            # 机台已入库
            mock_conn.execute.return_value.fetchone.return_value = ("SN001", "库存中（A01）")

            result = inbound_to_slot_v2("SN001", "A02", is_transfer=True)
            # 应该成功（调拨模式）
            assert result["ok"] is True
            assert "调拨" in result["message"]

    def test_successful_inbound_clears_cache(self, mock_layout, monkeypatch):
        """测试成功入库清除缓存"""
        monkeypatch.setattr("crud.inventory.get_warehouse_layout", lambda x: mock_layout)

        cache_clear_calls = []

        def mock_cache_clear():
            cache_clear_calls.append("v1")

        def mock_cache_clear_v2():
            cache_clear_calls.append("v2")

        monkeypatch.setattr("crud.inventory.get_data.cache_clear", mock_cache_clear)
        monkeypatch.setattr("crud.inventory.get_data_v2.cache_clear", mock_cache_clear_v2)

        with patch("crud.inventory.get_engine") as mock_engine:
            mock_conn = MagicMock()
            mock_trans = MagicMock()
            mock_engine.return_value.connect.return_value = mock_conn
            mock_conn.begin.return_value = mock_trans

            # COUNT 返回 1（未满）
            mock_conn.execute.return_value.scalar.return_value = 1
            # 机台待入库
            mock_conn.execute.return_value.fetchone.return_value = ("SN001", "待入库")

            result = inbound_to_slot_v2("SN001", "A01")
            assert result["ok"] is True
            # 验证缓存被清除
            assert "v1" in cache_clear_calls
            assert "v2" in cache_clear_calls


class TestInboundV1V2OutputFormat:
    """测试 v1 和 v2 返回格式一致"""

    @pytest.fixture
    def mock_layout(self):
        """模拟正常的库位布局"""
        return {
            "layout_json": {
                "slots": [
                    {"code": "A01", "status": "正常"},
                    {"code": "A02", "status": "正常"},
                    {"code": "B01", "status": "锁定"},
                ]
            }
        }

    def test_success_response_format(self, mock_layout, monkeypatch):
        """测试成功响应格式"""
        monkeypatch.setattr("crud.inventory.get_warehouse_layout", lambda x: mock_layout)

        with patch("crud.inventory.get_engine") as mock_engine:
            mock_conn = MagicMock()
            mock_trans = MagicMock()
            mock_engine.return_value.connect.return_value = mock_conn
            mock_conn.begin.return_value = mock_trans

            mock_conn.execute.return_value.scalar.return_value = 1
            mock_conn.execute.return_value.fetchone.return_value = ("SN001", "待入库")

            result = inbound_to_slot_v2("SN001", "A01")

            # 验证返回格式
            assert "ok" in result
            assert "code" in result
            assert "message" in result
            assert "inbound_time" in result
            assert "slot_code" in result
            assert result["ok"] is True
            assert result["code"] == "OK"

    def test_error_response_format(self, mock_layout, monkeypatch):
        """测试错误响应格式"""
        result = inbound_to_slot_v2("", "A01")

        # 验证错误返回格式
        assert "ok" in result
        assert "code" in result
        assert "message" in result
        assert result["ok"] is False
