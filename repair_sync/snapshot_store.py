from __future__ import annotations

import json
import hashlib
from datetime import date, datetime
from typing import Any

from sqlalchemy import text

from database import get_engine

TABLE_DDL = """
CREATE TABLE IF NOT EXISTS repair_sync_snapshots (
  snapshot_id VARCHAR(64) NOT NULL PRIMARY KEY,
  business_date DATE NOT NULL,
  schema_version VARCHAR(32) NOT NULL,
  dataset_type VARCHAR(64) NOT NULL,
  payload_json LONGTEXT NOT NULL,
  payload_sha256 CHAR(64) NOT NULL,
  record_count INT NOT NULL DEFAULT 0,
  machine_count INT NOT NULL DEFAULT 0,
  source_watermark_json JSON NULL,
  status VARCHAR(32) NOT NULL DEFAULT 'created',
  last_error TEXT NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  uploaded_at DATETIME NULL,
  UNIQUE KEY uq_repair_snapshot_date (business_date, dataset_type),
  KEY idx_repair_snapshot_status (status, created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
"""


def ensure_snapshot_table() -> None:
    with get_engine().begin() as conn:
        conn.execute(text(TABLE_DDL))


def _public_payload(payload: dict[str, Any]) -> dict[str, Any]:
    # These fields are local bookkeeping and are deliberately not sent to the
    # server contract, which rejects undeclared fields.
    return {key: value for key, value in payload.items() if key not in {"payloadSha256", "sourceWatermark"}}


def payload_sha256(payload: dict[str, Any]) -> str:
    raw = json.dumps(_public_payload(payload), ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _payload_json(payload: dict[str, Any]) -> str:
    return json.dumps(_public_payload(payload), ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def save_snapshot(payload: dict[str, Any], *, status: str = "created") -> dict[str, Any]:
    ensure_snapshot_table()
    tables = payload.get("tables") or {}
    counts = payload.get("counts") or {}
    snapshot_id = str(payload["snapshotId"])
    business_date = str(payload["businessDate"])
    payload_json = _payload_json(payload)
    digest = payload_sha256(payload)
    with get_engine().begin() as conn:
        existing = conn.execute(
            text(
                "SELECT snapshot_id, payload_sha256, status FROM repair_sync_snapshots "
                "WHERE business_date=:business_date AND dataset_type='repair_snapshot'"
            ),
            {"business_date": business_date},
        ).mappings().first()
        if existing:
            if existing["payload_sha256"] != digest:
                raise ValueError(f"snapshot already exists for {business_date} with different content")
            return dict(existing)
        conn.execute(
            text(
                """
                INSERT INTO repair_sync_snapshots
                  (snapshot_id, business_date, schema_version, dataset_type, payload_json,
                   payload_sha256, record_count, machine_count, source_watermark_json, status)
                VALUES
                  (:snapshot_id, :business_date, :schema_version, 'repair_snapshot', :payload_json,
                   :payload_sha256, :record_count, :machine_count, :watermark_json, :status)
                """
            ),
            {
                "snapshot_id": snapshot_id,
                "business_date": business_date,
                "schema_version": str(payload.get("schemaVersion") or ""),
                "payload_json": payload_json,
                "payload_sha256": digest,
                "record_count": sum(len(value) for value in tables.values() if isinstance(value, list)),
                "machine_count": int(counts.get("machines") or 0),
                "watermark_json": json.dumps(payload.get("sourceWatermark") or {}, ensure_ascii=False),
                "status": status,
            },
        )
    return {
        "snapshot_id": snapshot_id,
        "business_date": business_date,
        "status": status,
        "payload_sha256": digest,
    }


def get_snapshot(snapshot_id: str | None = None, business_date: date | str | None = None) -> dict[str, Any] | None:
    ensure_snapshot_table()
    if not snapshot_id and business_date is None:
        raise ValueError("snapshot_id or business_date is required")
    where = "snapshot_id=:snapshot_id" if snapshot_id else "business_date=:business_date AND dataset_type='repair_snapshot'"
    params = {"snapshot_id": snapshot_id} if snapshot_id else {"business_date": str(business_date)}
    with get_engine().connect() as conn:
        row = conn.execute(text(f"SELECT * FROM repair_sync_snapshots WHERE {where} LIMIT 1"), params).mappings().first()
    if not row:
        return None
    result = dict(row)
    result["payload"] = json.loads(result.pop("payload_json"))
    return result


def mark_snapshot_uploaded(snapshot_id: str) -> None:
    with get_engine().begin() as conn:
        conn.execute(
            text(
                "UPDATE repair_sync_snapshots SET status='uploaded', uploaded_at=NOW(), last_error=NULL "
                "WHERE snapshot_id=:snapshot_id"
            ),
            {"snapshot_id": snapshot_id},
        )


def mark_snapshot_error(snapshot_id: str, error: str) -> None:
    with get_engine().begin() as conn:
        conn.execute(
            text(
                "UPDATE repair_sync_snapshots SET status='failed', last_error=:last_error "
                "WHERE snapshot_id=:snapshot_id"
            ),
            {"snapshot_id": snapshot_id, "last_error": str(error)[:4000]},
        )


def mark_snapshot_rejected(snapshot_id: str, error: str) -> None:
    with get_engine().begin() as conn:
        conn.execute(
            text(
                "UPDATE repair_sync_snapshots SET status='rejected', last_error=:last_error "
                "WHERE snapshot_id=:snapshot_id"
            ),
            {"snapshot_id": snapshot_id, "last_error": str(error)[:4000]},
        )


def list_snapshots(limit: int = 20) -> list[dict[str, Any]]:
    ensure_snapshot_table()
    with get_engine().connect() as conn:
        rows = conn.execute(
            text(
                "SELECT snapshot_id, business_date, status, payload_sha256 "
                "FROM repair_sync_snapshots ORDER BY business_date DESC LIMIT :limit"
            ),
            {"limit": max(1, min(int(limit), 100))},
        ).mappings().all()
    return [dict(row) for row in rows]
