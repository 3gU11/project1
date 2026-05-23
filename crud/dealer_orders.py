from __future__ import annotations

import json
from collections import OrderedDict
from math import ceil
from typing import Any

from sqlalchemy import bindparam, text

from database import get_engine
from crud.cloud_sync_outbox import (
    enqueue_wechat_batch_summary_sync,
    ensure_cloud_sync_outbox_table,
    insert_cloud_sync_event,
)


ACTIVE_HOLD_STATUSES = ("pending", "approved")

CONVERTIBLE_STATUSES = ("pending", "approved")


def _enqueue_cloud_sync(conn, event_type: str, order_no: str, payload: dict[str, Any]) -> None:
    event_id = f"v7-{event_type}-{__import__('uuid').uuid4().hex}"
    insert_cloud_sync_event(
        conn,
        event_id,
        event_type,
        order_no,
        json.dumps(payload, ensure_ascii=False, default=str),
    )


def ensure_dealer_order_tables() -> None:
    ensure_cloud_sync_outbox_table()
    with get_engine().begin() as conn:
        conn.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS dealer_order_sync_events (
                  id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
                  event_id VARCHAR(64) NOT NULL UNIQUE,
                  order_no VARCHAR(64) NOT NULL,
                  event_type VARCHAR(64) NOT NULL,
                  source VARCHAR(32) NOT NULL DEFAULT 'wechat',
                  payload_json JSON NOT NULL,
                  status VARCHAR(32) NOT NULL DEFAULT 'pending',
                  attempts INT NOT NULL DEFAULT 0,
                  last_error TEXT,
                  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                  acked_at DATETIME NULL,
                  INDEX idx_sync_events_order (order_no),
                  INDEX idx_sync_events_status (status, id)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
                """
            )
        )
        conn.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS dealer_orders (
                  id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
                  order_no VARCHAR(64) NOT NULL,
                  line_no INT NOT NULL DEFAULT 1,
                  dealer_id VARCHAR(128) NOT NULL,
                  dealer_name VARCHAR(255) NOT NULL,
                  dealer_phone VARCHAR(64) DEFAULT '',
                  customer_name VARCHAR(255) NOT NULL,
                  contact_name VARCHAR(128) NOT NULL,
                  contact_phone VARCHAR(64) NOT NULL,
                  model VARCHAR(255) NOT NULL,
                  batch_no VARCHAR(255) DEFAULT '',
                  eta VARCHAR(64) DEFAULT '',
                  inventory_type VARCHAR(32) DEFAULT '',
                  quantity INT NOT NULL DEFAULT 1,
                  approved_qty INT NOT NULL DEFAULT 0,
                  allocated_qty INT NOT NULL DEFAULT 0,
                  delivery_date VARCHAR(64) DEFAULT '',
                  remark TEXT,
                  extra_remark TEXT,
                  ERMQ INT NOT NULL DEFAULT 0,
                  factory_pending TINYINT(1) NOT NULL DEFAULT 0,
                  source VARCHAR(32) NOT NULL DEFAULT 'wechat',
                  last_synced_at DATETIME NULL,
                  sync_status VARCHAR(32) NOT NULL DEFAULT 'pending',
                  sync_error TEXT,
                  factory_reviewed_at DATETIME NULL,
                  factory_reviewed_by VARCHAR(128) DEFAULT '',
                  extra_remark_reviewed_at DATETIME NULL,
                  extra_remark_reviewed_by VARCHAR(128) DEFAULT '',
                  status VARCHAR(32) NOT NULL DEFAULT 'pending',
                  reviewed_at DATETIME NULL,
                  reviewed_by VARCHAR(128) DEFAULT '',
                  contract_no VARCHAR(128) DEFAULT '',
                  v7_order_no VARCHAR(128) DEFAULT '',
                  review_note TEXT,
                  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                  updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                  UNIQUE KEY uq_dealer_order_line (order_no, line_no),
                  INDEX idx_dealer_order_no (order_no),
                  INDEX idx_dealer_id (dealer_id),
                  INDEX idx_status (status),
                  INDEX idx_batch_model_status (batch_no, model, status),
                  INDEX idx_created_at (created_at)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
                """
            )
        )
        columns = {row[0] for row in conn.execute(text("SHOW COLUMNS FROM dealer_orders")).fetchall()}
        additions = [
            ("line_no", "ALTER TABLE dealer_orders ADD COLUMN line_no INT NOT NULL DEFAULT 1 AFTER order_no"),
            ("regional_manager_name", "ALTER TABLE dealer_orders ADD COLUMN regional_manager_name VARCHAR(128) DEFAULT '' AFTER dealer_phone"),
            ("approved_qty", "ALTER TABLE dealer_orders ADD COLUMN approved_qty INT NOT NULL DEFAULT 0 AFTER quantity"),
            ("allocated_qty", "ALTER TABLE dealer_orders ADD COLUMN allocated_qty INT NOT NULL DEFAULT 0 AFTER approved_qty"),
            ("reviewed_at", "ALTER TABLE dealer_orders ADD COLUMN reviewed_at DATETIME NULL AFTER status"),
            ("reviewed_by", "ALTER TABLE dealer_orders ADD COLUMN reviewed_by VARCHAR(128) DEFAULT '' AFTER reviewed_at"),
            ("contract_no", "ALTER TABLE dealer_orders ADD COLUMN contract_no VARCHAR(128) DEFAULT '' AFTER reviewed_by"),
            ("v7_order_no", "ALTER TABLE dealer_orders ADD COLUMN v7_order_no VARCHAR(128) DEFAULT '' AFTER contract_no"),
            ("review_note", "ALTER TABLE dealer_orders ADD COLUMN review_note TEXT AFTER v7_order_no"),
            ("extra_remark", "ALTER TABLE dealer_orders ADD COLUMN extra_remark TEXT AFTER remark"),
            ("ERMQ", "ALTER TABLE dealer_orders ADD COLUMN ERMQ INT NOT NULL DEFAULT 0 AFTER extra_remark"),
            ("factory_pending", "ALTER TABLE dealer_orders ADD COLUMN factory_pending TINYINT(1) NOT NULL DEFAULT 0 AFTER ERMQ"),
            ("source", "ALTER TABLE dealer_orders ADD COLUMN source VARCHAR(32) NOT NULL DEFAULT 'wechat' AFTER factory_pending"),
            ("last_synced_at", "ALTER TABLE dealer_orders ADD COLUMN last_synced_at DATETIME NULL AFTER source"),
            ("sync_status", "ALTER TABLE dealer_orders ADD COLUMN sync_status VARCHAR(32) NOT NULL DEFAULT 'pending' AFTER last_synced_at"),
            ("sync_error", "ALTER TABLE dealer_orders ADD COLUMN sync_error TEXT AFTER sync_status"),
            ("factory_reviewed_at", "ALTER TABLE dealer_orders ADD COLUMN factory_reviewed_at DATETIME NULL AFTER sync_error"),
            ("factory_reviewed_by", "ALTER TABLE dealer_orders ADD COLUMN factory_reviewed_by VARCHAR(128) DEFAULT '' AFTER factory_reviewed_at"),
            ("extra_remark_reviewed_at", "ALTER TABLE dealer_orders ADD COLUMN extra_remark_reviewed_at DATETIME NULL AFTER factory_reviewed_by"),
            ("extra_remark_reviewed_by", "ALTER TABLE dealer_orders ADD COLUMN extra_remark_reviewed_by VARCHAR(128) DEFAULT '' AFTER extra_remark_reviewed_at"),
            ("regional_review_status", "ALTER TABLE dealer_orders ADD COLUMN regional_review_status VARCHAR(32) DEFAULT '' AFTER status"),
            ("regional_review_note", "ALTER TABLE dealer_orders ADD COLUMN regional_review_note TEXT AFTER regional_review_status"),
            ("regional_reviewed_by", "ALTER TABLE dealer_orders ADD COLUMN regional_reviewed_by VARCHAR(128) DEFAULT '' AFTER regional_review_note"),
            ("regional_reviewed_at", "ALTER TABLE dealer_orders ADD COLUMN regional_reviewed_at DATETIME NULL AFTER regional_reviewed_by"),
        ]
        for column, sql in additions:
            if column not in columns:
                conn.execute(text(sql))

        indexes = {row[2] for row in conn.execute(text("SHOW INDEX FROM dealer_orders")).fetchall()}
        for index_name in ("order_no", "uq_order_no"):
            if index_name in indexes:
                conn.execute(text(f"ALTER TABLE dealer_orders DROP INDEX {index_name}"))
        indexes = {row[2] for row in conn.execute(text("SHOW INDEX FROM dealer_orders")).fetchall()}
        if "idx_dealer_order_no" not in indexes:
            conn.execute(text("ALTER TABLE dealer_orders ADD INDEX idx_dealer_order_no (order_no)"))
        if "uq_dealer_order_line" not in indexes:
            conn.execute(text("ALTER TABLE dealer_orders ADD UNIQUE KEY uq_dealer_order_line (order_no, line_no)"))


