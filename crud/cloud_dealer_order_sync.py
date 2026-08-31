from __future__ import annotations

import logging
import os
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime
from pathlib import Path
from typing import Any

import httpx
from sqlalchemy import bindparam, text

from crud.dealer_orders import ensure_dealer_order_tables
from database import get_engine

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Shared httpx client (connection pool reuse)
# ---------------------------------------------------------------------------
_http_client: httpx.Client | None = None
_http_lock = threading.Lock()


def _get_http_client() -> httpx.Client:
    """Return a module-level shared httpx.Client with connection pooling."""
    global _http_client
    if _http_client is None or _http_client.is_closed:
        with _http_lock:
            if _http_client is None or _http_client.is_closed:
                _, api_key = _cloud_config()
                _http_client = httpx.Client(
                    timeout=30.0,
                    trust_env=False,
                    headers={"X-V7-API-KEY": api_key},
                    limits=httpx.Limits(max_connections=10, max_keepalive_connections=5),
                )
    return _http_client


SYNCABLE_STATUSES = {
    "regional_pending",
    "regional_rejected",
    "pending",
    "approved",
    "contracted",
    "partial_allocated",
    "allocated",
    "completed",
    "complete",
    "rejected",
    "cancelled",
}
# Only statuses supported by the cloud API (regional_* are local-only)
CLOUD_READ_STATUSES = (
    "pending",
    "approved",
    "contracted",
    "partial_allocated",
    "allocated",
    "completed",
    "rejected",
    "cancelled",
)


def _ensure_wechat_batch_summary_schema(conn) -> None:
    conn.execute(
        text(
            """
            CREATE TABLE IF NOT EXISTS wechat_batch_summary (
              summary_id CHAR(32) NOT NULL,
              batch_no VARCHAR(100) NOT NULL,
              expected_inbound_time DATETIME NULL,
              model VARCHAR(100) NOT NULL,
              quantity INT NOT NULL DEFAULT 0,
              heightened TINYINT(1) NOT NULL DEFAULT 0,
              original_batch_no VARCHAR(100) DEFAULT '',
              original_expected_inbound_time DATETIME NULL,
              updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
              PRIMARY KEY (summary_id),
              INDEX idx_wbs_batch (batch_no),
              INDEX idx_wbs_inbound (expected_inbound_time),
              INDEX idx_wbs_model (model)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """
        )
    )

    def has_column(column_name: str) -> bool:
        return conn.execute(
            text("SHOW COLUMNS FROM wechat_batch_summary LIKE :column_name"),
            {"column_name": column_name},
        ).fetchone() is not None

    missing_columns = [
        ("heightened", "TINYINT(1) NOT NULL DEFAULT 0"),
        ("original_batch_no", "VARCHAR(100) DEFAULT ''"),
        ("original_expected_inbound_time", "DATETIME NULL"),
        ("updated_at", "TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP"),
    ]
    for column_name, column_def in missing_columns:
        if not has_column(column_name):
            conn.execute(text(f"ALTER TABLE wechat_batch_summary ADD COLUMN {column_name} {column_def}"))

    for column_name, column_def in [
        ("批次号", "VARCHAR(100) NOT NULL DEFAULT ''"),
        ("预计入库时间", "DATETIME NULL"),
        ("机型", "VARCHAR(100) NOT NULL DEFAULT ''"),
        ("数量", "INT NOT NULL DEFAULT 0"),
        ("更新时间", "TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP"),
    ]:
        if not has_column(column_name):
            conn.execute(text(f"ALTER TABLE wechat_batch_summary ADD COLUMN `{column_name}` {column_def}"))
        else:
            conn.execute(text(f"ALTER TABLE wechat_batch_summary MODIFY COLUMN `{column_name}` {column_def}"))

    def has_index(index_name: str) -> bool:
        return conn.execute(
            text(
                """
                SELECT COUNT(*)
                FROM information_schema.STATISTICS
                WHERE TABLE_SCHEMA = DATABASE()
                  AND TABLE_NAME = 'wechat_batch_summary'
                  AND INDEX_NAME = :index_name
                """
            ),
            {"index_name": index_name},
        ).scalar() > 0

    for index_name, column_name in [
        ("idx_wbs_batch", "batch_no"),
        ("idx_wbs_inbound", "expected_inbound_time"),
        ("idx_wbs_model", "model"),
    ]:
        if not has_index(index_name):
            conn.execute(text(f"CREATE INDEX {index_name} ON wechat_batch_summary ({column_name})"))


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


def _sync_secret() -> str:
    return (
        os.getenv("V8_SYNC_SECRET")
        or os.getenv("CLOUD_SYNC_SECRET")
        or _read_dotenv_value("V8_SYNC_SECRET")
        or _read_dotenv_value("CLOUD_SYNC_SECRET")
    ).strip()


def _as_int(value: Any, default: int = 0) -> int:
    try:
        return int(value if value is not None else default)
    except (TypeError, ValueError):
        return default


def _clean(value: Any, default: str = "") -> str:
    if value is None:
        return default
    return str(value).strip()


