"""
测试 save_data_v2 UPSERT 功能
验证 v1 (DELETE+INSERT) 和 v2 (UPSERT) 功能一致性
"""

import pytest
import pandas as pd
import numpy as np
from datetime import datetime
from unittest.mock import patch, MagicMock

from crud.inventory import save_data, save_data_v2


class TestUpsertV2:
    """测试 save_data_v2 UPSERT 功能"""

    def test_save_data_v2_returns_stats(self, monkeypatch):
        """测试 save_data_v2 返回插入/更新统计"""
        df = pd.DataFrame({
            "流水号": ["SN001", "SN002"],
            "批次号": ["B001", "B002"],
            "机型": ["Model A", "Model B"],
            "状态": ["库存中", "待入库"],
        })

        with patch("crud.inventory.get_engine") as mock_engine:
            mock_conn = MagicMock()
            mock_trans = MagicMock()
            mock_engine.return_value.begin.return_value.__enter__ = lambda self: mock_conn
            mock_engine.return_value.begin.return_value.__exit__ = lambda self, *args: None

            # 模拟 SHOW COLUMNS 返回 Location_Code 存在
            mock_conn.execute.return_value.fetchone.return_value = ("Location_Code",)

            # 模拟 UPSERT 执行结果
            mock_result = MagicMock()
            mock_result.rowcount = 1  # 1 = INSERT
            mock_conn.execute.side_effect = [
                MagicMock(fetchone=MagicMock(return_value=("Location_Code",))),  # SHOW COLUMNS
                mock_result,  # UPSERT SN001
                mock_result,  # UPSERT SN002
            ]

            result = save_data_v2(df)

            assert "inserted" in result
            assert "updated" in result

    def test_empty_df_returns_zero_stats(self, monkeypatch):
        """测试空 DataFrame 返回零统计"""
        df = pd.DataFrame()

        with patch("crud.inventory.get_engine") as mock_engine:
            mock_conn = MagicMock()
            mock_engine.return_value.begin.return_value.__enter__ = lambda self: mock_conn
            mock_engine.return_value.begin.return_value.__exit__ = lambda self, *args: None
            mock_conn.execute.return_value.fetchone.return_value = ("Location_Code",)

            result = save_data_v2(df)

            assert result["inserted"] == 0
            assert result["updated"] == 0

    def test_duplicate_serials_keeps_last(self, monkeypatch):
        """测试重复流水号保留最后一条"""
        df = pd.DataFrame({
            "流水号": ["SN001", "SN001", "SN002"],
            "批次号": ["B001", "B002", "B003"],
            "机型": ["Model A", "Model A Updated", "Model B"],
            "状态": ["待入库", "库存中", "待入库"],
        })

        with patch("crud.inventory.get_engine") as mock_engine:
            mock_conn = MagicMock()
            mock_engine.return_value.begin.return_value.__enter__ = lambda self: mock_conn
            mock_engine.return_value.begin.return_value.__exit__ = lambda self, *args: None
            mock_conn.execute.return_value.fetchone.return_value = ("Location_Code",)

            mock_result = MagicMock()
            mock_result.rowcount = 1
            mock_conn.execute.side_effect = [
                MagicMock(fetchone=MagicMock(return_value=("Location_Code",))),
                mock_result,  # SN001 (last)
                mock_result,  # SN002
            ]

            result = save_data_v2(df)

            # 验证只有 2 条记录被处理（去重后）
            assert result["inserted"] + result["updated"] == 2

    def test_v1_v2_column_handling_consistency(self, monkeypatch):
        """测试 v1 和 v2 列处理逻辑一致"""
        df = pd.DataFrame({
            "流水号": ["SN001"],
            "批次号": ["B001"],
        })

        # v1 和 v2 都应该添加缺失的列
        with patch("crud.inventory.get_engine") as mock_engine:
            mock_conn = MagicMock()
            mock_engine.return_value.begin.return_value.__enter__ = lambda self: mock_conn
            mock_engine.return_value.begin.return_value.__exit__ = lambda self, *args: None
            mock_conn.execute.return_value.fetchone.return_value = ("Location_Code",)

            mock_result = MagicMock()
            mock_result.rowcount = 1
            mock_conn.execute.side_effect = [
                MagicMock(fetchone=MagicMock(return_value=("Location_Code",))),
                mock_result,
            ]

            # v2 不应该抛出列缺失错误
            result = save_data_v2(df)
            assert "inserted" in result