def _summary_batch_no(batch_no: object, inventory_type: object = "") -> str:
    raw_batch = str(batch_no or "").strip()
    raw_type = str(inventory_type or "").strip().lower()
    if raw_type == "finished" or raw_batch in {"FINISHED-STOCK", "库存中", "现货"}:
        return "库存中"
    return raw_batch


def _order_hold_batch_no(batch_no: object, inventory_type: object = "") -> str:
    raw_batch = str(batch_no or "").strip()
    raw_type = str(inventory_type or "").strip().lower()
    if raw_type == "finished" or raw_batch in {"FINISHED-STOCK", "库存中", "现货"}:
        return "FINISHED-STOCK"
    return raw_batch


def _row_to_dict(row: Any) -> dict:
    data = dict(row._mapping if hasattr(row, "_mapping") else row)
    for key, value in list(data.items()):
        if hasattr(value, "isoformat"):
            data[key] = value.isoformat(sep=" ") if hasattr(value, "hour") else value.isoformat()
    return data


def _delimited_match_sql(column_name: str, param_name: str) -> str:
    return (
        f"FIND_IN_SET(:{param_name}, "
        f"REPLACE(REPLACE(REPLACE(REPLACE(COALESCE({column_name}, ''), '，', '、'), ',', '、'), ' ', ''), '、', ',')"
        ") > 0"
    )


def get_pending_factory_review_lock(
    *,
    dealer_order_no: str = "",
    contract_nos: list[str] | None = None,
    sales_order_no: str = "",
) -> dict | None:
    """Return the pending dealer order that freezes this contract/order chain, if any."""
    ensure_dealer_order_tables()
    dealer_order_no = str(dealer_order_no or "").strip()
    sales_order_no = str(sales_order_no or "").strip()
    contract_values = [str(value or "").strip() for value in (contract_nos or []) if str(value or "").strip()]

    with get_engine().begin() as conn:
        if sales_order_no:
            rows = conn.execute(
                text(
                    "SELECT DISTINCT `合同号` FROM factory_plan "
                    "WHERE TRIM(COALESCE(`订单号`, '')) = :sales_order_no "
                    "AND COALESCE(TRIM(`合同号`), '') <> ''"
                ),
                {"sales_order_no": sales_order_no},
            ).fetchall()
            contract_values.extend(str(row[0] or "").strip() for row in rows if str(row[0] or "").strip())

        contract_values = list(OrderedDict.fromkeys(contract_values))
        clauses: list[str] = []
        params: dict[str, Any] = {}
        if dealer_order_no:
            clauses.append("order_no = :dealer_order_no")
            params["dealer_order_no"] = dealer_order_no
        if sales_order_no:
            clauses.append(_delimited_match_sql("v7_order_no", "sales_order_no"))
            params["sales_order_no"] = sales_order_no
        for idx, contract_no in enumerate(contract_values):
            key = f"contract_no_{idx}"
            clauses.append(_delimited_match_sql("contract_no", key))
            params[key] = contract_no

        if not clauses:
            return None

        row = conn.execute(
            text(
                "SELECT order_no, contract_no, v7_order_no, review_note "
                "FROM dealer_orders "
                "WHERE factory_pending = 1 "
                "AND status NOT IN ('complete', 'completed') "
                f"AND ({' OR '.join(clauses)}) "
                "ORDER BY updated_at DESC, id DESC LIMIT 1"
            ),
            params,
        ).mappings().first()
        return _row_to_dict(row) if row else None


def assert_no_pending_factory_review_lock(
    *,
    dealer_order_no: str = "",
    contract_nos: list[str] | None = None,
    sales_order_no: str = "",
    action: str = "操作",
) -> None:
    locked = get_pending_factory_review_lock(
        dealer_order_no=dealer_order_no,
        contract_nos=contract_nos,
        sales_order_no=sales_order_no,
    )
    if locked:
        order_no = str(locked.get("order_no") or "").strip()
        raise ValueError(f"当前合同/订单已冻结：经销商订单 {order_no} 有新备注待复审，复审通过后才可以{action}")


