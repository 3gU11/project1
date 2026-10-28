from __future__ import annotations

import asyncio
import json
import logging
import os
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
    "dealer_order_cancelled",
    "dealer_order_completed",
    "wechat_batch_summary_sync",
    "repair_snapshot_sync",
    "repair_delta_event_sync",
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
                  event_id VARCHAR(128) NOT NULL,
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
        row = conn.execute(
            text(
                """
                SELECT CHARACTER_MAXIMUM_LENGTH
                FROM INFORMATION_SCHEMA.COLUMNS
                WHERE TABLE_SCHEMA = DATABASE()
                  AND TABLE_NAME = 'cloud_sync_outbox'
                  AND COLUMN_NAME = 'event_id'
                """
            )
        ).first()
        current_len = int(row[0] or 0) if row else 0
        if current_len < 128:
            conn.execute(text("ALTER TABLE cloud_sync_outbox MODIFY COLUMN event_id VARCHAR(128) NOT NULL"))
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
              event_type=IF(status='synced', event_type, VALUES(event_type)),
              biz_key=IF(status='synced', biz_key, VALUES(biz_key)),
              payload_json=IF(status='synced', payload_json, VALUES(payload_json)),
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


def supersede_pending_cloud_sync_events(event_type: str, biz_key: str) -> int:
    ensure_cloud_sync_outbox_table()
    with get_engine().begin() as conn:
        result = conn.execute(
            text(
                """
                UPDATE cloud_sync_outbox
                SET status='superseded', last_error='replaced by a newer snapshot',
                    updated_at=CURRENT_TIMESTAMP
                WHERE event_type=:event_type AND biz_key=:biz_key
                  AND status IN ('pending', 'failed')
                """
            ),
            {"event_type": event_type, "biz_key": biz_key},
        )
    return int(result.rowcount or 0)


def supersede_pending_order_sync_events(
    conn: Any,
    order_no: str,
    *,
    reason: str = "superseded by newer terminal event",
) -> int:
    """作废同一订单尚未发送的 dealer_order_* 事件。

    由调用方事务保证：在入队取消/终态事件之前调用，把该订单所有 pending/failed 的
    旧回传事件置为 superseded，避免退避重试中的旧事件晚到又把云端状态覆盖回旧值。
    传入的 conn 必须是调用方已开启的事务连接（本函数不新开事务、不负责建表）。
    """
    order_no = str(order_no or "").strip()
    if not order_no:
        return 0
    result = conn.execute(
        text(
            """
            UPDATE cloud_sync_outbox
            SET status='superseded', last_error=:reason, updated_at=CURRENT_TIMESTAMP
            WHERE biz_key=:order_no
              AND event_type LIKE 'dealer_order_%'
              AND status IN ('pending', 'failed')
            """
        ),
        {"order_no": order_no, "reason": str(reason or "")[:4000]},
    )
    return int(result.rowcount or 0)


def enqueue_wechat_batch_summary_sync(reason: str = "") -> str:
    return enqueue_cloud_sync_event(
        "wechat_batch_summary_sync",
        "wechat_batch_summary",
        {"reason": str(reason or "").strip()},
    )


def _retry_delay_sql(next_retry_number: int, *, repair: bool = False) -> str:
    if repair:
        if next_retry_number <= 1:
            return "DATE_ADD(NOW(), INTERVAL 1 MINUTE)"
        if next_retry_number == 2:
            return "DATE_ADD(NOW(), INTERVAL 5 MINUTE)"
        if next_retry_number == 3:
            return "DATE_ADD(NOW(), INTERVAL 15 MINUTE)"
        if next_retry_number == 4:
            return "DATE_ADD(NOW(), INTERVAL 30 MINUTE)"
        return "DATE_ADD(NOW(), INTERVAL 60 MINUTE)"
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


def _mark_failed(event_id: str, error: Exception | str) -> None:
    with get_engine().begin() as conn:
        row = conn.execute(
            text("SELECT retry_count, event_type FROM cloud_sync_outbox WHERE event_id=:event_id"),
            {"event_id": event_id},
        ).mappings().first() or {}
        retry_count = int(row.get("retry_count") or 0)
        repair = str(row.get("event_type") or "").startswith("repair_")
        next_retry = retry_count + 1
        retryable = bool(getattr(error, "retryable", True))
        status = "failed" if retryable else "rejected"
        next_retry_sql = _retry_delay_sql(next_retry, repair=repair) if retryable else "NULL"
        conn.execute(
            text(
                f"""
                UPDATE cloud_sync_outbox
                SET status='{status}',
                    retry_count=retry_count+1,
                    last_error=:last_error,
                    next_retry_at={next_retry_sql}
                WHERE event_id=:event_id
                """
            ),
            {"event_id": event_id, "last_error": str(error or "")[:4000]},
        )