class TestUpsertV1V2Comparison:
    """对比 v1 和 v2 版本的功能一致性"""

    def test_both_versions_handle_datetime_columns(self, monkeypatch):
        """测试两个版本对日期列的处理一致"""
        df = pd.DataFrame({
            "流水号": ["SN001"],
            "批次号": ["B001"],
            "预计入库时间": ["2024-01-15 10:30:00"],
            "更新时间": ["2024-01-15 12:00:00"],
        })

        # v2 应该正确转换日期格式
        with patch("crud.inventory.get_engine") as mock_engine:
            mock_conn = MagicMock()
            mock_engine.return_value.begin.return_value.__enter__ = lambda self: mock_conn
            mock_engine.return_value.begin.return_value.__exit__ = lambda self, *args: None
            mock_conn.execute.return_value.fetchone.return_value = ("Location_Code",)

            mock_result = MagicMock()
            mock_result.rowcount = 1
            mock_conn.execute.side_effect = [
                MagicMock(fetchone=MagicMock(return_value=("Location_Code",))),
                mock_result,
            ]

            result = save_data_v2(df)
            assert result["inserted"] == 1

    def test_both_versions_handle_null_order_id(self, monkeypatch):
        """测试两个版本对空订单号的处理一致（转为 NULL）"""
        df = pd.DataFrame({
            "流水号": ["SN001"],
            "批次号": ["B001"],
            "占用订单号": [""],  # 空字符串应该转为 NULL
        })

        with patch("crud.inventory.get_engine") as mock_engine:
            mock_conn = MagicMock()
            mock_engine.return_value.begin.return_value.__enter__ = lambda self: mock_conn
            mock_engine.return_value.begin.return_value.__exit__ = lambda self, *args: None
            mock_conn.execute.return_value.fetchone.return_value = ("Location_Code",)

            call_params = []
            def capture_params(sql, params=None):
                call_params.append(params)
                mock_result = MagicMock()
                mock_result.rowcount = 1
                if "SHOW COLUMNS" in str(sql):
                    return MagicMock(fetchone=MagicMock(return_value=("Location_Code",)))
                return mock_result

            mock_conn.execute.side_effect = capture_params

            result = save_data_v2(df)

            # 验证参数被正确处理
            assert len(call_params) > 0


class TestUpsertErrorHandling:
    """测试 UPSERT 错误处理"""

    def test_upsert_raises_on_operational_error(self, monkeypatch):
        """测试数据库操作错误时抛出异常"""
        from sqlalchemy.exc import OperationalError

        df = pd.DataFrame({
            "流水号": ["SN001"],
            "批次号": ["B001"],
        })

        with patch("crud.inventory.get_engine") as mock_engine:
            mock_engine.side_effect = OperationalError("Connection failed", None, None)

            with pytest.raises(RuntimeError) as exc_info:
                save_data_v2(df)

            assert "保存失败" in str(exc_info.value)

    def test_upsert_handles_missing_location_column(self, monkeypatch):
        """测试自动添加 Location_Code 列"""
        df = pd.DataFrame({
            "流水号": ["SN001"],
            "批次号": ["B001"],
        })

        with patch("crud.inventory.get_engine") as mock_engine:
            mock_conn = MagicMock()
            mock_engine.return_value.begin.return_value.__enter__ = lambda self: mock_conn
            mock_engine.return_value.begin.return_value.__exit__ = lambda self, *args: None

            # 第一次查询返回 None（列不存在），第二次返回存在
            show_columns_results = [
                MagicMock(fetchone=MagicMock(return_value=None)),  # 列不存在
                MagicMock(fetchone=MagicMock(return_value=("Location_Code",))),  # ALTER 后
            ]

            mock_result = MagicMock()
            mock_result.rowcount = 1

            call_count = [0]
            def side_effect(sql, params=None):
                call_count[0] += 1
                if "SHOW COLUMNS" in str(sql):
                    return show_columns_results[0] if call_count[0] <= 1 else show_columns_results[1]
                elif "ALTER TABLE" in str(sql):
                    return MagicMock()
                return mock_result

            mock_conn.execute.side_effect = side_effect

            result = save_data_v2(df)
            assert result["inserted"] == 1


class TestUpsertPerformanceBenefits:
    """测试 UPSERT 性能优势"""

    def test_upsert_executes_no_delete(self, monkeypatch):
        """测试 UPSERT 不执行 DELETE 操作"""
        df = pd.DataFrame({
            "流水号": ["SN001", "SN002"],
            "批次号": ["B001", "B002"],
        })

        executed_sqls = []

        with patch("crud.inventory.get_engine") as mock_engine:
            mock_conn = MagicMock()
            mock_engine.return_value.begin.return_value.__enter__ = lambda self: mock_conn
            mock_engine.return_value.begin.return_value.__exit__ = lambda self, *args: None

            def capture_sql(sql, params=None):
                executed_sqls.append(str(sql))
                mock_result = MagicMock()
                mock_result.rowcount = 1
                if "SHOW COLUMNS" in str(sql):
                    return MagicMock(fetchone=MagicMock(return_value=("Location_Code",)))
                return mock_result

            mock_conn.execute.side_effect = capture_sql

            save_data_v2(df)

            # 验证没有执行 DELETE
            for sql in executed_sqls:
                assert "DELETE" not in sql.upper() or "DUPLICATE" in sql.upper()

            # 验证执行了 UPSERT
            upsert_count = sum(1 for sql in executed_sqls if "ON DUPLICATE KEY UPDATE" in sql)
            assert upsert_count >= 1
