"""
测试缩略图磁盘缓存功能
"""

import os
import pytest
import tempfile
import shutil
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch

from utils.thumbnail_cache import (
    cleanup_thumbnail_cache,
    invalidate_thumbnail_cache,
    get_thumbnail_cache_stats,
)


class TestThumbnailCache:
    """测试缩略图缓存管理"""

    @pytest.fixture
    def temp_archive_dir(self):
        """创建临时机台档案目录"""
        temp = tempfile.mkdtemp()
        yield temp
        shutil.rmtree(temp, ignore_errors=True)

    def test_cleanup_deletes_old_files(self, temp_archive_dir, monkeypatch):
        """测试清理删除过期文件"""
        monkeypatch.setattr("utils.thumbnail_cache.MACHINE_ARCHIVE_ABS_DIR", temp_archive_dir)

        # 创建测试目录结构
        sn_dir = Path(temp_archive_dir) / "SN001"
        thumb_dir = sn_dir / ".thumbs"
        thumb_dir.mkdir(parents=True)

        # 创建一个旧文件（10天前）
        old_file = thumb_dir / "old.jpg.thumb.jpg"
        old_file.write_text("old content")
        old_time = (datetime.now() - timedelta(days=10)).timestamp()
        os.utime(old_file, (old_time, old_time))

        # 创建一个新文件（1天前）
        new_file = thumb_dir / "new.jpg.thumb.jpg"
        new_file.write_text("new content")
        new_time = (datetime.now() - timedelta(days=1)).timestamp()
        os.utime(new_file, (new_time, new_time))

        # 执行清理（7天过期）
        result = cleanup_thumbnail_cache(max_age_days=7)

        # 验证只删除了旧文件
        assert result["deleted"] == 1
        assert not old_file.exists()
        assert new_file.exists()

    def test_cleanup_dry_run(self, temp_archive_dir, monkeypatch):
        """测试 dry_run 模式不实际删除"""
        monkeypatch.setattr("utils.thumbnail_cache.MACHINE_ARCHIVE_ABS_DIR", temp_archive_dir)

        sn_dir = Path(temp_archive_dir) / "SN001"
        thumb_dir = sn_dir / ".thumbs"
        thumb_dir.mkdir(parents=True)

        old_file = thumb_dir / "old.jpg.thumb.jpg"
        old_file.write_text("old content")
        old_time = (datetime.now() - timedelta(days=10)).timestamp()
        os.utime(old_file, (old_time, old_time))

        # dry_run 模式
        result = cleanup_thumbnail_cache(max_age_days=7, dry_run=True)

        # 验证文件仍然存在
        assert result["deleted"] == 1
        assert old_file.exists()

    def test_invalidate_specific_file(self, temp_archive_dir, monkeypatch):
        """测试使特定文件缓存失效"""
        monkeypatch.setattr("utils.thumbnail_cache.MACHINE_ARCHIVE_ABS_DIR", temp_archive_dir)

        sn_dir = Path(temp_archive_dir) / "SN001"
        thumb_dir = sn_dir / ".thumbs"
        thumb_dir.mkdir(parents=True)

        file1 = thumb_dir / "file1.jpg.thumb.jpg"
        file1.write_text("content1")
        file2 = thumb_dir / "file2.jpg.thumb.jpg"
        file2.write_text("content2")

        # 删除 file1 的缓存
        result = invalidate_thumbnail_cache("SN001", "file1.jpg")
        assert result is True
        assert not file1.exists()
        assert file2.exists()

    def test_invalidate_serial_no_all(self, temp_archive_dir, monkeypatch):
        """测试使机台全部缓存失效"""
        monkeypatch.setattr("utils.thumbnail_cache.MACHINE_ARCHIVE_ABS_DIR", temp_archive_dir)

        sn_dir = Path(temp_archive_dir) / "SN001"
        thumb_dir = sn_dir / ".thumbs"
        thumb_dir.mkdir(parents=True)

        file1 = thumb_dir / "file1.jpg.thumb.jpg"
        file1.write_text("content1")
        file2 = thumb_dir / "file2.jpg.thumb.jpg"
        file2.write_text("content2")

        # 删除 SN001 的全部缓存
        result = invalidate_thumbnail_cache("SN001")
        assert result is True
        assert not thumb_dir.exists()

    def test_get_stats(self, temp_archive_dir, monkeypatch):
        """测试获取缓存统计信息"""
        monkeypatch.setattr("utils.thumbnail_cache.MACHINE_ARCHIVE_ABS_DIR", temp_archive_dir)

        sn_dir = Path(temp_archive_dir) / "SN001"
        thumb_dir = sn_dir / ".thumbs"
        thumb_dir.mkdir(parents=True)

        file1 = thumb_dir / "file1.jpg.thumb.jpg"
        file1.write_text("content1")
        file2 = thumb_dir / "file2.jpg.thumb.jpg"
        file2.write_text("content2")

        stats = get_thumbnail_cache_stats()

        assert stats["total_files"] == 2
        assert stats["total_bytes"] == len("content1") + len("content2")
        assert stats["oldest_file"] is not None
        assert stats["newest_file"] is not None

    def test_get_stats_empty(self, temp_archive_dir, monkeypatch):
        """测试空缓存统计"""
        monkeypatch.setattr("utils.thumbnail_cache.MACHINE_ARCHIVE_ABS_DIR", temp_archive_dir)

        stats = get_thumbnail_cache_stats()

        assert stats["total_files"] == 0
        assert stats["total_bytes"] == 0
        assert stats["oldest_file"] is None
        assert stats["newest_file"] is None