def _pick(data: dict[str, Any], *keys: str, default: Any = None) -> Any:
    for key in keys:
        if key in data and data.get(key) is not None:
            return data.get(key)
    return default


def _jsonable(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.strftime("%Y-%m-%d %H:%M:%S")
    if isinstance(value, date):
        return value.strftime("%Y-%m-%d")
    return value


def _status_rank(status: str) -> int:
    return {
        "regional_pending": -1,
        "pending": 0,
        "approved": 1,
        "contracted": 2,
        "partial_allocated": 3,
        "allocated": 4,
        "completed": 5,
        "complete": 5,
        "regional_rejected": 6,
        "rejected": 6,
        "cancelled": 7,
    }.get(status or "", -1)


def _normalize_status(status: Any) -> str:
    value = _clean(status) or "pending"
    return value if value in SYNCABLE_STATUSES else "pending"


def _iter_cloud_items(order: dict[str, Any]) -> list[dict[str, Any]]:
    items = order.get("items")
    if isinstance(items, list) and items:
        return [item for item in items if isinstance(item, dict)]
    return [order]


def _fetch_cloud_dealer_orders_by_status(status: str, page_size: int = 100, max_pages: int = 20) -> list[dict[str, Any]]:
    base_url, api_key = _cloud_config()
    status = _normalize_status(status)
    page_size = min(max(1, int(page_size or 100)), 200)
    max_pages = max(1, int(max_pages or 1))
    orders: list[dict[str, Any]] = []
    client = _get_http_client()
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


def fetch_cloud_dealer_orders(status: str = "pending", page_size: int = 100, max_pages: int = 20) -> list[dict[str, Any]]:
    requested_status = _clean(status).lower()
    if requested_status not in {"", "all", "*"}:
        return _fetch_cloud_dealer_orders_by_status(status, page_size=page_size, max_pages=max_pages)

    # Concurrently fetch all statuses (up to 4 in parallel)
    orders: list[dict[str, Any]] = []
    seen_keys: set[tuple[str, int]] = set()
    status_results: dict[str, list[dict[str, Any]]] = {}
    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = {
            pool.submit(_fetch_cloud_dealer_orders_by_status, s, page_size, max_pages): s
            for s in CLOUD_READ_STATUSES
        }
        for future in as_completed(futures):
            s = futures[future]
            try:
                status_results[s] = future.result()
            except Exception as exc:
                logger.warning("cloud fetch status=%s failed: %s", s, exc)
                status_results[s] = []
    # Deduplicate in original status order
    for read_status in CLOUD_READ_STATUSES:
        for order in status_results.get(read_status, []):
            items = _iter_cloud_items(order)
            first_item = items[0] if items else order
            key = (
                _clean(_pick(first_item, "order_no", "orderNo") or _pick(order, "order_no", "orderNo")),
                _as_int(_pick(first_item, "line_no", "lineNo"), 1),
            )
            if key in seen_keys:
                continue
            seen_keys.add(key)
            orders.append(order)
    return orders


def _post_cloud_order(order_no: str, path_suffix: str, payload: dict[str, Any], idempotency_key: str) -> dict[str, Any]:
    base_url, api_key = _cloud_config()
    order_no = _clean(order_no)
    if not order_no:
        raise ValueError("order_no is required")
    client = _get_http_client()
    headers = {"Idempotency-Key": idempotency_key}
    secret = _sync_secret()
    if secret:
        headers["X-V8-Sync-Secret"] = secret
    response = client.post(
        f"{base_url}/api/dealer/orders/{order_no}/v8-status",
        headers=headers,
        json=payload,
    )
    if response.status_code == 404:
        # 404 means the order doesn't exist on the cloud yet.
        # Raise so the outbox marks this as failed and retries later
        # instead of silently marking the event as synced (old bug).
        raise RuntimeError(f"cloud order not found (404): order_no={order_no}")
    try:
        response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        detail = ""
        try:
            body = response.json()
            if isinstance(body, dict):
                detail = str(body.get("detail") or body.get("message") or body)
            else:
                detail = str(body)
        except ValueError:
            detail = response.text
        if detail:
            raise RuntimeError(f"{exc}; detail={detail}") from exc
        raise
    return response.json()


def push_cloud_review(
    order_no: str,
    status: str,
    reviewer: str,
    note: str = "",
    factory_pending: int | None = None,
    idempotency_key: str | None = None,
) -> dict[str, Any]:
    next_status = _clean(status)
    if next_status not in {"approved", "rejected"}:
        raise ValueError("cloud review status must be approved or rejected")
    payload = {
        "status": next_status,
        "reviewedBy": _clean(reviewer),
        "reviewNote": _clean(note),
        "updatedAt": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }
    if factory_pending is not None:
        payload["factory_pending"] = 1 if _as_int(factory_pending) else 0
    return _post_cloud_order(
        order_no=order_no,
        path_suffix="v8-status",
        payload=payload,
        idempotency_key=idempotency_key or f"v8-outbox-review-{next_status}-{_clean(order_no)}",
    )


def push_cloud_contract(
    order_no: str,
    contract_no: str,
    operator: str = "",
    v7_order_no: str = "",
    idempotency_key: str | None = None,
) -> dict[str, Any]:
    return _post_cloud_order(
        order_no=order_no,
        path_suffix="v8-status",
        payload={
            "status": "contracted",
            "contractNo": _clean(contract_no),
            "v7OrderNo": _clean(v7_order_no),
            "reviewedBy": _clean(operator),
            "reviewNote": "V8 contract sync",
            "updatedAt": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        },
        idempotency_key=idempotency_key or f"v8-outbox-contract-{_clean(order_no)}-{_clean(contract_no)}",
    )


def push_cloud_allocate(
    order_no: str,
    contract_no: str = "",
    operator: str = "",
    v7_order_no: str = "",
    idempotency_key: str | None = None,
) -> dict[str, Any]:
    return _post_cloud_order(
        order_no=order_no,
        path_suffix="v8-status",
        payload={
            "status": "allocated",
            "contractNo": _clean(contract_no),
            "v7OrderNo": _clean(v7_order_no),
            "reviewedBy": _clean(operator),
            "reviewNote": "V8 allocation sync",
            "updatedAt": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        },
        idempotency_key=idempotency_key or f"v8-outbox-allocate-{_clean(order_no)}-{_clean(contract_no)}-{_clean(v7_order_no)}",
    )


def push_cloud_complete(
    order_no: str,
    operator: str = "",
    v7_order_no: str = "",
    idempotency_key: str | None = None,
) -> dict[str, Any]:
    return _post_cloud_order(
        order_no=order_no,
        path_suffix="v8-status",
        payload={
            "status": "completed",
            "reviewedBy": _clean(operator),
            "v7OrderNo": _clean(v7_order_no),
            "reviewNote": "V8 completed sync",
            "updatedAt": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        },
        idempotency_key=idempotency_key or f"v8-outbox-complete-{_clean(order_no)}-{_clean(v7_order_no)}",
    )


def find_cloud_dealer_order(order_no: str) -> dict[str, Any] | None:
    order_no = _clean(order_no)
    if not order_no:
        return None
    for status in CLOUD_READ_STATUSES:
        for order in fetch_cloud_dealer_orders(status, page_size=100, max_pages=5):
            if _clean(_pick(order, "order_no", "orderNo", "id")) == order_no:
                return order
    return None


def push_cloud_completed_state(
    order_no: str,
    contract_no: str = "",
    operator: str = "",
    v7_order_no: str = "",
    idempotency_key_prefix: str | None = None,
) -> dict[str, Any]:
    """Move a cloud order to completed, filling missing intermediate V7 states only at completion time."""
    order_no = _clean(order_no)
    contract_no = _clean(contract_no)
    operator = _clean(operator) or "system"
    v7_order_no = _clean(v7_order_no)
    cloud_order = find_cloud_dealer_order(order_no)
    if not cloud_order:
        return {"skipped": True, "reason": "cloud_order_not_found", "order_no": order_no}

    statuses = {_normalize_status(item.get("status") or cloud_order.get("status")) for item in _iter_cloud_items(cloud_order)}
    steps: list[str] = []

    if statuses == {"pending"}:
        push_cloud_review(
            order_no,
            "approved",
            reviewer=operator,
            note="V7 completed sync",
            idempotency_key=f"{idempotency_key_prefix}-review" if idempotency_key_prefix else None,
        )
        statuses = {"approved"}
        steps.append("review")

    if contract_no and statuses == {"approved"}:
        push_cloud_contract(
            order_no,
            contract_no=contract_no,
            operator=operator,
            v7_order_no=v7_order_no,
            idempotency_key=f"{idempotency_key_prefix}-contract" if idempotency_key_prefix else None,
        )
        statuses = {"contracted"}
        steps.append("contract")

    result = push_cloud_complete(
        order_no,
        operator=operator,
        v7_order_no=v7_order_no,
        idempotency_key=f"{idempotency_key_prefix}-complete" if idempotency_key_prefix else None,
    )
    result["steps"] = steps + ["complete"]
    return result


def refresh_local_wechat_batch_summary() -> dict[str, Any]:
    """Rebuild the local mini-program inventory read model from finished_goods_data."""
    with get_engine().begin() as conn:
        _ensure_wechat_batch_summary_schema(conn)
        try:
            conn.execute(text("CALL `refresh_wechat_batch_summary_all`()"))
        except Exception:
            has_order_remark = conn.execute(
                text("SHOW COLUMNS FROM finished_goods_data LIKE '订单备注'")
            ).fetchone() is not None
            order_remark_high_clause = (
                "OR TRIM(COALESCE(`订单备注`, '')) LIKE '%加高%'"
                if has_order_remark
                else ""
            )

            conn.execute(text("TRUNCATE TABLE wechat_batch_summary"))
            conn.execute(
                text(
                    f"""
                    INSERT INTO wechat_batch_summary
                      (summary_id, batch_no, expected_inbound_time, model, quantity,
                       heightened, original_batch_no, original_expected_inbound_time,
                       `批次号`, `预计入库时间`, `机型`, `数量`)
                    SELECT
                      MD5(CONCAT(
                        s.batch_no, '|',
                        COALESCE(DATE_FORMAT(s.expected_inbound_time, '%Y-%m-%d %H:%i:%s'), ''),
                        '|', s.model, '|', s.heightened, '|', COALESCE(s.original_batch_no, '')
                      )) AS summary_id,
                      s.batch_no,
                      s.expected_inbound_time,
                      s.model,
                      s.quantity,
                      s.heightened,
                      s.original_batch_no,
                      s.original_expected_inbound_time,
                      s.batch_no,
                      s.expected_inbound_time,
                      s.model,
                      s.quantity
                    FROM (
                      SELECT
                        IF(raw.is_high, '加高', raw.source_batch_no) AS batch_no,
                        raw.source_expected_inbound_time AS expected_inbound_time,
                        raw.base_model AS model,
                        COUNT(*) AS quantity,
                        IF(raw.is_high, 1, 0) AS heightened,
                        IF(raw.is_high, raw.source_batch_no, '') AS original_batch_no,
                        IF(raw.is_high, raw.source_expected_inbound_time, NULL) AS original_expected_inbound_time
                      FROM (
                        SELECT
                          TRIM(`批次号`) AS source_batch_no,
                          `预计入库时间` AS source_expected_inbound_time,
                          TRIM(REPLACE(REPLACE(TRIM(`机型`), '(加高)', ''), '加高', '')) AS base_model,
                          (
                            TRIM(COALESCE(`机型`, '')) LIKE '%加高%'
                            OR TRIM(COALESCE(`批次号`, '')) LIKE '%附加%'
                            OR TRIM(COALESCE(`批次号`, '')) LIKE '%加高%'
                            OR TRIM(COALESCE(`合同备注`, '')) LIKE '%加高%'
                            {order_remark_high_clause}
                          ) AS is_high
                        FROM finished_goods_data
                        WHERE NULLIF(TRIM(COALESCE(`批次号`, '')), '') IS NOT NULL
                          AND NULLIF(TRIM(COALESCE(`机型`, '')), '') IS NOT NULL
                          AND TRIM(COALESCE(`状态`, '')) = '待入库'
                      ) raw
                      WHERE NULLIF(raw.base_model, '') IS NOT NULL
                      GROUP BY raw.source_batch_no, raw.source_expected_inbound_time, raw.base_model, raw.is_high
                      UNION ALL
                      SELECT
                        IF(raw.is_high, '加高', '库存中') AS batch_no,
                        CAST(NULL AS DATETIME) AS expected_inbound_time,
                        raw.base_model AS model,
                        COUNT(*) AS quantity,
                        IF(raw.is_high, 1, 0) AS heightened,
                        IF(raw.is_high, COALESCE(NULLIF(raw.source_batch_no, ''), '库存中'), '') AS original_batch_no,
                        CAST(NULL AS DATETIME) AS original_expected_inbound_time
                      FROM (
                        SELECT
                          TRIM(COALESCE(`批次号`, '')) AS source_batch_no,
                          TRIM(REPLACE(REPLACE(TRIM(`机型`), '(加高)', ''), '加高', '')) AS base_model,
                          (
                            TRIM(COALESCE(`机型`, '')) LIKE '%加高%'
                            OR TRIM(COALESCE(`批次号`, '')) LIKE '%附加%'
                            OR TRIM(COALESCE(`批次号`, '')) LIKE '%加高%'
                            OR TRIM(COALESCE(`合同备注`, '')) LIKE '%加高%'
                            {order_remark_high_clause}
                          ) AS is_high
                        FROM finished_goods_data
                        WHERE NULLIF(TRIM(COALESCE(`机型`, '')), '') IS NOT NULL
                          AND TRIM(COALESCE(`状态`, '')) = '库存中'
                      ) raw
                      WHERE NULLIF(raw.base_model, '') IS NOT NULL
                      GROUP BY raw.base_model, raw.is_high, IF(raw.is_high, COALESCE(NULLIF(raw.source_batch_no, ''), '库存中'), '')
                    ) s
                    ON DUPLICATE KEY UPDATE
                      batch_no = VALUES(batch_no),
                      expected_inbound_time = VALUES(expected_inbound_time),
                      model = VALUES(model),
                      quantity = VALUES(quantity),
                      heightened = VALUES(heightened),
                      original_batch_no = VALUES(original_batch_no),
                      original_expected_inbound_time = VALUES(original_expected_inbound_time),
                      `批次号` = VALUES(`批次号`),
                      `预计入库时间` = VALUES(`预计入库时间`),
                      `机型` = VALUES(`机型`),
                      `数量` = VALUES(`数量`)
                    """
                )
            )
            conn.execute(
                text(
                    """
                    UPDATE wechat_batch_summary
                    SET `批次号` = batch_no,
                        `预计入库时间` = expected_inbound_time,
                        `机型` = model,
                        `数量` = quantity
                    """
                )
            )
        total = conn.execute(text("SELECT COUNT(*) FROM wechat_batch_summary")).scalar() or 0
    return {"refreshed": True, "rows": int(total)}


def fetch_local_wechat_batch_summary() -> list[dict[str, Any]]:
    with get_engine().begin() as conn:
        _ensure_wechat_batch_summary_schema(conn)
        rows = conn.execute(
            text(
                """
                SELECT
                  summary_id,
                  batch_no,
                  expected_inbound_time,
                  model,
                  quantity,
                  heightened,
                  original_batch_no,
                  original_expected_inbound_time,
                  updated_at
                FROM wechat_batch_summary
                ORDER BY batch_no, expected_inbound_time, model
                """
            )
        ).mappings().all()
    return [{key: _jsonable(value) for key, value in row.items()} for row in rows]


def push_wechat_batch_summary_to_cloud(rows: list[dict[str, Any]], idempotency_key: str | None = None) -> dict[str, Any]:
    base_url, api_key = _cloud_config()
    client = _get_http_client()
    response = client.post(
        f"{base_url}/api/v7/wechat-batch-summary/sync",
        headers={"Idempotency-Key": idempotency_key or f"v8-outbox-wechat-batch-summary-{datetime.now().strftime('%Y%m%d%H%M%S')}"},
        json={"mode": "replace", "rows": rows},
        timeout=60.0,
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


def sync_completed_dealer_orders_to_cloud(limit: int = 200) -> dict[str, Any]:
    ensure_dealer_order_tables()
    limit = min(max(1, int(limit or 200)), 1000)
    rows: list[dict[str, Any]] = []
    with get_engine().begin() as conn:
        result = conn.execute(
            text(
                """
                SELECT
                  order_no,
                  COALESCE(MAX(contract_no), '') AS contract_no,
                  COALESCE(MAX(v7_order_no), '') AS v7_order_no
                FROM dealer_orders
                WHERE status='completed'
                GROUP BY order_no
                ORDER BY MAX(updated_at) DESC
                LIMIT :limit
                """
            ),
            {"limit": limit},
        ).mappings()
        rows = [dict(row) for row in result]

    pushed = 0
    skipped = 0
    failed: list[dict[str, Any]] = []
    for row in rows:
        order_no = _clean(row.get("order_no"))
        if not order_no:
            skipped += 1
            continue
        try:
            result = push_cloud_completed_state(
                order_no,
                contract_no=_clean(row.get("contract_no")),
                operator="system",
                v7_order_no=_clean(row.get("v7_order_no")),
            )
            if result.get("skipped"):
                skipped += 1
            else:
                pushed += 1
        except Exception as exc:
            failed.append({"order_no": order_no, "error": str(exc)})

    return {
        "message": "completed dealer orders synced",
        "scanned": len(rows),
        "pushed": pushed,
        "skipped": skipped,
        "failed": failed,
    }


def _line_payload(item: dict[str, Any], order: dict[str, Any]) -> dict[str, Any]:
    status = _normalize_status(_pick(item, "status") or _pick(order, "status"))
    quantity = max(1, _as_int(_pick(item, "quantity"), 1))
    extra_remark = _clean(
        _pick(item, "factory_remark", "factoryRemark")
        or _pick(item, "extra_remark", "extraRemark")
        or _pick(order, "factory_remark", "factoryRemark")
        or _pick(order, "extra_remark", "extraRemark")
    )
    ermq = max(0, _as_int(_pick(item, "ERMQ", "ermq"), 0))
    if extra_remark and ermq <= 0:
        ermq = quantity
    return {
        "order_no": _clean(_pick(item, "order_no", "orderNo", "id") or _pick(order, "order_no", "orderNo", "id")),
        "line_no": max(1, _as_int(_pick(item, "line_no", "lineNo"), 1)),
        "dealer_id": _clean(_pick(item, "dealer_id", "dealerId") or _pick(order, "dealer_id", "dealerId")),
        "dealer_name": _clean(_pick(item, "dealer_name", "dealerName") or _pick(order, "dealer_name", "dealerName")),
        "dealer_phone": _clean(_pick(item, "dealer_phone", "dealerPhone") or _pick(order, "dealer_phone", "dealerPhone")),
        "regional_manager_name": _clean(_pick(item, "regional_manager_name", "regionalManagerName") or _pick(order, "regional_manager_name", "regionalManagerName")),
        "customer_name": _clean(_pick(item, "customer_name", "customerName") or _pick(order, "customer_name", "customerName")),
        "contact_name": _clean(_pick(item, "contact_name", "contactName") or _pick(order, "contact_name", "contactName")),
        "contact_phone": _clean(_pick(item, "contact_phone", "contactPhone") or _pick(order, "contact_phone", "contactPhone")),
        "model": _clean(_pick(item, "model")),
        "batch_no": _clean(_pick(item, "batch_no", "batchNo")),
        "eta": _clean(_pick(item, "eta", "expected_inbound_time", "expectedInboundTime")),
        "inventory_type": _clean(_pick(item, "inventory_type", "inventoryType")),
        "quantity": quantity,
        "approved_qty": max(0, _as_int(_pick(item, "approved_qty", "approvedQty"), 0)),
        "allocated_qty": max(0, _as_int(_pick(item, "allocated_qty", "allocatedQty"), 0)),
        "delivery_date": _clean(_pick(item, "delivery_date", "deliveryDate") or _pick(order, "delivery_date", "deliveryDate")),
        "remark": _clean(_pick(item, "remark") or _pick(order, "remark")),
        "extra_remark": extra_remark,
        "ERMQ": ermq,
        "factory_pending": 1 if _as_int(_pick(item, "factory_pending", "factoryPending", default=_pick(order, "factory_pending", "factoryPending")), 0) else 0,
        "source": _clean(_pick(item, "source") or _pick(order, "source") or "wechat"),
        "last_synced_at": _clean(_pick(item, "last_synced_at", "lastSyncedAt") or _pick(order, "last_synced_at", "lastSyncedAt")) or None,
        "sync_status": _clean(_pick(item, "sync_status", "syncStatus") or _pick(order, "sync_status", "syncStatus") or "pending"),
        "sync_error": _clean(_pick(item, "sync_error", "syncError") or _pick(order, "sync_error", "syncError")),
        "factory_reviewed_at": _clean(_pick(item, "factory_reviewed_at", "factoryReviewedAt") or _pick(order, "factory_reviewed_at", "factoryReviewedAt")) or None,
        "factory_reviewed_by": _clean(_pick(item, "factory_reviewed_by", "factoryReviewedBy") or _pick(order, "factory_reviewed_by", "factoryReviewedBy")),
        "extra_remark_reviewed_at": _clean(_pick(item, "extra_remark_reviewed_at", "extraRemarkReviewedAt") or _pick(order, "extra_remark_reviewed_at", "extraRemarkReviewedAt")) or None,
        "extra_remark_reviewed_by": _clean(_pick(item, "extra_remark_reviewed_by", "extraRemarkReviewedBy") or _pick(order, "extra_remark_reviewed_by", "extraRemarkReviewedBy")),
        "status": status,
        "regional_review_status": _clean(_pick(item, "regional_review_status", "regionalReviewStatus") or _pick(order, "regional_review_status", "regionalReviewStatus")),
        "regional_review_note": _clean(_pick(item, "regional_review_note", "regionalReviewNote") or _pick(order, "regional_review_note", "regionalReviewNote")),
        "regional_reviewed_by": _clean(_pick(item, "regional_reviewed_by", "regionalReviewedBy") or _pick(order, "regional_reviewed_by", "regionalReviewedBy")),
        "regional_reviewed_at": _clean(_pick(item, "regional_reviewed_at", "regionalReviewedAt") or _pick(order, "regional_reviewed_at", "regionalReviewedAt")) or None,
        "reviewed_at": _clean(_pick(item, "reviewed_at", "reviewedAt") or _pick(order, "reviewed_at", "reviewedAt")) or None,
        "reviewed_by": _clean(_pick(item, "reviewed_by", "reviewedBy") or _pick(order, "reviewed_by", "reviewedBy")),
        "contract_no": _clean(_pick(item, "contract_no", "contractNo") or _pick(order, "contract_no", "contractNo")),
        "v7_order_no": _clean(_pick(item, "v7_order_no", "v7OrderNo") or _pick(order, "v7_order_no", "v7OrderNo")),
        "review_note": _clean(_pick(item, "review_note", "reviewNote") or _pick(order, "review_note", "reviewNote")),
        "created_at": _clean(_pick(item, "created_at", "createdAt") or _pick(order, "created_at", "createdAt")) or None,
        "updated_at": _clean(_pick(item, "updated_at", "updatedAt") or _pick(order, "updated_at", "updatedAt")) or None,
    }


def _batch_load_existing(
    conn: Any, keys: list[tuple[str, int]], batch_size: int = 200
) -> dict[tuple[str, int], dict[str, Any]]:
    """Batch-load existing dealer_orders rows for the given (order_no, line_no) keys."""
    _EXISTING_FIELDS = (
        "order_no, line_no, status, approved_qty, allocated_qty, reviewed_at, reviewed_by, "
        "contract_no, v7_order_no, review_note, extra_remark, ERMQ, factory_pending, "
        "source, last_synced_at, sync_status, sync_error, "
        "factory_reviewed_at, factory_reviewed_by, "
        "extra_remark_reviewed_at, extra_remark_reviewed_by"
    )
    result: dict[tuple[str, int], dict[str, Any]] = {}
    for i in range(0, len(keys), batch_size):
        batch = keys[i : i + batch_size]
        placeholders = ", ".join(f"(:on{j}, :ln{j})" for j in range(len(batch)))
        params: dict[str, Any] = {}
        for j, (on, ln) in enumerate(batch):
            params[f"on{j}"] = on
            params[f"ln{j}"] = ln
        rows = conn.execute(
            text(
                f"SELECT {_EXISTING_FIELDS} FROM dealer_orders "
                f"WHERE (order_no, line_no) IN ({placeholders})"
            ),
            params,
        ).mappings().all()
        for row in rows:
            result[(_clean(row["order_no"]), int(row["line_no"]))] = dict(row)
    return result


def _prune_cloud_deleted_local_orders(conn: Any, cloud_order_nos: set[str]) -> dict[str, int]:
    """Remove local WeChat mirror rows whose cloud-side order now returns 404."""
    rows = conn.execute(
        text(
            """
            SELECT DISTINCT biz_key
            FROM cloud_sync_outbox
            WHERE status = 'failed'
              AND last_error LIKE 'cloud order not found (404):%'
            """
        )
    ).fetchall()
    stale_order_nos = [
        _clean(row[0])
        for row in rows
        if _clean(row[0]) and _clean(row[0]) not in cloud_order_nos
    ]
    if not stale_order_nos:
        return {"orders": 0, "lines": 0}

    deleted_lines = conn.execute(
        text(
            """
            DELETE FROM dealer_orders
            WHERE source = 'wechat'
              AND status NOT IN ('complete', 'completed')
              AND order_no IN :order_nos
            """
        ).bindparams(bindparam("order_nos", expanding=True)),
        {"order_nos": stale_order_nos},
    ).rowcount

    conn.execute(
        text(
            """
            UPDATE cloud_sync_outbox
            SET status = 'synced',
                last_error = NULL,
                next_retry_at = NULL,
                synced_at = NOW()
            WHERE status = 'failed'
              AND last_error LIKE 'cloud order not found (404):%'
              AND biz_key IN :order_nos
            """
        ).bindparams(bindparam("order_nos", expanding=True)),
        {"order_nos": stale_order_nos},
    )

    return {"orders": len(stale_order_nos), "lines": int(deleted_lines or 0)}


def sync_cloud_dealer_orders(status: str = "pending", page_size: int = 100, max_pages: int = 20) -> dict[str, Any]:
    ensure_dealer_order_tables()
    orders = fetch_cloud_dealer_orders(status=status, page_size=page_size, max_pages=max_pages)
    inserted = 0
    updated = 0
    skipped = 0
    seen_lines: set[tuple[str, int]] = set()
    seen_order_nos: set[str] = set()
    pending_order_nos: set[str] = set()
    pruned = {"orders": 0, "lines": 0}

    # Phase 1: Build all payloads and collect unique keys
    all_payloads: list[tuple[tuple[str, int], dict[str, Any]]] = []
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
            seen_order_nos.add(order_no)
            all_payloads.append((key, payload))

    with get_engine().begin() as conn:
        # Phase 2: Batch-load all existing records (replaces N+1 SELECTs)
        existing_map = _batch_load_existing(conn, [k for k, _ in all_payloads])

        # Phase 3: Process each payload using the pre-loaded map
        for key, payload in all_payloads:
            order_no, line_no = key
            existing = existing_map.get(key)

            if existing:
                local_status = _clean(existing.get("status"))
                is_completed = local_status in {"complete", "completed"}
                extra_changed = (
                    _clean(existing.get("extra_remark")) != payload["extra_remark"]
                    or _as_int(existing.get("ERMQ")) != payload["ERMQ"]
                )
                if _status_rank(local_status) > _status_rank(payload["status"]):
                    payload["status"] = local_status
                    payload["approved_qty"] = max(_as_int(existing.get("approved_qty")), payload["approved_qty"])
                    payload["allocated_qty"] = max(_as_int(existing.get("allocated_qty")), payload["allocated_qty"])
                if is_completed:
                    payload["status"] = local_status
                    payload["extra_remark"] = _clean(existing.get("extra_remark"))
                    payload["ERMQ"] = _as_int(existing.get("ERMQ"))
                    payload["factory_pending"] = _as_int(existing.get("factory_pending"))
                elif extra_changed:
                    payload["factory_pending"] = 1
                    pending_order_nos.add(order_no)
                for field in (
                    "reviewed_at",
                    "reviewed_by",
                    "contract_no",
                    "v7_order_no",
                    "review_note",
                    "last_synced_at",
                    "factory_reviewed_at",
                    "factory_reviewed_by",
                    "extra_remark_reviewed_at",
                    "extra_remark_reviewed_by",
                ):
                    if existing.get(field) and not payload.get(field):
                        payload[field] = existing.get(field)
                if existing.get("source") and payload.get("source") == "wechat":
                    payload["source"] = existing.get("source")
                if existing.get("sync_status") and payload.get("sync_status") == "pending":
                    payload["sync_status"] = existing.get("sync_status")
                if existing.get("sync_error") and not payload.get("sync_error"):
                    payload["sync_error"] = existing.get("sync_error")
                conn.execute(
                    text(
                        """
                        UPDATE dealer_orders
                        SET dealer_id=:dealer_id, dealer_name=:dealer_name, dealer_phone=:dealer_phone,
                            regional_manager_name=:regional_manager_name,
                            customer_name=:customer_name, contact_name=:contact_name, contact_phone=:contact_phone,
                            model=:model, batch_no=:batch_no, eta=:eta, inventory_type=:inventory_type,
                            quantity=:quantity, approved_qty=:approved_qty, allocated_qty=:allocated_qty,
                            delivery_date=:delivery_date, remark=:remark,
                            extra_remark=:extra_remark, ERMQ=:ERMQ, factory_pending=:factory_pending,
                            source=:source,
                            last_synced_at=:last_synced_at,
                            sync_status=:sync_status,
                            sync_error=:sync_error,
                            factory_reviewed_at=:factory_reviewed_at,
                            factory_reviewed_by=:factory_reviewed_by,
                            extra_remark_reviewed_at=:extra_remark_reviewed_at,
                            extra_remark_reviewed_by=:extra_remark_reviewed_by,
                            status=:status,
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
                if payload["status"] not in {"complete", "completed"} and (
                    payload["extra_remark"] or payload["ERMQ"] > 0 or payload["factory_pending"]
                ):
                    payload["factory_pending"] = 1
                    pending_order_nos.add(order_no)
                conn.execute(
                    text(
                        """
                        INSERT INTO dealer_orders
                        (order_no, line_no, dealer_id, dealer_name, dealer_phone, regional_manager_name,
                         customer_name, contact_name, contact_phone, model, batch_no, eta, inventory_type,
                         quantity, approved_qty, allocated_qty, delivery_date, remark,
                         extra_remark, ERMQ, factory_pending,
                         source, last_synced_at, sync_status, sync_error,
                         factory_reviewed_at, factory_reviewed_by,
                         extra_remark_reviewed_at, extra_remark_reviewed_by,
                         status,
                         regional_review_status, regional_review_note, regional_reviewed_by, regional_reviewed_at,
                         reviewed_at, reviewed_by, contract_no, v7_order_no, review_note, created_at, updated_at)
                        VALUES
                        (:order_no, :line_no, :dealer_id, :dealer_name, :dealer_phone, :regional_manager_name,
                         :customer_name, :contact_name, :contact_phone, :model, :batch_no, :eta, :inventory_type,
                         :quantity, :approved_qty, :allocated_qty, :delivery_date, :remark,
                         :extra_remark, :ERMQ, :factory_pending,
                         :source, :last_synced_at, :sync_status, :sync_error,
                         :factory_reviewed_at, :factory_reviewed_by,
                         :extra_remark_reviewed_at, :extra_remark_reviewed_by,
                         :status,
                         :regional_review_status, :regional_review_note, :regional_reviewed_by, :regional_reviewed_at,
                         :reviewed_at, :reviewed_by, :contract_no, :v7_order_no, :review_note,
                         COALESCE(:created_at, NOW()), COALESCE(:updated_at, NOW()))
                        """
                    ),
                    payload,
                )
                inserted += 1

        for order_no in pending_order_nos:
            conn.execute(
                text(
                    "UPDATE dealer_orders SET factory_pending=1 "
                    "WHERE order_no=:order_no AND status NOT IN ('complete', 'completed')"
                ),
                {"order_no": order_no},
            )

        if _clean(status).lower() in {"", "all", "*"}:
            pruned = _prune_cloud_deleted_local_orders(conn, seen_order_nos)

    return {
        "message": "cloud dealer orders synced",
        "status": "all" if _clean(status).lower() in {"", "all", "*"} else _normalize_status(status),
        "orders_fetched": len(orders),
        "lines_seen": len(seen_lines),
        "inserted": inserted,
        "updated": updated,
        "skipped": skipped,
        "factory_pending_orders": len(pending_order_nos),
        "pruned_cloud_deleted_orders": pruned["orders"],
        "pruned_cloud_deleted_lines": pruned["lines"],
    }


async def cloud_pull_worker_loop() -> None:
    """
    Periodically pulls dealer orders from the cloud to the local database in a background thread.
    """
    import asyncio

    enabled_str = os.getenv("ENABLE_CLOUD_PULL", "true").strip().lower()
    if enabled_str not in {"1", "true", "yes", "on"}:
        logger.info("Cloud pull worker is disabled by ENABLE_CLOUD_PULL")
        return

    interval_str = os.getenv("CLOUD_PULL_INTERVAL_SECONDS", "60").strip()
    try:
        interval = max(10, int(interval_str))  # minimum 10 seconds to avoid overloading
    except ValueError:
        interval = 60

    logger.info("Cloud pull worker started (interval = %ds)", interval)

    while True:
        try:
            # run the blocking sync_cloud_dealer_orders in a threadpool to prevent blocking FastAPI
            res = await asyncio.to_thread(sync_cloud_dealer_orders, "all")
            logger.info(
                "Cloud pull synced successfully: fetched=%d, inserted=%d, updated=%d, skipped=%d",
                res.get("orders_fetched", 0),
                res.get("inserted", 0),
                res.get("updated", 0),
                res.get("skipped", 0),
            )
        except asyncio.CancelledError:
            logger.info("Cloud pull worker task cancelled")
            raise
        except Exception as exc:
            logger.error("Cloud pull worker tick failed: %s", exc)

        await asyncio.sleep(interval)
