from __future__ import annotations

import asyncio
import logging
import os
from contextlib import contextmanager
from datetime import date, datetime
from typing import Any, Iterator
from zoneinfo import ZoneInfo

from sqlalchemy import text

from database import get_engine
from crud.cloud_sync_outbox import (
    enqueue_cloud_sync_event,
    get_cloud_sync_status,
    process_due_cloud_sync_events,
    supersede_pending_cloud_sync_events,
)

from .config import V8SyncConfig, get_config
from .snapshot_builder import build_snapshot
from .snapshot_store import get_snapshot, list_snapshots, save_snapshot

logger = logging.getLogger(__name__)
LOCK_NAME = "v8_repair_daily_snapshot"


def _today(config: V8SyncConfig) -> date:
    try:
        return datetime.now(ZoneInfo(config.timezone)).date()
    except Exception:
        return datetime.now().date()


def business_key(business_date: date) -> str:
    return f"repair_snapshot:{business_date.isoformat()}"


def event_id(business_date: date) -> str:
    return f"v8-repair-snapshot-{business_date.strftime('%Y%m%d')}"


def revision_event_id(business_date: date, payload_sha256: str) -> str:
    return f"{event_id(business_date)}-{payload_sha256[:16]}"


@contextmanager
def advisory_lock(lock_name: str = LOCK_NAME) -> Iterator[bool]:
    # MySQL advisory locks belong to a connection, so keep this connection open
    # for the entire critical section.
    with get_engine().connect() as conn:
        acquired = bool(conn.execute(text("SELECT GET_LOCK(:lock_name, 0)"), {"lock_name": lock_name}).scalar())
        try:
            yield acquired
        finally:
            if acquired:
                conn.execute(text("SELECT RELEASE_LOCK(:lock_name)"), {"lock_name": lock_name})


def run_snapshot(
    business_date: date | None = None,
    *,
    dry_run: bool = False,
    config: V8SyncConfig | None = None,
) -> dict[str, Any]:
    config = config or get_config()
    target_date = business_date or _today(config)
    if dry_run:
        payload = build_snapshot(target_date, config=config)
        return {"status": "dry_run", "payload": payload}
    payload = build_snapshot(target_date, config=config)
    stored = save_snapshot(payload, replace_existing=True)
    status = "changed" if stored.get("replaced") else ("created" if stored.get("created") else "existing")
    return {"status": status, "snapshot": stored, "payload": payload}


def run_daily(
    business_date: date | None = None,
    *,
    config: V8SyncConfig | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    config = config or get_config()
    target_date = business_date or _today(config)
    if dry_run:
        return run_snapshot(target_date, dry_run=True, config=config)
    with advisory_lock() as acquired:
        if not acquired:
            return {"status": "locked", "business_date": target_date.isoformat()}
        result = run_snapshot(target_date, config=config)
        payload = result.get("payload") or {}
        stored = result.get("snapshot") or {}
        if config.enabled and payload:
            if result.get("status") == "changed":
                supersede_pending_cloud_sync_events("repair_snapshot_sync", business_key(target_date))
            needs_new_event = result.get("status") == "changed" or stored.get("status") in {"failed", "rejected"}
            result["event_id"] = enqueue_snapshot_event(
                target_date,
                str(stored.get("snapshot_id") or payload["snapshotId"]),
                str(stored.get("payload_sha256") or ""),
                revision=True,
            )
        return result


def enqueue_snapshot_event(
    business_date: date,
    snapshot_id: str,
    payload_sha256: str | None,
    *,
    revision: bool = False,
) -> str:
    digest = str(payload_sha256 or "")
    return enqueue_cloud_sync_event(
        "repair_snapshot_sync",
        business_key(business_date),
        {"snapshot_id": snapshot_id, "payload_sha256": digest},
        event_id=revision_event_id(business_date, digest) if revision else event_id(business_date),
    )


def send_pending(limit: int = 20) -> dict[str, Any]:
    return process_due_cloud_sync_events(limit=limit)


def _sync_interval_seconds() -> int:
    """快照生成间隔，默认 1 小时，最小 5 分钟，避免过度扫描。"""
    raw = os.getenv("V8_SYNC_INTERVAL_SECONDS") or os.getenv("REPAIR_SYNC_INTERVAL_SECONDS") or ""
    try:
        return max(300, int(str(raw).strip()))
    except (TypeError, ValueError):
        return 3600


async def run_sync_loop(config: V8SyncConfig | None = None) -> None:
    """周期性生成快照并入队。

    这是「只推一次就停」的修复：此前只有启动钩子会触发同步，
    进程长期不重启时，发货日期变化永远不会上传。
    """
    active_config = config or get_config()
    if os.getenv("V8_DEMO_MODE") == "1":
        logger.info("V8 sync loop skipped in demo mode")
        return
    if not active_config.enabled:
        logger.info("V8 sync loop skipped because V8_SYNC_ENABLED is false")
        return
    interval = _sync_interval_seconds()
    logger.info("V8 sync loop started, interval=%ss", interval)
    while True:
        try:
            result = await asyncio.to_thread(run_daily, config=active_config)
            logger.info(
                "V8 sync loop iteration status=%s event_id=%s",
                result.get("status"), result.get("event_id", ""),
            )
        except asyncio.CancelledError:
            logger.info("V8 sync loop cancelled")
            raise
        except Exception:
            logger.exception("V8 sync loop iteration failed")
        await asyncio.sleep(interval)


async def run_startup_sync(config: V8SyncConfig | None = None) -> dict[str, Any]:
    """Build and enqueue one idempotent snapshot when the V8 process starts."""
    active_config = config or get_config()
    if os.getenv("V8_DEMO_MODE") == "1":
        logger.info("V8 sync bridge startup sync skipped in demo mode")
        return {"status": "demo_disabled"}
    if not active_config.enabled:
        logger.info("V8 sync bridge startup sync skipped because V8_SYNC_ENABLED is false")
        return {"status": "disabled"}
    from .client import verify_config

    readiness = verify_config(active_config)
    if not readiness.get("upload_ready"):
        logger.warning("V8 sync bridge not started: %s", readiness.get("error", "invalid configuration"))
        return {"status": "not_configured"}
    try:
        result = await asyncio.to_thread(run_daily, config=active_config)
    except Exception:
        logger.exception("V8 sync bridge startup sync failed")
        return {"status": "failed"}
    logger.info(
        "V8 sync bridge startup sync status=%s event_id=%s",
        result.get("status"), result.get("event_id", ""),
    )
    return result


def status(limit: int = 20) -> dict[str, Any]:
    return {"snapshots": list_snapshots(limit), "outbox": get_cloud_sync_status(limit)}
