"""
缩略图磁盘缓存管理工具
"""

import os
import logging
import shutil
from datetime import datetime, timedelta
from pathlib import Path

from config import THUMBNAIL_CACHE_MAX_AGE_DAYS, MACHINE_ARCHIVE_ABS_DIR

logger = logging.getLogger(__name__)


def cleanup_thumbnail_cache(max_age_days: int = None, dry_run: bool = False) -> dict:
    """
    清理过期的缩略图缓存

    Args:
        max_age_days: 缓存最大保留天数（默认使用配置）
        dry_run: 如果为 True，只返回统计信息不实际删除

    Returns:
        {"deleted": 删除数量, "freed_bytes": 释放字节数}
    """
    if max_age_days is None:
        max_age_days = THUMBNAIL_CACHE_MAX_AGE_DAYS

    cutoff_time = datetime.now() - timedelta(days=max_age_days)
    deleted_count = 0
    freed_bytes = 0

    if not os.path.exists(MACHINE_ARCHIVE_ABS_DIR):
        return {"deleted": 0, "freed_bytes": 0}

    for sn_dir in Path(MACHINE_ARCHIVE_ABS_DIR).iterdir():
        if not sn_dir.is_dir():
            continue

        thumb_dir = sn_dir / ".thumbs"
        if not thumb_dir.exists():
            continue

        for thumb_file in thumb_dir.iterdir():
            if not thumb_file.is_file():
                continue

            try:
                file_mtime = datetime.fromtimestamp(thumb_file.stat().st_mtime)
                if file_mtime < cutoff_time:
                    file_size = thumb_file.stat().st_size
                    if not dry_run:
                        thumb_file.unlink()
                    deleted_count += 1
                    freed_bytes += file_size
            except Exception as e:
                logger.warning(f"Failed to process thumbnail {thumb_file}: {e}")

        # 如果 thumbs 目录为空，删除目录
        if not dry_run and thumb_dir.exists() and not any(thumb_dir.iterdir()):
            try:
                thumb_dir.rmdir()
            except Exception:
                pass

    return {"deleted": deleted_count, "freed_bytes": freed_bytes}


def invalidate_thumbnail_cache(serial_no: str = None, file_name: str = None) -> bool:
    """
    使特定缩略图缓存失效

    Args:
        serial_no: 机台流水号，如果为 None 则清理全部
        file_name: 文件名，如果为 None 则清理该机台全部

    Returns:
        是否成功删除
    """
    try:
        if serial_no is None:
            # 清理全部缓存
            for sn_dir in Path(MACHINE_ARCHIVE_ABS_DIR).iterdir():
                if sn_dir.is_dir():
                    thumb_dir = sn_dir / ".thumbs"
                    if thumb_dir.exists():
                        shutil.rmtree(thumb_dir)
            return True

        sn_dir = Path(MACHINE_ARCHIVE_ABS_DIR) / serial_no
        thumb_dir = sn_dir / ".thumbs"

        if not thumb_dir.exists():
            return True

        if file_name is None:
            # 清理该机台全部缓存
            shutil.rmtree(thumb_dir)
            return True

        # 清理特定文件缓存
        thumb_path = thumb_dir / f"{file_name}.thumb.jpg"
        if thumb_path.exists():
            thumb_path.unlink()
            return True

        return True
    except Exception as e:
        logger.error(f"Failed to invalidate thumbnail cache: {e}")
        return False


def get_thumbnail_cache_stats() -> dict:
    """
    获取缩略图缓存统计信息
    """
    stats = {
        "total_files": 0,
        "total_bytes": 0,
        "oldest_file": None,
        "newest_file": None,
    }

    if not os.path.exists(MACHINE_ARCHIVE_ABS_DIR):
        return stats

    oldest_time = None
    newest_time = None

    for sn_dir in Path(MACHINE_ARCHIVE_ABS_DIR).iterdir():
        if not sn_dir.is_dir():
            continue

        thumb_dir = sn_dir / ".thumbs"
        if not thumb_dir.exists():
            continue

        for thumb_file in thumb_dir.iterdir():
            if not thumb_file.is_file():
                continue

            stats["total_files"] += 1
            stats["total_bytes"] += thumb_file.stat().st_size

            mtime = thumb_file.stat().st_mtime
            if oldest_time is None or mtime < oldest_time:
                oldest_time = mtime
            if newest_time is None or mtime > newest_time:
                newest_time = mtime

    if oldest_time:
        stats["oldest_file"] = datetime.fromtimestamp(oldest_time).isoformat()
    if newest_time:
        stats["newest_file"] = datetime.fromtimestamp(newest_time).isoformat()

    return stats
