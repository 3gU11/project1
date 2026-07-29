from __future__ import annotations

import logging
from contextlib import contextmanager
from datetime import date, datetime
from typing import Any, Iterator
from zoneinfo import ZoneInfo

from sqlalchemy import text

from database import get_engine
from crud.cloud_sync_outbox import enqueue_cloud_sync_event, get_cloud_sync_status, process_due_cloud_sync_events

from .config import RepairSyncConfig, get_config
from .snapshot_builder import build_snapshot
from .snapshot_store import get_snapshot, list_snapshots, save_snapshot

logger = logging.getLogger(__name__)
LOCK_NAME = "v8_repair_daily_snapshot"


def _today(config: RepairSyncConfig) -> date:
    try:
        return datetime.now(ZoneInfo(config.timezone)).date()
    except Exception:
        return datetime.now().date()


def business_key(business_date: date) -> str:
    return f"repair_snapshot:{business_date.isoformat()}"


def event_id(business_date: date) -> str:
    return f"v8-repair-snapshot-{business_date.strftime('%Y%m%d')}"


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
    config: RepairSyncConfig | None = None,
) -> dict[str, Any]:
    config = config or get_config()
    target_date = business_date or _today(config)
    if dry_run:
        payload = build_snapshot(target_date, config=config)
        return {"status": "dry_run", "payload": payload}
    existing = get_snapshot(business_date=target_date)
    if existing:
        return {"status": "existing", "snapshot": existing}
    payload = build_snapshot(target_date, config=config)
    stored = save_snapshot(payload)
    return {"status": "created", "snapshot": stored, "payload": payload}


def run_daily(
    business_date: date | None = None,
    *,
    config: RepairSyncConfig | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    config = config or get_config()
    target_date = business_date or _today(config)
    if dry_run:
        return run_snapshot(target_date, dry_run=True, config=config)
    existing = get_snapshot(business_date=target_date)
    if existing:
        result: dict[str, Any] = {"status": "existing", "snapshot": existing}
        if config.enabled and existing.get("status") != "uploaded":
            result["event_id"] = enqueue_snapshot_event(target_date, existing["snapshot_id"], existing.get("payload_sha256"))
        return result
    with advisory_lock() as acquired:
        if not acquired:
            return {"status": "locked", "business_date": target_date.isoformat()}
        result = run_snapshot(target_date, config=config)
        payload = result.get("payload") or {}
        stored = result.get("snapshot") or {}
        if config.enabled and payload:
            result["event_id"] = enqueue_snapshot_event(
                target_date,
                str(stored.get("snapshot_id") or payload["snapshotId"]),
                str(stored.get("payload_sha256") or ""),
            )
        return result


def enqueue_snapshot_event(business_date: date, snapshot_id: str, payload_sha256: str | None) -> str:
    return enqueue_cloud_sync_event(
        "repair_snapshot_sync",
        business_key(business_date),
        {"snapshot_id": snapshot_id, "payload_sha256": payload_sha256 or ""},
        event_id=event_id(business_date),
    )


def send_pending(limit: int = 20) -> dict[str, Any]:
    return process_due_cloud_sync_events(limit=limit)


def status(limit: int = 20) -> dict[str, Any]:
    return {"snapshots": list_snapshots(limit), "outbox": get_cloud_sync_status(limit)}