def _split_linked_values(raw_values: list[object]) -> list[str]:
    values: list[str] = []
    for raw in raw_values:
        text_value = str(raw or "").strip()
        if not text_value:
            continue
        for part in text_value.replace("，", "、").replace(",", "、").split("、"):
            value = part.strip()
            if value and value not in values:
                values.append(value)
    return values


def _cancel_linked_contract_order_chain(
    conn,
    *,
    order_no: str,
    items: list[dict],
    operator: str,
    reason: str,
) -> dict:
    contract_nos = _split_linked_values([item.get("contract_no") for item in items])
    sales_order_ids = _split_linked_values([item.get("v7_order_no") for item in items])

    if contract_nos:
        fp_order_rows = conn.execute(
            text(
                "SELECT DISTINCT `订单号` FROM factory_plan "
                "WHERE TRIM(COALESCE(`合同号`, '')) IN :contract_nos "
                "AND COALESCE(TRIM(`订单号`), '') <> ''"
            ).bindparams(bindparam("contract_nos", expanding=True)),
            {"contract_nos": contract_nos},
        ).fetchall()
        for row in fp_order_rows:
            order_id = str(row[0] or "").strip()
            if order_id and order_id not in sales_order_ids:
                sales_order_ids.append(order_id)

    released_serials: list[str] = []
    if sales_order_ids:
        fg_rows = conn.execute(
            text(
                "SELECT DISTINCT `流水号` FROM finished_goods_data "
                "WHERE TRIM(COALESCE(`占用订单号`, '')) IN :order_ids "
                "AND COALESCE(TRIM(`流水号`), '') <> '' "
                "AND TRIM(COALESCE(`状态`, '')) <> '已出库'"
            ).bindparams(bindparam("order_ids", expanding=True)),
            {"order_ids": sales_order_ids},
        ).fetchall()
        released_serials.extend(str(row[0] or "").strip() for row in fg_rows if str(row[0] or "").strip())

    if contract_nos:
        fg_rows = conn.execute(
            text(
                "SELECT DISTINCT `流水号` FROM finished_goods_data "
                "WHERE TRIM(COALESCE(`合同号`, '')) IN :contract_nos "
                "AND COALESCE(TRIM(`流水号`), '') <> '' "
                "AND TRIM(COALESCE(`状态`, '')) <> '已出库'"
            ).bindparams(bindparam("contract_nos", expanding=True)),
            {"contract_nos": contract_nos},
        ).fetchall()
        for row in fg_rows:
            serial = str(row[0] or "").strip()
            if serial and serial not in released_serials:
                released_serials.append(serial)

    if released_serials:
        conn.execute(
            text(
                """
                UPDATE finished_goods_data
                SET `状态` = CASE
                        WHEN COALESCE(TRIM(`Location_Code`), '') <> ''
                        THEN CONCAT('库存中（', TRIM(`Location_Code`), '）')
                        ELSE '待入库'
                    END,
                    `占用订单号` = '',
                    `客户` = '',
                    `代理商` = '',
                    `合同号` = '',
                    `更新时间` = NOW()
                WHERE `流水号` IN :serials
                """
            ).bindparams(bindparam("serials", expanding=True)),
            {"serials": released_serials},
        )
        conn.execute(
            text(
                """
                UPDATE units
                SET contract_no = NULL,
                    customer = NULL,
                    dealer_name = NULL,
                    sales_id = NULL,
                    due_date = NULL,
                    is_locked = 0
                WHERE serial_no IN :serials OR forecast_serial_no IN :serials
                """
            ).bindparams(bindparam("serials", expanding=True)),
            {"serials": released_serials},
        )
        try:
            from crud.logs import append_log

            append_log(f"经销商新备注复审驳回自动释放-{order_no}-退回待入库", released_serials, operator=operator)
        except Exception:
            pass

    if contract_nos:
        conn.execute(
            text(
                "UPDATE factory_plan SET `状态`='已取消' "
                "WHERE TRIM(COALESCE(`合同号`, '')) IN :contract_nos"
            ).bindparams(bindparam("contract_nos", expanding=True)),
            {"contract_nos": contract_nos},
        )
        conn.execute(
            text(
                "DELETE FROM production_queue "
                "WHERE TRIM(COALESCE(contract_no, '')) IN :contract_nos AND status = 'Waiting'"
            ).bindparams(bindparam("contract_nos", expanding=True)),
            {"contract_nos": contract_nos},
        )
        conn.execute(
            text(
                "UPDATE rush_order_queue SET status='deleted', updated_by=:operator "
                "WHERE TRIM(COALESCE(contract_no, '')) IN :contract_nos AND status='pending'"
            ).bindparams(bindparam("contract_nos", expanding=True)),
            {"contract_nos": contract_nos, "operator": operator},
        )
        conn.execute(
            text(
                """
                UPDATE units
                SET contract_no = NULL,
                    customer = NULL,
                    dealer_name = NULL,
                    sales_id = NULL,
                    due_date = NULL,
                    order_remark = NULL,
                    is_locked = 0
                WHERE TRIM(COALESCE(contract_no, '')) IN :contract_nos
                """
            ).bindparams(bindparam("contract_nos", expanding=True)),
            {"contract_nos": contract_nos},
        )

    if sales_order_ids:
        conn.execute(
            text(
                "UPDATE sales_orders SET status='deleted', delete_reason=:reason "
                "WHERE TRIM(COALESCE(`订单号`, '')) IN :order_ids"
            ).bindparams(bindparam("order_ids", expanding=True)),
            {
                "order_ids": sales_order_ids,
                "reason": f"经销商订单 {order_no} 新备注复审驳回：{reason}",
            },
        )
        conn.execute(
            text(
                """
                UPDATE units
                SET contract_no = NULL,
                    customer = NULL,
                    dealer_name = NULL,
                    sales_id = NULL,
                    due_date = NULL,
                    order_remark = NULL,
                    is_locked = 0
                WHERE TRIM(COALESCE(sales_id, '')) IN :order_ids
                """
            ).bindparams(bindparam("order_ids", expanding=True)),
            {"order_ids": sales_order_ids},
        )

    if contract_nos or sales_order_ids or released_serials:
        try:
            from crud.cloud_sync_outbox import enqueue_wechat_batch_summary_sync as _enqueue_batch_sync
            _enqueue_batch_sync("dealer_extra_review_rejected_cancel_chain")
        except Exception:
            pass  # non-critical: sync will be picked up by next batch
        try:
            import crud.inventory
            import crud.orders
            import crud.planning

            if hasattr(crud.inventory.get_data, "cache_clear"):
                crud.inventory.get_data.cache_clear()
            if hasattr(crud.orders.get_orders, "cache_clear"):
                crud.orders.get_orders.cache_clear()
            if hasattr(crud.orders.get_orders_v2, "cache_clear"):
                crud.orders.get_orders_v2.cache_clear()
            if hasattr(crud.planning.get_factory_plan, "cache_clear"):
                crud.planning.get_factory_plan.cache_clear()
            if hasattr(crud.planning.get_factory_plan_v2, "cache_clear"):
                crud.planning.get_factory_plan_v2.cache_clear()
        except Exception:
            pass

    return {
        "cancelled_contracts": contract_nos,
        "cancelled_orders": sales_order_ids,
        "released_serials": released_serials,
    }