def _record_sync_channel_result(event_type: str, *, ok: bool, error: Any = None) -> None:
    """把 outbox 事件结果同步到本地「同步通道状态」，供页面展示。"""
    try:
        from crud.sync_channels import (
            channel_for_event_type,
            record_channel_failure,
            record_channel_success,
        )

        channel_key = channel_for_event_type(event_type)
        if not channel_key:
            return
        if ok:
            record_channel_success(channel_key, "auto")
        else:
            record_channel_failure(channel_key, error)
    except Exception as exc:  # pragma: no cover - 状态记录失败不影响同步主流程
        logger.warning("record sync channel result failed: %s %s", event_type, exc)


def process_next_cloud_sync_event() -> dict[str, Any] | None:
    event = _load_due_event()
    if not event:
        return None
    event_id = str(event["event_id"])
    event_type = str(event.get("event_type") or "")
    try:
        _dispatch_event(event)
        _mark_synced(event_id)
        _record_sync_channel_result(event_type, ok=True)
        return {"event_id": event_id, "status": "synced"}
    except Exception as exc:
        _mark_failed(event_id, exc)
        _record_sync_channel_result(event_type, ok=False, error=exc)
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


# 云端订单状态语义下的先后顺序：数字越大越接近终态。
# 与 crud.dealer_orders._aggregate_status 聚合出的本地状态配合，用于丢弃
# “本地状态已推进、事件仍停留在旧状态”的过期回传（例如取消成功后晚到的 allocated）。
# rejected 不是云端终态（云端只保护 cancelled/completed），已完成事件允许覆盖已驳回，
# 因此 completed 排在 rejected 之后。
_ORDER_STATUS_RANK = {
    "pending": 0,
    "approved": 1,
    "contracted": 2,
    "partial_allocated": 3,
    "allocated": 4,
    "rejected": 5,
    "completed": 6,
    "complete": 6,
    "cancelled": 7,
}


def _order_status_rank(status: Any) -> int:
    return _ORDER_STATUS_RANK.get(str(status or "").strip(), -1)


def _event_intended_status(event_type: str, payload: dict[str, Any]) -> str:
    """事件想把云端订单改成什么状态；未知事件返回空串（不参与过期判断）。"""
    if event_type == "dealer_order_cancelled":
        return "cancelled"
    if event_type == "dealer_order_contracted":
        return "contracted"
    if event_type == "dealer_order_completed":
        return "completed"
    if event_type == "dealer_order_allocated":
        return str(payload.get("status") or "allocated")
    if event_type == "dealer_order_reviewed":
        return str(payload.get("status") or "")
    return ""


def _load_local_order_aggregate_status(order_no: str) -> str:
    """按 dealer_orders 行聚合出本地订单状态（与订单审核列表同一套 _aggregate_status）。"""
    from crud.dealer_orders import _aggregate_status

    with get_engine().begin() as conn:
        rows = conn.execute(
            text("SELECT * FROM dealer_orders WHERE order_no=:order_no ORDER BY line_no, id"),
            {"order_no": order_no},
        ).mappings().all()
    items = [dict(row) for row in rows]
    if not items:
        return ""
    return _aggregate_status(items)


