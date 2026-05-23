from __future__ import annotations

import asyncio
import json
import logging
import uuid
from datetime import date, datetime
from typing import Any

from sqlalchemy import text

from database import get_engine

logger = logging.getLogger(__name__)

SYNC_EVENT_TYPES = {
    "dealer_order_reviewed",
    "dealer_order_contracted",
    "dealer_order_allocated",
    "dealer_order_completed",
    "wechat_batch_summary_sync",
}

POLL_INTERVAL_SECONDS = 5


def _json_default(value: Any) -> str:
    if isinstance(value, datetime):
        return value.strftime("%Y-%m-%d %H:%M:%S")
    if isinstance(value, date):
        return value.strftime("%Y-%m-%d")
    return str(value)


_outbox_table_ensured = False


def ensure_cloud_sync_outbox_table() -> None:
    global _outbox_table_ensured
    if _outbox_table_ensured:
        return
    with get_engine().begin() as conn:
        conn.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS cloud_sync_outbox (
                  id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
                  event_id VARCHAR(64) NOT NULL,
                  event_type VARCHAR(64) NOT NULL,
                  biz_key VARCHAR(128) NOT NULL DEFAULT '',
                  payload_json LONGTEXT NOT NULL,
                  status VARCHAR(32) NOT NULL DEFAULT 'pending',
                  retry_count INT NOT NULL DEFAULT 0,
                  last_error TEXT NULL,
                  next_retry_at DATETIME NULL,
                  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                  updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                  synced_at DATETIME NULL,
                  UNIQUE KEY uq_cloud_sync_event_id (event_id),
                  INDEX idx_cloud_sync_status_retry (status, next_retry_at, id),
                  INDEX idx_cloud_sync_biz_key (biz_key),
                  INDEX idx_cloud_sync_event_type (event_type)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
                """
            )
        )
    _outbox_table_ensured = True


def enqueue_cloud_sync_event(
    event_type: str,
    biz_key: str,
    payload: dict[str, Any] | None = None,
    event_id: str | None = None,
) -> str:
    if event_type not in SYNC_EVENT_TYPES:
        raise ValueError(f"unsupported cloud sync event_type: {event_type}")
    ensure_cloud_sync_outbox_table()
    eid = (event_id or f"v8-outbox-{event_type}-{uuid.uuid4().hex}").strip()
    payload_json = json.dumps(payload or {}, ensure_ascii=False, default=_json_default)
    with get_engine().begin() as conn:
        insert_cloud_sync_event(conn, eid, event_type, biz_key, payload_json)
    return eid


def insert_cloud_sync_event(conn: Any, event_id: str, event_type: str, biz_key: str, payload_json: str) -> None:
    conn.execute(
        text(
            """
            INSERT INTO cloud_sync_outbox
              (event_id, event_type, biz_key, payload_json, status, retry_count, next_retry_at)
            VALUES
              (:event_id, :event_type, :biz_key, :payload_json, 'pending', 0, NULL)
            ON DUPLICATE KEY UPDATE
              event_type=VALUES(event_type),
              biz_key=VALUES(biz_key),
              payload_json=VALUES(payload_json),
              status=IF(status='synced', status, 'pending'),
              last_error=NULL,
              next_retry_at=NULL
            """
        ),
        {
            "event_id": event_id,
            "event_type": event_type,
            "biz_key": str(biz_key or "").strip(),
            "payload_json": payload_json,
        },
    )


def enqueue_wechat_batch_summary_sync(reason: str = "") -> str:
    return enqueue_cloud_sync_event(
        "wechat_batch_summary_sync",
        "wechat_batch_summary",
        {"reason": str(reason or "").strip()},
    )


def _retry_delay_sql(next_retry_number: int) -> str:
    if next_retry_number <= 1:
        return "DATE_ADD(NOW(), INTERVAL 30 SECOND)"
    if next_retry_number == 2:
        return "DATE_ADD(NOW(), INTERVAL 2 MINUTE)"
    if next_retry_number == 3:
        return "DATE_ADD(NOW(), INTERVAL 5 MINUTE)"
    return "DATE_ADD(NOW(), INTERVAL 10 MINUTE)"


def _load_due_event() -> dict[str, Any] | None:
    ensure_cloud_sync_outbox_table()
    with get_engine().begin() as conn:
        row = conn.execute(
            text(
                """
                SELECT id, event_id, event_type, biz_key, payload_json, retry_count
                FROM cloud_sync_outbox
                WHERE
                  status='pending'
                  OR (status='failed' AND (next_retry_at IS NULL OR next_retry_at <= NOW()))
                  OR (status='processing' AND updated_at < DATE_SUB(NOW(), INTERVAL 10 MINUTE))
                ORDER BY id
                LIMIT 1
                """
            )
        ).mappings().first()
        if not row:
            return None
        updated = conn.execute(
            text(
                """
                UPDATE cloud_sync_outbox
                SET status='processing', last_error=NULL
                WHERE id=:id AND status IN ('pending', 'failed', 'processing')
                """
            ),
            {"id": row["id"]},
        ).rowcount
        if not updated:
            return None
        payload: dict[str, Any]
        try:
            payload = json.loads(row["payload_json"] or "{}")
            if not isinstance(payload, dict):
                payload = {}
        except json.JSONDecodeError:
            payload = {}
        return {**dict(row), "payload": payload}


def _mark_synced(event_id: str) -> None:
    with get_engine().begin() as conn:
        conn.execute(
            text(
                """
                UPDATE cloud_sync_outbox
                SET status='synced', last_error=NULL, next_retry_at=NULL, synced_at=NOW()
                WHERE event_id=:event_id
                """
            ),
            {"event_id": event_id},
        )


def _mark_failed(event_id: str, error: str) -> None:
    with get_engine().begin() as conn:
        retry_count = int(
            conn.execute(
                text("SELECT retry_count FROM cloud_sync_outbox WHERE event_id=:event_id"),
                {"event_id": event_id},
            ).scalar()
            or 0
        )
        next_retry = retry_count + 1
        conn.execute(
            text(
                f"""
                UPDATE cloud_sync_outbox
                SET status='failed',
                    retry_count=retry_count+1,
                    last_error=:last_error,
                    next_retry_at={_retry_delay_sql(next_retry)}
                WHERE event_id=:event_id
                """
            ),
            {"event_id": event_id, "last_error": str(error or "")[:4000]},
        )


def process_next_cloud_sync_event() -> dict[str, Any] | None:
    event = _load_due_event()
    if not event:
        return None
    event_id = str(event["event_id"])
    try:
        _dispatch_event(event)
        _mark_synced(event_id)
        return {"event_id": event_id, "status": "synced"}
    except Exception as exc:
        _mark_failed(event_id, str(exc))
        logger.warning("cloud sync event failed: %s %s", event_id, exc)
        return {"event_id": event_id, "status": "failed", "error": str(exc)}


def process_due_cloud_sync_events(limit: int = 20) -> dict[str, Any]:
    processed = 0
    synced = 0
    failed = 0
    for _ in range(max(1, int(limit or 20))):
        result = process_next_cloud_sync_event()
        if not result:
            break
        processed += 1
        if result.get("status") == "synced":
            synced += 1
        else:
            failed += 1
    return {"processed": processed, "synced": synced, "failed": failed}


def _dispatch_event(event: dict[str, Any]) -> None:
    from crud.cloud_dealer_order_sync import (
        fetch_local_wechat_batch_summary,
        push_cloud_allocate,
        push_cloud_completed_state,
        push_cloud_contract,
        push_cloud_review,
        push_wechat_batch_summary_to_cloud,
        refresh_local_wechat_batch_summary,
    )

    payload = event.get("payload") or {}
    event_id = str(event.get("event_id") or "")
    event_type = str(event.get("event_type") or "")
    order_no = str(payload.get("order_no") or event.get("biz_key") or "").strip()

    if event_type == "dealer_order_reviewed":
        push_cloud_review(
            order_no,
            str(payload.get("status") or ""),
            reviewer=str(payload.get("reviewer") or payload.get("reviewed_by") or "system"),
            note=str(payload.get("note") or payload.get("review_note") or ""),
            factory_pending=payload.get("factory_pending") if "factory_pending" in payload else None,
            idempotency_key=event_id,
        )
        return

    if event_type == "dealer_order_contracted":
        push_cloud_contract(
            order_no,
            contract_no=str(payload.get("contract_no") or ""),
            operator=str(payload.get("operator") or "system"),
            v7_order_no=str(payload.get("v7_order_no") or ""),
            idempotency_key=event_id,
        )
        return

    if event_type == "dealer_order_allocated":
        push_cloud_allocate(
            order_no,
            contract_no=str(payload.get("contract_no") or ""),
            operator=str(payload.get("operator") or "system"),
            v7_order_no=str(payload.get("v7_order_no") or ""),
            idempotency_key=event_id,
        )
        return

    if event_type == "dealer_order_completed":
        push_cloud_completed_state(
            order_no,
            contract_no=str(payload.get("contract_no") or ""),
            operator=str(payload.get("operator") or "system"),
            v7_order_no=str(payload.get("v7_order_no") or ""),
            idempotency_key_prefix=event_id,
        )
        return

    if event_type == "wechat_batch_summary_sync":
        refresh_local_wechat_batch_summary()
        rows = fetch_local_wechat_batch_summary()
        push_wechat_batch_summary_to_cloud(rows, idempotency_key=event_id)
        return

    raise ValueError(f"unsupported cloud sync event_type: {event_type}")


def get_cloud_sync_status(limit: int = 5) -> dict[str, Any]:
    ensure_cloud_sync_outbox_table()
    limit = min(max(1, int(limit or 5)), 20)
    with get_engine().begin() as conn:
        pending = int(
            conn.execute(text("SELECT COUNT(*) FROM cloud_sync_outbox WHERE status IN ('pending', 'processing')")).scalar()
            or 0
        )
        failed = int(conn.execute(text("SELECT COUNT(*) FROM cloud_sync_outbox WHERE status='failed'")).scalar() or 0)
        rows = conn.execute(
            text(
                """
                SELECT id, event_id, event_type, biz_key, status, retry_count, last_error, next_retry_at, updated_at
                FROM cloud_sync_outbox
                WHERE status='failed'
                ORDER BY updated_at DESC, id DESC
                LIMIT :limit
                """
            ),
            {"limit": limit},
        ).mappings().all()
    return {
        "pending": pending,
        "failed": failed,
        "recent_failed": [
            {key: _json_default(value) if isinstance(value, (datetime, date)) else value for key, value in row.items()}
            for row in rows
        ],
    }


def retry_failed_cloud_sync_events() -> dict[str, Any]:
    ensure_cloud_sync_outbox_table()
    with get_engine().begin() as conn:
        count = conn.execute(
            text(
                """
                UPDATE cloud_sync_outbox
                SET status='pending', next_retry_at=NULL, last_error=NULL
                WHERE status='failed'
                """
            )
        ).rowcount
    return {"queued": int(count or 0)}


async def cloud_sync_worker_loop() -> None:
    ensure_cloud_sync_outbox_table()
    logger.info("cloud sync worker started")
    while True:
        try:
            await asyncio.to_thread(process_due_cloud_sync_events, 20)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.warning("cloud sync worker tick failed: %s", exc)
        await asyncio.sleep(POLL_INTERVAL_SECONDS)