def _status_rank(status: str) -> int:
    return {
        "pending": 0,
        "approved": 1,
        "contracted": 2,
        "partial_allocated": 3,
        "allocated": 4,
        "rejected": 5,
        "cancelled": 6,
        "complete": 7,
        "completed": 7,
    }.get(status or "", 9)


def _list_priority(order: dict) -> int:
    status = str(order.get("status") or "")
    if int(order.get("factory_pending") or 0) == 1 and status not in {"complete", "completed"}:
        return -1
    return _status_rank(status)


def _sort_review_list(grouped: list[dict]) -> None:
    grouped.sort(
        key=lambda order: (
            str(order.get("updated_at") or order.get("created_at") or ""),
            str(order.get("created_at") or ""),
            str(order.get("order_no") or ""),
        ),
        reverse=True,
    )
    grouped.sort(key=_list_priority)


def _aggregate_status(items: list[dict]) -> str:
    statuses = [str(item.get("status") or "") for item in items]
    if statuses and all(status in {"complete", "completed"} for status in statuses):
        return "completed"
    if statuses and all(status == "allocated" for status in statuses):
        return "allocated"
    if any(status == "allocated" or (int(item.get("allocated_qty") or 0) > 0 and status != "completed") for status, item in zip(statuses, items)):
        return "partial_allocated"
    if statuses and all(status == "rejected" for status in statuses):
        return "rejected"
    if statuses and all(status == "cancelled" for status in statuses):
        return "cancelled"
    if any(status == "contracted" for status in statuses):
        return "contracted"
    if any(status == "approved" for status in statuses):
        return "approved"
    return statuses[0] if statuses else "pending"


def _summarize_models(items: list[dict]) -> str:
    parts = []
    for item in items:
        model = str(item.get("model") or "-")
        qty = int(item.get("quantity") or 0)
        parts.append(f"{model}x{qty}")
    return " / ".join(parts)


def _summarize_batches(items: list[dict]) -> str:
    batches: list[str] = []
    for item in items:
        batch = str(item.get("batch_no") or "").strip() or "-"
        if batch not in batches:
            batches.append(batch)
    return " / ".join(batches)


def _summarize_text(items: list[dict], field: str) -> str:
    values: list[str] = []
    for item in items:
        value = str(item.get(field) or "").strip()
        if value and value not in values:
            values.append(value)
    return " ".join(values)


def _has_factory_remark(items: list[dict]) -> bool:
    return any(
        str(item.get("factory_remark") or item.get("extra_remark") or "").strip()
        for item in items
    )


def _group_orders(rows: list[dict]) -> list[dict]:
    grouped: OrderedDict[str, list[dict]] = OrderedDict()
    for row in rows:
        grouped.setdefault(str(row.get("order_no") or ""), []).append(row)

    orders = []
    for order_no, items in grouped.items():
        base = dict(items[0])
        base["order_no"] = order_no
        base["items"] = items
        base["line_count"] = len(items)
        base["model"] = _summarize_models(items)
        base["batch_no"] = _summarize_batches(items)
        base["remark"] = _summarize_text(items, "remark")
        base["extra_remark"] = _summarize_text(items, "extra_remark")
        base["factory_remark"] = base["extra_remark"]
        base["ERMQ"] = sum(int(item.get("ERMQ") or 0) for item in items)
        base["factory_pending"] = 1 if any(int(item.get("factory_pending") or 0) for item in items) else 0
        base["review_note"] = _summarize_text(items, "review_note")
        base["regional_review_note"] = _summarize_text(items, "regional_review_note")
        base["quantity"] = sum(int(item.get("quantity") or 0) for item in items)
        base["approved_qty"] = sum(int(item.get("approved_qty") or 0) for item in items)
        base["allocated_qty"] = sum(int(item.get("allocated_qty") or 0) for item in items)
        base["summary_qty"] = sum(int(item.get("summary_qty") or 0) for item in items)
        base["occupied_qty"] = sum(int(item.get("occupied_qty") or 0) for item in items)
        base["available_qty"] = min((int(item.get("available_qty") or 0) for item in items), default=0)
        base["status"] = _aggregate_status(items)
        orders.append(base)
    return orders