def _dispatch_event(event: dict[str, Any]) -> None:
    from crud.cloud_dealer_order_sync import (
        fetch_local_wechat_batch_summary,
        push_cloud_allocate,
        push_cloud_cancel,
        push_cloud_completed_state,
        push_cloud_contract,
        push_cloud_review,
        push_wechat_batch_summary_to_cloud,
        refresh_local_wechat_batch_summary,
    )

    payload = event.get("payload") or {}
    event_id = str(event.get("event_id") or "")
    event_type = str(event.get("event_type") or "")

    if event_type == "repair_snapshot_sync":
        from v8_sync.client import NonRetryableSyncError, upload_snapshot
        from v8_sync.config import get_config
        from v8_sync.snapshot_store import (
            get_snapshot,
            mark_snapshot_error,
            mark_snapshot_rejected,
            mark_snapshot_uploaded,
        )

        snapshot_id = str(payload.get("snapshot_id") or "").strip()
        if not snapshot_id:
            raise ValueError("repair snapshot event missing snapshot_id")
        snapshot_row = get_snapshot(snapshot_id=snapshot_id)
        if not snapshot_row:
            raise ValueError(f"repair snapshot not found: {snapshot_id}")
        expected_sha = str(payload.get("payload_sha256") or "")
        actual_sha = str(snapshot_row.get("payload_sha256") or "")
        if expected_sha and expected_sha != actual_sha:
            raise ValueError(f"repair snapshot digest mismatch: {snapshot_id}")
        try:
            upload_snapshot(
                snapshot_row["payload"],
                idempotency_key=event_id,
                config=get_config(),
            )
        except Exception as exc:
            if isinstance(exc, NonRetryableSyncError):
                mark_snapshot_rejected(snapshot_id, str(exc))
            else:
                mark_snapshot_error(snapshot_id, str(exc))
            raise
        mark_snapshot_uploaded(snapshot_id)
        return

    if event_type == "repair_delta_event_sync":
        from v8_sync.client import NonRetryableSyncError

        raise NonRetryableSyncError("repair delta event upload is reserved for the realtime sync phase")
    order_no = str(payload.get("order_no") or event.get("biz_key") or "").strip()

    if event_type.startswith("dealer_order_") and order_no:
        with get_engine().begin() as conn:
            exists = int(
                conn.execute(
                    text("SELECT COUNT(*) FROM dealer_orders WHERE order_no=:order_no"),
                    {"order_no": order_no},
                ).scalar()
                or 0
            )
        if exists <= 0:
            logger.info("Skipping cloud sync event %s because local dealer order %s no longer exists", event_id, order_no)
            return

    # 本地订单已经推进到更靠后的状态时，丢弃退避重试中晚到的旧事件，避免把云端
    # 从 cancelled/completed 等终态覆盖回 allocated/approved；取消事件本身永不拦截。
    if (
        event_type.startswith("dealer_order_")
        and event_type != "dealer_order_cancelled"
        and order_no
    ):
        intended_status = _event_intended_status(event_type, payload)
        intended_rank = _order_status_rank(intended_status)
        local_status = _load_local_order_aggregate_status(order_no)
        local_rank = _order_status_rank(local_status)
        # intended_rank < 0：事件目标状态不可识别，交回原推送逻辑处理（由其报错/重试）。
        if intended_rank >= 0 and local_rank > intended_rank:
            logger.info(
                "skipped-stale cloud sync event %s: order=%s local=%s(rank %s) > "
                "intended=%s(rank %s), local order already advanced",
                event_id,
                order_no,
                local_status,
                local_rank,
                intended_status,
                intended_rank,
            )
            return

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
            status=str(payload.get("status") or "allocated"),
        )
        return

    if event_type == "dealer_order_cancelled":
        push_cloud_cancel(
            order_no,
            contract_no=str(payload.get("contract_no") or ""),
            operator=str(payload.get("operator") or "system"),
            note=str(payload.get("note") or payload.get("reason") or ""),
            line_nos=payload.get("line_nos"),
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
        rows, _excluded_special = fetch_local_wechat_batch_summary()
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


def get_cloud_sync_event_status(event_id: str) -> dict[str, Any] | None:
    """读取单个 outbox 事件的最新状态，供手动触发后回显。"""
    target = str(event_id or "").strip()
    if not target:
        return None
    ensure_cloud_sync_outbox_table()
    with get_engine().connect() as conn:
        row = conn.execute(
            text(
                """
                SELECT event_id, event_type, biz_key, status, retry_count, last_error,
                       next_retry_at, created_at, updated_at, synced_at
                FROM cloud_sync_outbox
                WHERE event_id=:event_id
                LIMIT 1
                """
            ),
            {"event_id": target},
        ).mappings().first()
    if not row:
        return None
    return {
        key: _json_default(value) if isinstance(value, (datetime, date)) else value
        for key, value in dict(row).items()
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
    if os.getenv('V8_DEMO_MODE') == '1':
        logger.info('Cloud push disabled for isolated demo')
        return
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
