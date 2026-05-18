from __future__ import annotations

import json
from collections import OrderedDict
from math import ceil
from typing import Any

from sqlalchemy import text

from database import get_engine


ACTIVE_HOLD_STATUSES = ("pending", "approved")


def ensure_dealer_order_tables() -> None:
    with get_engine().begin() as conn:
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
            ("approved_qty", "ALTER TABLE dealer_orders ADD COLUMN approved_qty INT NOT NULL DEFAULT 0 AFTER quantity"),
            ("allocated_qty", "ALTER TABLE dealer_orders ADD COLUMN allocated_qty INT NOT NULL DEFAULT 0 AFTER approved_qty"),
            ("reviewed_at", "ALTER TABLE dealer_orders ADD COLUMN reviewed_at DATETIME NULL AFTER status"),
            ("reviewed_by", "ALTER TABLE dealer_orders ADD COLUMN reviewed_by VARCHAR(128) DEFAULT '' AFTER reviewed_at"),
            ("contract_no", "ALTER TABLE dealer_orders ADD COLUMN contract_no VARCHAR(128) DEFAULT '' AFTER reviewed_by"),
            ("v7_order_no", "ALTER TABLE dealer_orders ADD COLUMN v7_order_no VARCHAR(128) DEFAULT '' AFTER contract_no"),
            ("review_note", "ALTER TABLE dealer_orders ADD COLUMN review_note TEXT AFTER v7_order_no"),
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


def _status_rank(status: str) -> int:
    return {
        "pending": 0,
        "approved": 1,
        "partial_allocated": 2,
        "allocated": 3,
        "rejected": 4,
        "cancelled": 5,
        "completed": 6,
    }.get(status or "", 9)


def _aggregate_status(items: list[dict]) -> str:
    statuses = [str(item.get("status") or "") for item in items]
    if statuses and all(status == "allocated" for status in statuses):
        return "allocated"
    if any(status == "allocated" or int(item.get("allocated_qty") or 0) > 0 for status, item in zip(statuses, items)):
        return "partial_allocated"
    if statuses and all(status == "rejected" for status in statuses):
        return "rejected"
    if statuses and all(status == "cancelled" for status in statuses):
        return "cancelled"
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
            "order_no LIKE :kw OR dealer_name LIKE :kw OR customer_name LIKE :kw "
            "OR contact_phone LIKE :kw OR model LIKE :kw OR batch_no LIKE :kw"
            ")"
        )
        params["kw"] = f"%{keyword}%"
    where_sql = f"WHERE {' AND '.join(where)}" if where else ""
    with get_engine().connect() as conn:
        raw_rows = conn.execute(
            text(
                f"""
                SELECT id, order_no, line_no, dealer_id, dealer_name, dealer_phone, customer_name,
                       contact_name, contact_phone, model, batch_no, eta, inventory_type,
                       quantity, approved_qty, allocated_qty, delivery_date, remark,
                       status, reviewed_at, reviewed_by, contract_no, v7_order_no, review_note,
                       created_at, updated_at
                FROM dealer_orders
                {where_sql}
                ORDER BY FIELD(status, 'pending', 'approved', 'allocated', 'rejected', 'cancelled', 'completed'),
                         created_at DESC, order_no DESC, line_no ASC, id ASC
                """
            ),
            params,
        ).fetchall()
        rows = []
        for row in raw_rows:
            item = _row_to_dict(row)
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
    if status_filter:
        grouped = [order for order in grouped if order.get("status") == status_filter]
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
    with get_engine().connect() as conn:
        rows = conn.execute(
            text("SELECT * FROM dealer_orders WHERE order_no=:order_no ORDER BY line_no, id"),
            {"order_no": order_no},
        ).fetchall()
        if not rows:
            raise ValueError("订单不存在")
        items = _decorate_items_with_availability(conn, [_row_to_dict(row) for row in rows])
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
    return preview_dealer_order(order_no)


def mark_dealer_order_allocated(order_no: str, allocated_qty: int, v7_order_no: str = "", reviewer: str = "") -> dict:
    ensure_dealer_order_tables()
    with get_engine().begin() as conn:
        items = _get_order_lines_for_update(conn, order_no)
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
    return preview_dealer_order(order_no)