def list_dealer_orders(
    status: str = "",
    keyword: str = "",
    dealer_id: str = "",
    model: str = "",
    batch_no: str = "",
    date_from: str = "",
    date_to: str = "",
    page: int = 1,
    page_size: int = 50,
) -> dict:
    ensure_dealer_order_tables()
    page = max(1, int(page or 1))
    page_size = min(200, max(1, int(page_size or 50)))
    where = []
    params: dict[str, Any] = {}
    status_filter = str(status or "").strip()
    if dealer_id:
        where.append("dealer_id = :dealer_id")
        params["dealer_id"] = dealer_id
    if model:
        where.append("model = :model")
        params["model"] = model
    if batch_no:
        where.append("batch_no = :batch_no")
        params["batch_no"] = batch_no
    if date_from:
        where.append("created_at >= :date_from")
        params["date_from"] = date_from
    if date_to:
        where.append("created_at < DATE_ADD(:date_to, INTERVAL 1 DAY)")
        params["date_to"] = date_to
    if keyword:
        where.append(
            "("
            "order_no LIKE :kw OR dealer_name LIKE :kw OR regional_manager_name LIKE :kw OR customer_name LIKE :kw "
            "OR contact_phone LIKE :kw OR model LIKE :kw OR batch_no LIKE :kw"
            ")"
        )
        params["kw"] = f"%{keyword}%"
    where_sql = f"WHERE {' AND '.join(where)}" if where else ""
    with get_engine().begin() as conn:
        raw_rows = conn.execute(
            text(
                f"""
                SELECT id, order_no, line_no, dealer_id, dealer_name, dealer_phone, customer_name,
                       contact_name, contact_phone, model, batch_no, eta, inventory_type,
                       quantity, approved_qty, allocated_qty, delivery_date, remark,
                       extra_remark, ERMQ, factory_pending,
                       status, reviewed_at, reviewed_by, contract_no, v7_order_no, review_note,
                       regional_manager_name, regional_review_status, regional_review_note,
                       regional_reviewed_by, regional_reviewed_at,
                       source, last_synced_at, sync_status, sync_error,
                       factory_reviewed_at, factory_reviewed_by,
                       extra_remark_reviewed_at, extra_remark_reviewed_by,
                       created_at, updated_at
                FROM dealer_orders
                {where_sql}
                ORDER BY FIELD(status, 'pending', 'approved', 'contracted', 'partial_allocated', 'allocated', 'rejected', 'cancelled', 'completed'),
                         created_at DESC, order_no DESC, line_no ASC, id ASC
                """
            ),
            params,
        ).fetchall()
        # Group raw rows by order_no for per-order sync
        order_groups: OrderedDict[str, list[dict]] = OrderedDict()
        for row in raw_rows:
            item = _row_to_dict(row)
            order_groups.setdefault(str(item.get("order_no") or ""), []).append(item)

        # Auto-sync allocation status for contracted orders
        rows = []
        for order_no_key, items in order_groups.items():
            synced_items = _sync_allocation_status(conn, order_no_key, items)
            for item in synced_items:
                availability = get_availability(conn, item)
                item.update(
                    {
                        "summary_qty": availability["summary_qty"],
                        "occupied_qty": availability["occupied_qty"],
                        "available_qty": availability["available_for_current"],
                    }
                )
                rows.append(item)

    grouped = _group_orders(rows)
    if status_filter == "todo":
        grouped = [
            order
            for order in grouped
            if (
                int(order.get("factory_pending") or 0) == 1
                and str(order.get("status") or "") not in {"complete", "completed"}
            )
            or order.get("status") == "pending"
        ]
        _sort_review_list(grouped)
    elif status_filter == "factory_pending":
        grouped = [order for order in grouped if int(order.get("factory_pending") or 0) == 1 and str(order.get("status") or "") not in {"complete", "completed"}]
    elif status_filter:
        grouped = [order for order in grouped if order.get("status") == status_filter]
    else:
        _sort_review_list(grouped)
    total = len(grouped)
    offset = (page - 1) * page_size
    data = grouped[offset : offset + page_size]
    return {
        "data": data,
        "total": total,
        "page": page,
        "page_size": page_size,
        "pages": ceil(total / page_size) if page_size else 0,
    }


def _get_order_lines_for_update(conn, order_no: str) -> list[dict]:
    rows = conn.execute(
        text("SELECT * FROM dealer_orders WHERE order_no=:order_no ORDER BY line_no, id FOR UPDATE"),
        {"order_no": order_no},
    ).fetchall()
    if not rows:
        raise ValueError("订单不存在")
    return [_row_to_dict(row) for row in rows]


def get_availability(conn, order: dict) -> dict:
    summary_batch = _summary_batch_no(order.get("batch_no"), order.get("inventory_type"))
    hold_batch = _order_hold_batch_no(order.get("batch_no"), order.get("inventory_type"))
    model = str(order.get("model") or "").strip()
    summary_qty = int(
        conn.execute(
            text(
                "SELECT COALESCE(SUM(quantity), 0) FROM wechat_batch_summary "
                "WHERE batch_no=:batch_no AND model=:model"
            ),
            {"batch_no": summary_batch, "model": model},
        ).scalar()
        or 0
    )
    occupied_qty = int(
        conn.execute(
            text(
                "SELECT COALESCE(SUM(GREATEST(quantity - allocated_qty, 0)), 0) "
                "FROM dealer_orders "
                "WHERE batch_no=:batch_no AND model=:model "
                "AND status IN ('pending', 'approved') "
                "AND quantity > allocated_qty"
            ),
            {"batch_no": hold_batch, "model": model},
        ).scalar()
        or 0
    )
    current_unallocated = max(0, int(order.get("quantity") or 0) - int(order.get("allocated_qty") or 0))
    available_for_current = summary_qty - occupied_qty + current_unallocated
    return {
        "summary_batch_no": summary_batch,
        "order_batch_no": hold_batch,
        "model": model,
        "summary_qty": summary_qty,
        "occupied_qty": occupied_qty,
        "current_unallocated_qty": current_unallocated,
        "available_for_current": available_for_current,
    }


