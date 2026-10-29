"""本地同步通道状态（与云端「同步监控 → V8 桥接上传」的 4 条通道对齐）。

云端监控按「最近成功时间 + 设定周期」推算通道是否超期；本地页面要展示同一套
通道语义，就需要把本地每次成功/失败记录下来。记录表只存每个通道最近一次状态，
由各自动 worker 与手动触发统一写入，避免各按钮/定时任务各记各的。
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import bindparam, text

from database import get_engine

logger = logging.getLogger(__name__)

TABLE_DDL = """
CREATE TABLE IF NOT EXISTS sync_channel_state (
  channel_key VARCHAR(64) NOT NULL PRIMARY KEY,
  last_success_at DATETIME NULL,
  last_attempt_at DATETIME NULL,
  last_trigger VARCHAR(16) NULL,
  last_error TEXT NULL,
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
"""

# 与云端 AdminSyncEventsController 的 4 条通道保持一致：
# snapshot / orders-pull / machine-snapshot / status-callback。
CHANNELS: tuple[dict[str, Any], ...] = (
    {
        "key": "factory-snapshot",
        "label": "工厂库存快照",
        "direction": "V8 → 云端",
        "interval_seconds": 300,
        "interval_env": "CLOUD_SNAPSHOT_INTERVAL_SECONDS",
        "event_types": ("wechat_batch_summary_sync",),
        "manual_action": "push-inventory",
        "description": "每 5 分钟推送库存/机型快照，库存变化时即时触发",
    },
    {
        "key": "orders-pull",
        "label": "V8 拉取订单",
        "direction": "云端 → V8（拉取）",
        "interval_seconds": 60,
        "interval_env": "CLOUD_PULL_INTERVAL_SECONDS",
        "event_types": (),
        "manual_action": "pull-orders",
        "description": "每 1 分钟从云端分页拉取订单镜像",
    },
    {
        "key": "machine-snapshot",
        "label": "机台快照同步",
        "direction": "V8 → 云端",
        "interval_seconds": 86400,
        "interval_env": "V8_SYNC_CHANNEL_INTERVAL_SECONDS",
        "event_types": ("repair_snapshot_sync",),
        "manual_action": "push-machines",
        "description": "每日生成机台资料快照并上传",
    },
    {
        "key": "status-callback",
        "label": "订单状态回调",
        "direction": "V8 → 云端",
        "interval_seconds": None,
        "interval_env": None,
        "event_types": (
            "dealer_order_reviewed",
            "dealer_order_contracted",
            "dealer_order_allocated",
            "dealer_order_cancelled",
            "dealer_order_completed",
        ),
        "manual_action": None,
        "description": "订单状态变更时事件驱动回传",
    },
)

_CHANNEL_BY_KEY = {channel["key"]: channel for channel in CHANNELS}
_EVENT_CHANNEL_MAP = {
    event_type: channel["key"]
    for channel in CHANNELS
    for event_type in channel["event_types"]
}

STATE_LABELS = {
    "ok": "正常",
    "late": "延迟",
    "down": "超期未同步",
    "unknown": "未知",
    "idle": "暂无事件",
    "pending": "待发送",
    "failed": "有失败",
}

_table_ensured = False


def ensure_sync_channel_state_table() -> None:
    global _table_ensured
    if _table_ensured:
        return
    with get_engine().begin() as conn:
        conn.execute(text(TABLE_DDL))
    _table_ensured = True


def channel_for_event_type(event_type: str) -> str | None:
    return _EVENT_CHANNEL_MAP.get(str(event_type or "").strip())


def _env_interval(name: str | None, default: int) -> int:
    if not name:
        return default
    raw = os.getenv(name)
    if raw is None or not str(raw).strip():
        return default
    try:
        return max(1, int(str(raw).strip()))
    except (TypeError, ValueError):
        return default


def record_channel_success(channel_key: str, trigger: str = "auto") -> None:
    """记录一次通道成功；写失败不影响业务主流程。"""
    try:
        ensure_sync_channel_state_table()
        with get_engine().begin() as conn:
            conn.execute(
                text(
                    """
                    INSERT INTO sync_channel_state
                      (channel_key, last_success_at, last_attempt_at, last_trigger, last_error)
                    VALUES
                      (:channel_key, NOW(), NOW(), :trigger, NULL)
                    ON DUPLICATE KEY UPDATE
                      last_success_at=NOW(),
                      last_attempt_at=NOW(),
                      last_trigger=:trigger,
                      last_error=NULL
                    """
                ),
                {"channel_key": channel_key, "trigger": trigger},
            )
    except Exception as exc:  # pragma: no cover - 状态记录失败不应影响同步
        logger.warning("record sync channel success failed: %s %s", channel_key, exc)


def record_channel_failure(channel_key: str, error: Any) -> None:
    try:
        ensure_sync_channel_state_table()
        with get_engine().begin() as conn:
            conn.execute(
                text(
                    """
                    INSERT INTO sync_channel_state
                      (channel_key, last_success_at, last_attempt_at, last_trigger, last_error)
                    VALUES
                      (:channel_key, NULL, NOW(), NULL, :last_error)
                    ON DUPLICATE KEY UPDATE
                      last_attempt_at=NOW(),
                      last_error=:last_error
                    """
                ),
                {"channel_key": channel_key, "last_error": str(error or "")[:4000]},
            )
    except Exception as exc:  # pragma: no cover - 状态记录失败不应影响同步
        logger.warning("record sync channel failure failed: %s %s", channel_key, exc)


def compute_channel_state(
    *,
    interval_seconds: int | None,
    last_success_at: datetime | None,
    pending: int = 0,
    failed: int = 0,
    now: datetime | None = None,
) -> dict[str, Any]:
    """按云端同一套口径计算通道状态：ok / late / down / unknown / idle / pending / failed。"""
    current = now or datetime.now()
    expected_next: datetime | None = None
    overdue_seconds = 0
    if interval_seconds is None:
        if failed > 0:
            state = "failed"
        elif pending > 0:
            state = "pending"
        elif last_success_at is None:
            state = "idle"
        else:
            state = "ok"
    elif last_success_at is None:
        state = "unknown"
    else:
        expected_next = last_success_at + timedelta(seconds=interval_seconds)
        overdue_seconds = max(0, int((current - expected_next).total_seconds()))
        grace = max(60, min(interval_seconds // 5, 1800))
        if overdue_seconds <= 0:
            state = "ok"
        elif overdue_seconds <= grace:
            state = "late"
        else:
            state = "down"
    return {
        "state": state,
        "state_label": STATE_LABELS.get(state, state),
        "expected_next_at": expected_next.strftime("%Y-%m-%d %H:%M:%S") if expected_next else None,
        "overdue_seconds": overdue_seconds,
    }


def _format_interval(interval_seconds: int | None) -> str:
    if interval_seconds is None:
        return "事件驱动"
    if interval_seconds % 3600 == 0:
        return f"{interval_seconds // 3600} 小时"
    if interval_seconds % 60 == 0:
        return f"{interval_seconds // 60} 分钟"
    return f"{interval_seconds} 秒"


def _format_time(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.strftime("%Y-%m-%d %H:%M:%S")
    return str(value)


def _load_state_rows() -> dict[str, dict[str, Any]]:
    try:
        ensure_sync_channel_state_table()
        with get_engine().connect() as conn:
            rows = conn.execute(text("SELECT * FROM sync_channel_state")).mappings().all()
        return {str(row["channel_key"]): dict(row) for row in rows}
    except Exception as exc:
        logger.warning("read sync channel state failed: %s", exc)
        return {}


def _count_events(event_types: tuple[str, ...]) -> tuple[int, int]:
    if not event_types:
        return 0, 0
    try:
        from crud.cloud_sync_outbox import ensure_cloud_sync_outbox_table

        ensure_cloud_sync_outbox_table()
        with get_engine().connect() as conn:
            row = conn.execute(
                text(
                    """
                    SELECT
                      SUM(CASE WHEN status IN ('pending', 'processing') THEN 1 ELSE 0 END) AS pending,
                      SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END) AS failed
                    FROM cloud_sync_outbox
                    WHERE event_type IN :event_types
                    """
                ).bindparams(bindparam("event_types", expanding=True)),
                {"event_types": tuple(event_types)},
            ).mappings().first()
        return int((row or {}).get("pending") or 0), int((row or {}).get("failed") or 0)
    except Exception as exc:
        logger.warning("count sync channel events failed: %s", exc)
        return 0, 0


def _fallback_last_success(event_types: tuple[str, ...]) -> datetime | None:
    """新装/重建状态表后，用 outbox 已同步事件回填最近成功时间。"""
    if not event_types:
        return None
    try:
        from crud.cloud_sync_outbox import ensure_cloud_sync_outbox_table

        ensure_cloud_sync_outbox_table()
        with get_engine().connect() as conn:
            value = conn.execute(
                text(
                    """
                    SELECT MAX(synced_at) FROM cloud_sync_outbox
                    WHERE event_type IN :event_types AND status = 'synced'
                    """
                ).bindparams(bindparam("event_types", expanding=True)),
                {"event_types": tuple(event_types)},
            ).scalar()
        return value if isinstance(value, datetime) else None
    except Exception as exc:
        logger.warning("fallback sync channel last success failed: %s", exc)
        return None


def get_sync_channels_status(now: datetime | None = None) -> dict[str, Any]:
    """返回 4 条同步通道的本地可观测状态（云端监控仍是最终口径）。"""
    current = now or datetime.now()
    state_rows = _load_state_rows()
    channels: list[dict[str, Any]] = []
    for channel in CHANNELS:
        key = channel["key"]
        row = state_rows.get(key) or {}
        event_types = tuple(channel["event_types"])
        pending, failed = _count_events(event_types)
        last_success = row.get("last_success_at")
        if not isinstance(last_success, datetime):
            last_success = _fallback_last_success(event_types)
        interval = _env_interval(channel.get("interval_env"), int(channel["interval_seconds"] or 0) or 0) or None
        if channel["interval_seconds"] is None:
            interval = None
        computed = compute_channel_state(
            interval_seconds=interval,
            last_success_at=last_success,
            pending=pending,
            failed=failed,
            now=current,
        )
        channels.append(
            {
                "key": key,
                "label": channel["label"],
                "direction": channel["direction"],
                "description": channel["description"],
                "interval_seconds": interval,
                "interval_label": _format_interval(interval),
                "last_success_at": _format_time(last_success),
                "last_trigger": row.get("last_trigger"),
                "last_error": row.get("last_error"),
                "pending": pending,
                "failed": failed,
                "manual_action": channel["manual_action"],
                **computed,
            }
        )
    return {
        "server_time": current.strftime("%Y-%m-%d %H:%M:%S"),
        "channels": channels,
    }
