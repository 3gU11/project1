from __future__ import annotations

import os
from datetime import date, datetime
from pathlib import Path
from typing import Any

import httpx
from sqlalchemy import text

from crud.dealer_orders import ensure_dealer_order_tables
from database import get_engine


SYNCABLE_STATUSES = {"pending", "approved", "contracted", "partial_allocated", "allocated", "completed", "rejected"}


def _read_dotenv_value(key: str) -> str:
    env_path = Path(__file__).resolve().parents[1] / ".env"
    if not env_path.exists():
        return ""
    try:
        for line in env_path.read_text(encoding="utf-8").splitlines():
            raw = line.strip()
            if not raw or raw.startswith("#") or "=" not in raw:
                continue
            name, value = raw.split("=", 1)
            if name.strip() == key:
                return value.strip().strip('"').strip("'")
    except OSError:
        return ""
    return ""


def _cloud_config() -> tuple[str, str]:
    base_url = (os.getenv("WECHAT_CLOUD_API_BASE") or _read_dotenv_value("WECHAT_CLOUD_API_BASE")).strip().rstrip("/")
    api_key = (os.getenv("V7_API_KEY") or _read_dotenv_value("V7_API_KEY")).strip()
    if not base_url:
        raise ValueError("WECHAT_CLOUD_API_BASE is not configured")
    if not api_key:
        raise ValueError("V7_API_KEY is not configured")
    return base_url, api_key


def _as_int(value: Any, default: int = 0) -> int:
    try:
        return int(value if value is not None else default)
    except (TypeError, ValueError):
        return default


def _clean(value: Any, default: str = "") -> str:
    if value is None:
        return default
    return str(value).strip()