def _sync_allocation_status(conn, order_no: str, items: list[dict]) -> list[dict]:
    """Trace contract→sales_order→inventory to auto-sync allocated_qty and per-line status.

    Only operates on orders where status='contracted' and contract_no is non-empty.
    Returns the (possibly updated) items list.
    """
    if not items:
        return items
    if any(int(item.get("factory_pending") or 0) for item in items):
        return items
    first = items[0]
    status = str(first.get("status") or "")
    if status not in ("contracted", "partial_allocated", "allocated"):
        return items
    contract_nos_str = str(first.get("contract_no") or "").strip()
    if not contract_nos_str:
        return items

    # Split multiple contract IDs
    contract_nos = [cid.strip() for cid in contract_nos_str.replace("，", "、").split("、") if cid.strip()]
    if not contract_nos:
        return items

    # Build contract_no → set of order IDs mapping
    placeholders_c = ",".join([f":cid_{i}" for i in range(len(contract_nos))])
    params_c = {f"cid_{i}": cid for i, cid in enumerate(contract_nos)}
    fp_rows = conn.execute(
        text(
            f"SELECT `合同号`, `机型`, `订单号` FROM factory_plan "
            f"WHERE `合同号` IN ({placeholders_c}) AND `订单号` IS NOT NULL AND `订单号` != ''"
        ),
        params_c,
    ).fetchall()
    if not fp_rows:
        return items

    # contract_no → {model → set of order IDs}
    contract_model_orders: dict[str, dict[str, set[str]]] = {}
    for row in fp_rows:
        cid = str(row[0] or "").strip()
        model = str(row[1] or "").strip()
        order_id = str(row[2] or "").strip()
        if not cid or not model or not order_id:
            continue
        contract_model_orders.setdefault(cid, {}).setdefault(model, set()).add(order_id)

    # Collect all unique order IDs and check their statuses
    all_order_ids: set[str] = set()
    for model_map in contract_model_orders.values():
        for orders in model_map.values():
            all_order_ids.update(orders)
    if not all_order_ids:
        return items

    order_ids_list = list(all_order_ids)
    placeholders_o = ",".join([f":oid_{i}" for i in range(len(order_ids_list))])
    params_o = {f"oid_{i}": oid for i, oid in enumerate(order_ids_list)}
    so_rows = conn.execute(
        text(
            f"SELECT `订单号`, `status` FROM sales_orders WHERE `订单号` IN ({placeholders_o})"
        ),
        params_o,
    ).fetchall()
    order_status: dict[str, str] = {}
    for row in so_rows:
        order_status[str(row[0] or "").strip()] = str(row[1] or "").strip()

    # Count allocated/shipped machines per (order_id, model)
    if not order_ids_list:
        return items
    fg_rows = conn.execute(
        text(
            f"SELECT `占用订单号`, `机型`, COUNT(*) as cnt FROM finished_goods_data "
            f"WHERE `占用订单号` IN ({placeholders_o}) "
            f"AND `机型` IS NOT NULL AND `机型` != '' "
            f"AND `状态` IN ('待发货', '已出库') "
            f"GROUP BY `占用订单号`, `机型`"
        ),
        params_o,
    ).fetchall()
    allocation_count: dict[tuple[str, str], int] = {}
    for row in fg_rows:
        oid = str(row[0] or "").strip()
        model = str(row[1] or "").strip()
        cnt = int(row[2] or 0)
        allocation_count[(oid, model)] = allocation_count.get((oid, model), 0) + cnt

    # Compute per-line allocated_qty
    updated = False
    updated_items = []
    for item in items:
        item_contract_no = str(item.get("contract_no") or "").strip()
        item_cids = [c.strip() for c in item_contract_no.replace("，", "、").split("、") if c.strip()] if item_contract_no else []
        model = str(item.get("model") or "").strip()
        qty = int(item.get("quantity") or 0)

        # Find all order IDs for this line's model across all its contracts
        line_order_ids: set[str] = set()
        for cid in item_cids:
            model_map = contract_model_orders.get(cid, {})
            line_order_ids.update(model_map.get(model, set()))

        total_allocated = 0
        all_done = True
        for oid in line_order_ids:
            total_allocated += allocation_count.get((oid, model), 0)
            if order_status.get(oid, "") != "done":
                all_done = False

        new_item = dict(item)
        new_item["allocated_qty"] = min(total_allocated, qty)

        # Determine per-line status
        if total_allocated >= qty and all_done:
            new_item["status"] = "completed"
        elif total_allocated >= qty:
            new_item["status"] = "allocated"
        elif total_allocated > 0:
            new_item["status"] = "partial_allocated"
        # else keep as contracted

        if new_item.get("allocated_qty") != item.get("allocated_qty") or new_item.get("status") != item.get("status"):
            updated = True
        updated_items.append(new_item)

    # Persist changes to DB
    if updated:
        for item in updated_items:
            conn.execute(
                text(
                    "UPDATE dealer_orders SET allocated_qty=:allocated_qty, status=:status "
                    "WHERE id=:id"
                ),
                {
                    "allocated_qty": item["allocated_qty"],
                    "status": item["status"],
                    "id": item["id"],
                },
            )
        aggregate_status = _aggregate_status(updated_items)
        if aggregate_status in {"partial_allocated", "allocated"}:
            _enqueue_cloud_sync(
                conn,
                "dealer_order_allocated",
                order_no,
                {
                    "order_no": order_no,
                    "contract_no": str(first.get("contract_no") or "").strip(),
                    "operator": "system",
                    "v7_order_no": ",".join(sorted(all_order_ids)),
                },
            )

    return updated_items


def sync_dealer_order_statuses_by_sales_orders(sales_order_ids: list[str]) -> list[dict]:
    """Refresh dealer order line statuses for orders linked to the given V7 sales orders."""
    ensure_dealer_order_tables()
    order_ids = [str(order_id or "").strip() for order_id in sales_order_ids if str(order_id or "").strip()]
    if not order_ids:
        return []

    placeholders = ",".join([f":oid_{i}" for i in range(len(order_ids))])
    params = {f"oid_{i}": oid for i, oid in enumerate(order_ids)}
    synced: list[dict] = []

    with get_engine().begin() as conn:
        rows = conn.execute(
            text(
                f"""
                SELECT DISTINCT d.order_no
                FROM dealer_orders d
                JOIN factory_plan fp
                  ON FIND_IN_SET(
                    TRIM(fp.`合同号`) COLLATE utf8mb4_general_ci,
                    REPLACE(REPLACE(TRIM(COALESCE(d.contract_no, '')), '，', '、'), '、', ',') COLLATE utf8mb4_general_ci
                  ) > 0
                WHERE fp.`订单号` IN ({placeholders})
                  AND COALESCE(TRIM(d.contract_no), '') <> ''
                """
            ),
            params,
        ).fetchall()
        order_nos = [str(row[0] or "").strip() for row in rows if str(row[0] or "").strip()]

        for order_no in order_nos:
            line_rows = conn.execute(
                text("SELECT * FROM dealer_orders WHERE order_no=:order_no ORDER BY line_no, id"),
                {"order_no": order_no},
            ).fetchall()
            items = [_row_to_dict(row) for row in line_rows]
            if not items:
                continue
            updated_items = _sync_allocation_status(conn, order_no, items)
            status = _aggregate_status(updated_items)
            synced.append(
                {
                    "order_no": order_no,
                    "status": status,
                    "contract_no": "、".join(
                        sorted(
                            {
                                str(item.get("contract_no") or "").strip()
                                for item in updated_items
                                if str(item.get("contract_no") or "").strip()
                            }
                        )
                    ),
                    "v7_order_no": "、".join(order_ids),
                    "items": updated_items,
                }
            )

    return synced


