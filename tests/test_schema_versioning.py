"""
测试 Schema 版本控制功能
"""

import pytest
from datetime import datetime
from unittest.mock import patch, MagicMock

from database import (
    init_mysql_tables_v2,
    _ensure_schema_version_table,
    _get_current_schema_version,
    _record_schema_version,
    CURRENT_SCHEMA_VERSION,
)


class TestSchemaVersioning:
    """测试 Schema 版本控制功能"""

    def test_ensure_schema_version_table_creates_table(self):
        """测试确保版本表存在"""
        mock_conn = MagicMock()
        _ensure_schema_version_table(mock_conn)
        assert mock_conn.execute.called

    def test_get_current_schema_version_returns_zero_if_empty(self):
        """测试空数据库返回版本 0"""
        mock_conn = MagicMock()
        mock_conn.execute.return_value.scalar.return_value = None
        version = _get_current_schema_version(mock_conn)
        assert version == 0

    def test_get_current_schema_version_returns_max_version(self):
        """测试返回最大版本号"""
        mock_conn = MagicMock()
        mock_conn.execute.return_value.scalar.return_value = 5
        version = _get_current_schema_version(mock_conn)
        assert version == 5

    def test_record_schema_version_inserts_or_updates(self):
        """测试记录版本号"""
        mock_conn = MagicMock()
        _record_schema_version(mock_conn, 1, "Test migration")
        assert mock_conn.execute.called
        call_args = mock_conn.execute.call_args
        assert "ON DUPLICATE KEY UPDATE" in str(call_args[0][0])

    def test_init_v2_skips_if_already_up_to_date(self, monkeypatch):
        """测试已是最新版本时跳过初始化"""
        monkeypatch.setattr("database._get_current_schema_version", lambda conn: CURRENT_SCHEMA_VERSION)
        monkeypatch.setattr("database._ensure_schema_version_table", lambda conn: None)

        with patch("database.get_engine") as mock_engine:
            mock_conn = MagicMock()
            mock_engine.return_value.begin.return_value.__enter__ = lambda self: mock_conn
            mock_engine.return_value.begin.return_value.__exit__ = lambda self, *args: None

            result = init_mysql_tables_v2()

            assert result["initialized"] is False
            assert result["version"] == CURRENT_SCHEMA_VERSION
            assert "already up to date" in result["message"]

    def test_init_v2_performs_migration_when_needed(self, monkeypatch):
        """测试需要升级时执行迁移"""
        monkeypatch.setattr("database._get_current_schema_version", lambda conn: 0)
        monkeypatch.setattr("database._ensure_schema_version_table", lambda conn: None)
        monkeypatch.setattr("database._record_schema_version", lambda conn, v, d: None)

        with patch("database.get_engine") as mock_engine:
            mock_conn = MagicMock()
            mock_conn.execute.return_value.fetchone.return_value = [1]

            class MockContext:
                def __enter__(self):
                    return mock_conn
                def __exit__(self, *args):
                    return None

            mock_engine.return_value.begin.return_value = MockContext()

            result = init_mysql_tables_v2()

            assert result["initialized"] is True
            assert result["from_version"] == 0
            assert result["to_version"] == CURRENT_SCHEMA_VERSION

    def test_current_schema_version_is_positive(self):
        """测试当前版本号是正数"""
        assert CURRENT_SCHEMA_VERSION > 0
        assert isinstance(CURRENT_SCHEMA_VERSION, int)