def _jsonable(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.strftime("%Y-%m-%d %H:%M:%S")
    if isinstance(value, date):
        return value.strftime("%Y-%m-%d")
    return value


def _status_rank(status: str) -> int:
    return {
        "pending": 0,
        "approved": 1,
        "contracted": 2,
        "partial_allocated": 3,
        "allocated": 4,
        "completed": 5,
        "rejected": 6,
    }.get(status or "", -1)


def _normalize_status(status: Any) -> str:
    value = _clean(status) or "pending"
    return value if value in SYNCABLE_STATUSES else "pending"


def _iter_cloud_items(order: dict[str, Any]) -> list[dict[str, Any]]:
    items = order.get("items")
    if isinstance(items, list) and items:
        return [item for item in items if isinstance(item, dict)]
    return [order]


def fetch_cloud_dealer_orders(status: str = "pending", page_size: int = 100, max_pages: int = 20) -> list[dict[str, Any]]:
    base_url, api_key = _cloud_config()
    status = _normalize_status(status)
    page_size = min(max(1, int(page_size or 100)), 200)
    max_pages = max(1, int(max_pages or 1))
    orders: list[dict[str, Any]] = []
    with httpx.Client(timeout=20.0, trust_env=False, headers={"X-V7-API-KEY": api_key}) as client:
        for page in range(1, max_pages + 1):
            response = client.get(
                f"{base_url}/api/v7/dealer-orders",
                params={"status": status, "page": page, "page_size": page_size},
            )
            response.raise_for_status()
            payload = response.json()
            data = payload.get("data") if isinstance(payload, dict) else []
            if not isinstance(data, list) or not data:
                break
            orders.extend([row for row in data if isinstance(row, dict)])
            if len(data) < page_size:
                break
    return orders


def _post_cloud_order(order_no: str, path_suffix: str, payload: dict[str, Any], idempotency_key: str) -> dict[str, Any]:
    base_url, api_key = _cloud_config()
    order_no = _clean(order_no)
    if not order_no:
        raise ValueError("order_no is required")
    with httpx.Client(timeout=20.0, trust_env=False, headers={"X-V7-API-KEY": api_key}) as client:
        response = client.post(
            f"{base_url}/api/v7/dealer-orders/{order_no}/{path_suffix}",
            headers={"Idempotency-Key": idempotency_key},
            json=payload,
        )
        if response.status_code == 404:
            return {"skipped": True, "reason": "cloud_order_not_found", "order_no": order_no}
        response.raise_for_status()
        return response.json()


def push_cloud_review(order_no: str, status: str, reviewer: str, note: str = "") -> dict[str, Any]:
    next_status = _clean(status)
    if next_status not in {"approved", "rejected"}:
        raise ValueError("cloud review status must be approved or rejected")
    return _post_cloud_order(
        order_no=order_no,
        path_suffix="review",
        payload={"status": next_status, "reviewedBy": _clean(reviewer), "reviewNote": _clean(note)},
        idempotency_key=f"v7-review-{next_status}-{_clean(order_no)}",
    )


def push_cloud_contract(order_no: str, contract_no: str, operator: str = "", v7_order_no: str = "") -> dict[str, Any]:
    return _post_cloud_order(
        order_no=order_no,
        path_suffix="contract",
        payload={
            "contractNo": _clean(contract_no),
            "v7OrderNo": _clean(v7_order_no),
            "contractedBy": _clean(operator),
        },
        idempotency_key=f"v7-contract-{_clean(order_no)}-{_clean(contract_no)}",
    )


def push_cloud_allocate(order_no: str, contract_no: str = "", operator: str = "", v7_order_no: str = "") -> dict[str, Any]:
    return _post_cloud_order(
        order_no=order_no,
        path_suffix="allocate",
        payload={
            "contractNo": _clean(contract_no),
            "v7OrderNo": _clean(v7_order_no),
            "allocatedBy": _clean(operator),
        },
        idempotency_key=f"v7-allocate-{_clean(order_no)}-{_clean(contract_no)}-{_clean(v7_order_no)}",
    )


def refresh_local_wechat_batch_summary() -> dict[str, Any]:
    """Rebuild the local mini-program inventory read model from finished_goods_data."""
    with get_engine().begin() as conn:
        try:
            conn.execute(text("CALL `refresh_wechat_batch_summary_all`()"))
        except Exception:
            conn.execute(
                text(
                    """
                    CREATE TABLE IF NOT EXISTS wechat_batch_summary (
                      summary_id CHAR(32) NOT NULL,
                      batch_no VARCHAR(100) NOT NULL,
                      expected_inbound_time DATETIME NULL,
                      model VARCHAR(100) NOT NULL,
                      quantity INT NOT NULL DEFAULT 0,
                      `批次号` VARCHAR(100) NOT NULL,
                      `预计入库时间` DATETIME NULL,
                      `机型` VARCHAR(100) NOT NULL,
                      `数量` INT NOT NULL DEFAULT 0,
                      `更新时间` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                      PRIMARY KEY (summary_id),
                      INDEX idx_wbs_batch (`批次号`),
                      INDEX idx_wbs_inbound (`预计入库时间`),
                      INDEX idx_wbs_model (`机型`)
                    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
                    """
                )
            )
            conn.execute(text("TRUNCATE TABLE wechat_batch_summary"))
            conn.execute(
                text(
                    """
                    INSERT INTO wechat_batch_summary
                      (summary_id, batch_no, expected_inbound_time, model, quantity,
                       `批次号`, `预计入库时间`, `机型`, `数量`)
                    SELECT
                      MD5(CONCAT(
                        s.batch_no, '|',
                        COALESCE(DATE_FORMAT(s.expected_inbound_time, '%Y-%m-%d %H:%i:%s'), ''),
                        '|', s.model
                      )) AS summary_id,
                      s.batch_no,
                      s.expected_inbound_time,
                      s.model,
                      s.quantity,
                      s.batch_no AS `批次号`,
                      s.expected_inbound_time AS `预计入库时间`,
                      s.model AS `机型`,
                      s.quantity AS `数量`
                    FROM (
                      SELECT
                        TRIM(`批次号`) AS batch_no,
                        `预计入库时间` AS expected_inbound_time,
                        TRIM(`机型`) AS model,
                        COUNT(*) AS quantity
                      FROM finished_goods_data
                      WHERE NULLIF(TRIM(COALESCE(`批次号`, '')), '') IS NOT NULL
                        AND NULLIF(TRIM(COALESCE(`机型`, '')), '') IS NOT NULL
                        AND TRIM(COALESCE(`状态`, '')) = '待入库'
                      GROUP BY TRIM(`批次号`), `预计入库时间`, TRIM(`机型`)
                      UNION ALL
                      SELECT
                        '库存中' AS batch_no,
                        CAST(NULL AS DATETIME) AS expected_inbound_time,
                        TRIM(`机型`) AS model,
                        COUNT(*) AS quantity
                      FROM finished_goods_data
                      WHERE NULLIF(TRIM(COALESCE(`机型`, '')), '') IS NOT NULL
                        AND TRIM(COALESCE(`状态`, '')) = '库存中'
                      GROUP BY TRIM(`机型`)
                    ) s
                    """
                )
            )
        total = conn.execute(text("SELECT COUNT(*) FROM wechat_batch_summary")).scalar() or 0
    return {"refreshed": True, "rows": int(total)}


def fetch_local_wechat_batch_summary() -> list[dict[str, Any]]:
    with get_engine().begin() as conn:
        rows = conn.execute(
            text(
                """
                SELECT
                  summary_id,
                  batch_no,
                  expected_inbound_time,
                  model,
                  quantity,
                  `批次号`,
                  `预计入库时间`,
                  `机型`,
                  `数量`,
                  `更新时间`
                FROM wechat_batch_summary
                ORDER BY batch_no, expected_inbound_time, model
                """
            )
        ).mappings().all()
    return [{key: _jsonable(value) for key, value in row.items()} for row in rows]


def push_wechat_batch_summary_to_cloud(rows: list[dict[str, Any]]) -> dict[str, Any]:
    base_url, api_key = _cloud_config()
    with httpx.Client(timeout=60.0, trust_env=False, headers={"X-V7-API-KEY": api_key}) as client:
        response = client.post(
            f"{base_url}/api/v7/wechat-batch-summary/sync",
            json={"mode": "replace", "rows": rows},
        )
        response.raise_for_status()
        return response.json()


def sync_wechat_batch_summary_to_cloud() -> dict[str, Any]:
    local = refresh_local_wechat_batch_summary()
    rows = fetch_local_wechat_batch_summary()
    cloud = push_wechat_batch_summary_to_cloud(rows)
    return {
        "message": "wechat batch summary synced",
        "local_rows": local["rows"],
        "pushed_rows": len(rows),
        "cloud": cloud,
    }


def _line_payload(item: dict[str, Any], order: dict[str, Any]) -> dict[str, Any]:
    status = _normalize_status(item.get("status") or order.get("status"))
    return {
        "order_no": _clean(item.get("order_no") or order.get("order_no")),
        "line_no": max(1, _as_int(item.get("line_no"), 1)),
        "dealer_id": _clean(item.get("dealer_id") or order.get("dealer_id")),
        "dealer_name": _clean(item.get("dealer_name") or order.get("dealer_name")),
        "dealer_phone": _clean(item.get("dealer_phone") or order.get("dealer_phone")),
        "regional_manager_name": _clean(item.get("regional_manager_name") or order.get("regional_manager_name")),
        "customer_name": _clean(item.get("customer_name") or order.get("customer_name")),
        "contact_name": _clean(item.get("contact_name") or order.get("contact_name")),
        "contact_phone": _clean(item.get("contact_phone") or order.get("contact_phone")),
        "model": _clean(item.get("model")),
        "batch_no": _clean(item.get("batch_no")),
        "eta": _clean(item.get("eta") or item.get("expected_inbound_time")),
        "inventory_type": _clean(item.get("inventory_type")),
        "quantity": max(1, _as_int(item.get("quantity"), 1)),
        "approved_qty": max(0, _as_int(item.get("approved_qty"), 0)),
        "allocated_qty": max(0, _as_int(item.get("allocated_qty"), 0)),
        "delivery_date": _clean(item.get("delivery_date") or order.get("delivery_date")),
        "remark": _clean(item.get("remark") or order.get("remark")),
        "status": status,
        "regional_review_status": _clean(item.get("regional_review_status") or order.get("regional_review_status")),
        "regional_review_note": _clean(item.get("regional_review_note") or order.get("regional_review_note")),
        "regional_reviewed_by": _clean(item.get("regional_reviewed_by") or order.get("regional_reviewed_by")),
        "regional_reviewed_at": _clean(item.get("regional_reviewed_at") or order.get("regional_reviewed_at")) or None,
        "reviewed_at": _clean(item.get("reviewed_at") or order.get("reviewed_at")) or None,
        "reviewed_by": _clean(item.get("reviewed_by") or order.get("reviewed_by")),
        "contract_no": _clean(item.get("contract_no") or order.get("contract_no")),
        "v7_order_no": _clean(item.get("v7_order_no") or order.get("v7_order_no")),
        "review_note": _clean(item.get("review_note") or order.get("review_note")),
        "created_at": _clean(item.get("created_at") or order.get("created_at")) or None,
        "updated_at": _clean(item.get("updated_at") or order.get("updated_at")) or None,
    }


def sync_cloud_dealer_orders(status: str = "pending", page_size: int = 100, max_pages: int = 20) -> dict[str, Any]:
    ensure_dealer_order_tables()
    orders = fetch_cloud_dealer_orders(status=status, page_size=page_size, max_pages=max_pages)
    inserted = 0
    updated = 0
    skipped = 0
    seen_lines: set[tuple[str, int]] = set()

    with get_engine().begin() as conn:
        for order in orders:
            for item in _iter_cloud_items(order):
                payload = _line_payload(item, order)
                order_no = payload["order_no"]
                line_no = payload["line_no"]
                if not order_no or not payload["model"]:
                    skipped += 1
                    continue
                key = (order_no, line_no)
                if key in seen_lines:
                    skipped += 1
                    continue
                seen_lines.add(key)

                existing = conn.execute(
                    text(
                        "SELECT status, approved_qty, allocated_qty, reviewed_at, reviewed_by, "
                        "contract_no, v7_order_no, review_note "
                        "FROM dealer_orders WHERE order_no=:order_no AND line_no=:line_no"
                    ),
                    {"order_no": order_no, "line_no": line_no},
                ).mappings().first()

                if existing:
                    local_status = _clean(existing.get("status"))
                    if _status_rank(local_status) > _status_rank(payload["status"]):
                        payload["status"] = local_status
                        payload["approved_qty"] = max(_as_int(existing.get("approved_qty")), payload["approved_qty"])
                        payload["allocated_qty"] = max(_as_int(existing.get("allocated_qty")), payload["allocated_qty"])
                    for field in ("reviewed_at", "reviewed_by", "contract_no", "v7_order_no", "review_note"):
                        if existing.get(field) and not payload.get(field):
                            payload[field] = existing.get(field)
                    conn.execute(
                        text(
                            """
                            UPDATE dealer_orders
                            SET dealer_id=:dealer_id, dealer_name=:dealer_name, dealer_phone=:dealer_phone,
                                regional_manager_name=:regional_manager_name,
                                customer_name=:customer_name, contact_name=:contact_name, contact_phone=:contact_phone,
                                model=:model, batch_no=:batch_no, eta=:eta, inventory_type=:inventory_type,
                                quantity=:quantity, approved_qty=:approved_qty, allocated_qty=:allocated_qty,
                                delivery_date=:delivery_date, remark=:remark, status=:status,
                                regional_review_status=:regional_review_status,
                                regional_review_note=:regional_review_note,
                                regional_reviewed_by=:regional_reviewed_by,
                                regional_reviewed_at=:regional_reviewed_at,
                                reviewed_at=:reviewed_at, reviewed_by=:reviewed_by,
                                contract_no=:contract_no, v7_order_no=:v7_order_no, review_note=:review_note,
                                updated_at=COALESCE(:updated_at, NOW())
                            WHERE order_no=:order_no AND line_no=:line_no
                            """
                        ),
                        payload,
                    )
                    updated += 1
                else:
                    conn.execute(
                        text(
                            """
                            INSERT INTO dealer_orders
                            (order_no, line_no, dealer_id, dealer_name, dealer_phone, regional_manager_name,
                             customer_name, contact_name, contact_phone, model, batch_no, eta, inventory_type,
                             quantity, approved_qty, allocated_qty, delivery_date, remark, status,
                             regional_review_status, regional_review_note, regional_reviewed_by, regional_reviewed_at,
                             reviewed_at, reviewed_by, contract_no, v7_order_no, review_note, created_at, updated_at)
                            VALUES
                            (:order_no, :line_no, :dealer_id, :dealer_name, :dealer_phone, :regional_manager_name,
                             :customer_name, :contact_name, :contact_phone, :model, :batch_no, :eta, :inventory_type,
                             :quantity, :approved_qty, :allocated_qty, :delivery_date, :remark, :status,
                             :regional_review_status, :regional_review_note, :regional_reviewed_by, :regional_reviewed_at,
                             :reviewed_at, :reviewed_by, :contract_no, :v7_order_no, :review_note,
                             COALESCE(:created_at, NOW()), COALESCE(:updated_at, NOW()))
                            """
                        ),
                        payload,
                    )
                    inserted += 1

    return {
        "message": "cloud dealer orders synced",
        "status": _normalize_status(status),
        "orders_fetched": len(orders),
        "lines_seen": len(seen_lines),
        "inserted": inserted,
        "updated": updated,
        "skipped": skipped,
    }