def _decorate_items_with_availability(conn, items: list[dict]) -> list[dict]:
    decorated = []
    for item in items:
        availability = get_availability(conn, item)
        next_item = dict(item)
        next_item.update(
            {
                "summary_qty": availability["summary_qty"],
                "occupied_qty": availability["occupied_qty"],
                "available_qty": availability["available_for_current"],
            }
        )
        decorated.append(next_item)
    return decorated


def preview_dealer_order(order_no: str) -> dict:
    ensure_dealer_order_tables()
    with get_engine().begin() as conn:
        rows = conn.execute(
            text("SELECT * FROM dealer_orders WHERE order_no=:order_no ORDER BY line_no, id"),
            {"order_no": order_no},
        ).fetchall()
        if not rows:
            raise ValueError("订单不存在")
        raw_items = [_row_to_dict(row) for row in rows]
        synced_items = _sync_allocation_status(conn, order_no, raw_items)
        items = _decorate_items_with_availability(conn, synced_items)
        order = _group_orders(items)[0]
        can_approve = all(
            int(item.get("available_qty") or 0)
            >= max(0, int(item.get("quantity") or 0) - int(item.get("allocated_qty") or 0))
            for item in items
        )
        return {
            "order": order,
            "items": items,
            "availability": {"items": items},
            "summary_qty": order["summary_qty"],
            "occupied_qty": order["occupied_qty"],
            "available_qty": order["available_qty"],
            "can_approve": can_approve,
        }


def approve_dealer_order(order_no: str, reviewer: str, note: str = "") -> dict:
    ensure_dealer_order_tables()
    with get_engine().begin() as conn:
        items = _get_order_lines_for_update(conn, order_no)
        if any(item.get("status") != "pending" for item in items):
            raise ValueError("只有整张订单全部处于待审核时才可以通过")
        for item in items:
            availability = get_availability(conn, item)
            needed = max(0, int(item.get("quantity") or 0) - int(item.get("allocated_qty") or 0))
            if availability["available_for_current"] < needed:
                raise ValueError(
                    f"{item.get('model')} 可用数量不足：需要 {needed}，当前可用 {availability['available_for_current']}"
                )
        conn.execute(
            text(
                "UPDATE dealer_orders SET status='approved', approved_qty=quantity, "
                "reviewed_at=NOW(), reviewed_by=:reviewer, review_note=:note "
                "WHERE order_no=:order_no"
            ),
            {"order_no": order_no, "reviewer": reviewer, "note": note},
        )
        _enqueue_cloud_sync(
            conn,
            "dealer_order_reviewed",
            order_no,
            {"order_no": order_no, "status": "approved", "reviewer": reviewer, "note": note},
        )
        # Sync batch_no to factory_plan
        for item in items:
            batch_no = str(item.get("batch_no") or "").strip()
            if not batch_no or batch_no == "FINISHED-STOCK":
                continue
            _merge_batch_to_factory_plan(
                conn,
                model=str(item.get("model") or "").strip(),
                batch_no=batch_no,
                quantity=int(item.get("quantity") or 0),
                customer_name=str(item.get("customer_name") or "").strip(),
                dealer_name=str(item.get("dealer_name") or "").strip(),
                due_date=str(item.get("delivery_date") or "").strip(),
            )
    return preview_dealer_order(order_no)


def _merge_batch_to_factory_plan(conn, model: str, batch_no: str, quantity: int, customer_name: str, dealer_name: str, due_date: str):
    """将经销商订单的批次信息合并到 factory_plan 的 指定批次/来源 JSON 字段"""
    if not model or not batch_no or quantity <= 0:
        return

    # Find existing factory_plan row by model + customer_name
    rows = conn.execute(
        text("SELECT id, `指定批次/来源` FROM factory_plan WHERE `机型` = :model AND `客户名` = :customer LIMIT 1"),
        {"model": model, "customer": customer_name},
    ).fetchall()

    if rows:
        row_id = rows[0][0]
        existing = rows[0][1]
        if isinstance(existing, str):
            try:
                existing = json.loads(existing)
            except (json.JSONDecodeError, TypeError):
                existing = {}
        alloc = existing if isinstance(existing, dict) else {}
        # Merge: alloc[model][batch_no] += quantity
        model_alloc = alloc.get(model, {})
        if not isinstance(model_alloc, dict):
            model_alloc = {}
        model_alloc[batch_no] = model_alloc.get(batch_no, 0) + quantity
        alloc[model] = model_alloc
        conn.execute(
            text("UPDATE factory_plan SET `指定批次/来源` = :alloc WHERE id = :id"),
            {"alloc": json.dumps(alloc, ensure_ascii=False), "id": row_id},
        )
    else:
        alloc = {model: {batch_no: quantity}}
        conn.execute(
            text(
                "INSERT INTO factory_plan (`指定批次/来源`, `机型`, `客户名`, `代理商`, `要求交期`, `状态`, `合同号`) "
                "VALUES (:alloc, :model, :customer, :dealer, :due, '待规划', '')"
            ),
            {
                "alloc": json.dumps(alloc, ensure_ascii=False),
                "model": model,
                "customer": customer_name,
                "dealer": dealer_name,
                "due": due_date,
            },
        )


def reject_dealer_order(order_no: str, reviewer: str, reason: str = "") -> dict:
    ensure_dealer_order_tables()
    with get_engine().begin() as conn:
        items = _get_order_lines_for_update(conn, order_no)
        if any(item.get("status") not in {"pending", "approved"} for item in items):
            raise ValueError("当前订单状态不能驳回")
        conn.execute(
            text(
                "UPDATE dealer_orders SET status='rejected', reviewed_at=NOW(), "
                "reviewed_by=:reviewer, review_note=:reason WHERE order_no=:order_no"
            ),
            {"order_no": order_no, "reviewer": reviewer, "reason": reason},
        )
        _enqueue_cloud_sync(
            conn,
            "dealer_order_reviewed",
            order_no,
            {"order_no": order_no, "status": "rejected", "reviewer": reviewer, "note": reason},
        )
    return preview_dealer_order(order_no)


def mark_dealer_order_allocated(order_no: str, allocated_qty: int, v7_order_no: str = "", reviewer: str = "") -> dict:
    ensure_dealer_order_tables()
    with get_engine().begin() as conn:
        items = _get_order_lines_for_update(conn, order_no)
        if any(int(item.get("factory_pending") or 0) for item in items):
            raise ValueError("当前经销商订单已冻结：订单有新备注待复审，复审通过后才可以配货")
        if any(item.get("status") not in {"approved", "pending"} for item in items):
            raise ValueError("只有待审核或已通过订单可以标记配货")
        conn.execute(
            text(
                "UPDATE dealer_orders SET allocated_qty=quantity, status='allocated', "
                "v7_order_no=:v7_order_no, reviewed_at=COALESCE(reviewed_at, NOW()), "
                "reviewed_by=CASE WHEN COALESCE(reviewed_by, '')='' THEN :reviewer ELSE reviewed_by END "
                "WHERE order_no=:order_no"
            ),
            {"order_no": order_no, "v7_order_no": v7_order_no, "reviewer": reviewer},
        )
        contract_no = str(items[0].get("contract_no") or "").strip() if items else ""
        _enqueue_cloud_sync(
            conn,
            "dealer_order_allocated",
            order_no,
            {
                "order_no": order_no,
                "contract_no": contract_no,
                "operator": reviewer,
                "v7_order_no": v7_order_no,
            },
        )
    return preview_dealer_order(order_no)


def validate_dealer_order_convertible(order_no: str) -> list[dict]:
    """Lock and validate a dealer order is eligible for contract conversion. Returns line items."""
    ensure_dealer_order_tables()
    with get_engine().begin() as conn:
        items = _get_order_lines_for_update(conn, order_no)
        if any(int(item.get("factory_pending") or 0) for item in items):
            raise ValueError("当前经销商订单已冻结：订单有新备注待复审，复审通过后才可以转为合同")
        if any(item.get("status") not in CONVERTIBLE_STATUSES for item in items):
            raise ValueError("只有待审核或已通过的订单可以转为合同")
        return items


def approve_dealer_order_extra_review(order_no: str, reviewer: str, note: str = "") -> dict:
    ensure_dealer_order_tables()
    with get_engine().begin() as conn:
        items = _get_order_lines_for_update(conn, order_no)
        if not any(int(item.get("factory_pending") or 0) for item in items):
            raise ValueError("订单没有待复审的新备注")
        if all(str(item.get("status") or "") in {"complete", "completed"} for item in items):
            raise ValueError("已完成订单不需要附加备注复审")
        conn.execute(
            text(
                "UPDATE dealer_orders SET factory_pending=0, reviewed_at=NOW(), "
                "reviewed_by=:reviewer, review_note=CASE WHEN :note='' THEN review_note ELSE :note END "
                "WHERE order_no=:order_no"
            ),
            {"order_no": order_no, "reviewer": reviewer, "note": note},
        )
        _enqueue_cloud_sync(
            conn,
            "dealer_order_reviewed",
            order_no,
            {
                "order_no": order_no,
                "status": "approved",
                "factory_pending": 0,
                "reviewer": reviewer,
                "note": note,
            },
        )
    return preview_dealer_order(order_no)


def reject_dealer_order_extra_review(order_no: str, reviewer: str, reason: str = "") -> dict:
    ensure_dealer_order_tables()
    cascade_result: dict = {}
    with get_engine().begin() as conn:
        items = _get_order_lines_for_update(conn, order_no)
        if not any(int(item.get("factory_pending") or 0) for item in items):
            raise ValueError("订单没有待复审的新备注")
        if not _has_factory_remark(items):
            raise ValueError("订单没有可驳回的新备注内容")
        cascade_result = _cancel_linked_contract_order_chain(
            conn,
            order_no=order_no,
            items=items,
            operator=reviewer,
            reason=reason,
        )
        conn.execute(
            text(
                "UPDATE dealer_orders SET status='rejected', factory_pending=0, reviewed_at=NOW(), "
                "reviewed_by=:reviewer, review_note=:reason WHERE order_no=:order_no"
            ),
            {"order_no": order_no, "reviewer": reviewer, "reason": reason},
        )
        _enqueue_cloud_sync(
            conn,
            "dealer_order_reviewed",
            order_no,
            {"order_no": order_no, "status": "rejected", "factory_pending": 0, "reviewer": reviewer, "note": reason},
        )
    result = preview_dealer_order(order_no)
    result["cascade_cancel"] = cascade_result
    return result


def mark_dealer_order_contracted(order_no: str, contract_no: str, operator: str = "") -> None:
    """Update dealer order after successful contract creation."""
    ensure_dealer_order_tables()
    with get_engine().begin() as conn:
        rows = conn.execute(
            text("SELECT status FROM dealer_orders WHERE order_no=:order_no"),
            {"order_no": order_no},
        ).mappings().all()
        prior_statuses = {str(row.get("status") or "").strip() for row in rows}
        conn.execute(
            text(
                "UPDATE dealer_orders SET status='contracted', contract_no=:contract_no, "
                "reviewed_at=COALESCE(reviewed_at, NOW()), "
                "reviewed_by=CASE WHEN COALESCE(reviewed_by, '')='' THEN :operator ELSE reviewed_by END "
                "WHERE order_no=:order_no"
            ),
            {"order_no": order_no, "contract_no": contract_no, "operator": operator},
        )
        if "pending" in prior_statuses:
            _enqueue_cloud_sync(
                conn,
                "dealer_order_reviewed",
                order_no,
                {"order_no": order_no, "status": "approved", "reviewer": operator, "note": "V7 contract sync pre-approval"},
            )
        _enqueue_cloud_sync(
            conn,
            "dealer_order_contracted",
            order_no,
            {
                "order_no": order_no,
                "contract_no": contract_no,
                "operator": operator,
                "v7_order_no": "",
            },
        )


def get_dealer_orders_pending_counts() -> dict:
    ensure_dealer_order_tables()
    with get_engine().begin() as conn:
        # pending count
        pending = conn.execute(
            text("SELECT COUNT(DISTINCT order_no) FROM dealer_orders WHERE status = 'pending'")
        ).scalar() or 0

        # factory pending count
        factory_pending = conn.execute(
            text(
                "SELECT COUNT(DISTINCT order_no) FROM dealer_orders "
                "WHERE factory_pending = 1 AND status NOT IN ('complete', 'completed')"
            )
        ).scalar() or 0

        # total (todo) count
        total = conn.execute(
            text(
                "SELECT COUNT(DISTINCT order_no) FROM dealer_orders "
                "WHERE status = 'pending' OR (factory_pending = 1 AND status NOT IN ('complete', 'completed'))"
            )
        ).scalar() or 0

        return {
            "pending": pending,
            "factory_pending": factory_pending,
            "total": total,
        }

