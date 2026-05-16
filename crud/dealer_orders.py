from __future__ import annotations

from math import ceil
from typing import Any

from sqlalchemy import text

from database import get_engine


ACTIVE_HOLD_STATUSES = ("pending", "approved")


def ensure_dealer_order_tables() -> None:
    with get_engine().begin() as conn:
        conn.execute(text(
            """
            CREATE TABLE IF NOT EXISTS dealer_orders (
              id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
              order_no VARCHAR(64) NOT NULL UNIQUE,
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
              v7_order_no VARCHAR(128) DEFAULT '',
              review_note TEXT,
              created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
              updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
              INDEX idx_dealer_id (dealer_id),
              INDEX idx_status (status),
              INDEX idx_batch_model_status (batch_no, model, status),
              INDEX idx_created_at (created_at)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """
        ))
        columns = {
            row[0]
            for row in conn.execute(text("SHOW COLUMNS FROM dealer_orders")).fetchall()
        }
        additions = [
            ("approved_qty", "ALTER TABLE dealer_orders ADD COLUMN approved_qty INT NOT NULL DEFAULT 0 AFTER quantity"),
            ("allocated_qty", "ALTER TABLE dealer_orders ADD COLUMN allocated_qty INT NOT NULL DEFAULT 0 AFTER approved_qty"),
            ("reviewed_at", "ALTER TABLE dealer_orders ADD COLUMN reviewed_at DATETIME NULL AFTER status"),
            ("reviewed_by", "ALTER TABLE dealer_orders ADD COLUMN reviewed_by VARCHAR(128) DEFAULT '' AFTER reviewed_at"),
            ("v7_order_no", "ALTER TABLE dealer_orders ADD COLUMN v7_order_no VARCHAR(128) DEFAULT '' AFTER reviewed_by"),
            ("review_note", "ALTER TABLE dealer_orders ADD COLUMN review_note TEXT AFTER v7_order_no"),
        ]
        for column, sql in additions:
            if column not in columns:
                conn.execute(text(sql))


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
    if status:
        where.append("status = :status")
        params["status"] = status
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
    offset = (page - 1) * page_size
    with get_engine().connect() as conn:
        total = int(conn.execute(text(f"SELECT COUNT(*) FROM dealer_orders {where_sql}"), params).scalar() or 0)
        rows = conn.execute(
            text(
                f"""
                SELECT id, order_no, dealer_id, dealer_name, dealer_phone, customer_name,
                       contact_name, contact_phone, model, batch_no, eta, inventory_type,
                       quantity, approved_qty, allocated_qty, delivery_date, remark,
                       status, reviewed_at, reviewed_by, v7_order_no, review_note,
                       created_at, updated_at
                FROM dealer_orders
                {where_sql}
                ORDER BY FIELD(status, 'pending', 'approved', 'allocated', 'rejected', 'cancelled', 'completed'),
                         created_at DESC
                LIMIT :limit OFFSET :offset
                """
            ),
            {**params, "limit": page_size, "offset": offset},
        ).fetchall()
    data = []
    with get_engine().connect() as conn:
        for row in rows:
            item = _row_to_dict(row)
            availability = get_availability(conn, item)
            item.update(
                {
                    "summary_qty": availability["summary_qty"],
                    "occupied_qty": availability["occupied_qty"],
                    "available_qty": availability["available_for_current"],
                }
            )
            data.append(item)
    return {
        "data": data,
        "total": total,
        "page": page,
        "page_size": page_size,
        "pages": ceil(total / page_size) if page_size else 0,
    }


def _get_order_for_update(conn, order_no: str) -> dict:
    row = conn.execute(
        text("SELECT * FROM dealer_orders WHERE order_no=:order_no FOR UPDATE"),
        {"order_no": order_no},
    ).fetchone()
    if not row:
        raise ValueError("订单不存在")
    return _row_to_dict(row)


def get_availability(conn, order: dict) -> dict:
    summary_batch = _summary_batch_no(order.get("batch_no"), order.get("inventory_type"))
    hold_batch = _order_hold_batch_no(order.get("batch_no"), order.get("inventory_type"))
    model = str(order.get("model") or "").strip()
    summary_qty = int(conn.execute(
        text(
            "SELECT COALESCE(SUM(quantity), 0) FROM wechat_batch_summary "
            "WHERE batch_no=:batch_no AND model=:model"
        ),
        {"batch_no": summary_batch, "model": model},
    ).scalar() or 0)
    occupied_qty = int(conn.execute(
        text(
            "SELECT COALESCE(SUM(GREATEST(quantity - allocated_qty, 0)), 0) "
            "FROM dealer_orders "
            "WHERE batch_no=:batch_no AND model=:model "
            "AND status IN ('pending', 'approved') "
            "AND quantity > allocated_qty"
        ),
        {"batch_no": hold_batch, "model": model},
    ).scalar() or 0)
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


def preview_dealer_order(order_no: str) -> dict:
    ensure_dealer_order_tables()
    with get_engine().connect() as conn:
        row = conn.execute(text("SELECT * FROM dealer_orders WHERE order_no=:order_no"), {"order_no": order_no}).fetchone()
        if not row:
            raise ValueError("订单不存在")
        order = _row_to_dict(row)
        availability = get_availability(conn, order)
        return {
            "order": order,
            "availability": availability,
            "summary_qty": availability["summary_qty"],
            "occupied_qty": availability["occupied_qty"],
            "available_qty": availability["available_for_current"],
            "can_approve": availability["available_for_current"] >= max(
                0,
                int(order.get("quantity") or 0) - int(order.get("allocated_qty") or 0),
            ),
        }


def approve_dealer_order(order_no: str, reviewer: str, note: str = "") -> dict:
    ensure_dealer_order_tables()
    with get_engine().begin() as conn:
        order = _get_order_for_update(conn, order_no)
        if order.get("status") != "pending":
            raise ValueError("只有待审核订单可以通过")
        availability = get_availability(conn, order)
        needed = max(0, int(order.get("quantity") or 0) - int(order.get("allocated_qty") or 0))
        if availability["available_for_current"] < needed:
            raise ValueError(
                f"可用数量不足：需要 {needed}，当前可用 {availability['available_for_current']}"
            )
        conn.execute(
            text(
                "UPDATE dealer_orders SET status='approved', approved_qty=quantity, "
                "reviewed_at=NOW(), reviewed_by=:reviewer, review_note=:note "
                "WHERE order_no=:order_no"
            ),
            {"order_no": order_no, "reviewer": reviewer, "note": note},
        )
    return preview_dealer_order(order_no)


def reject_dealer_order(order_no: str, reviewer: str, reason: str = "") -> dict:
    ensure_dealer_order_tables()
    with get_engine().begin() as conn:
        order = _get_order_for_update(conn, order_no)
        if order.get("status") not in {"pending", "approved"}:
            raise ValueError("当前状态不能驳回")
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
    allocated_qty = max(1, int(allocated_qty or 0))
    with get_engine().begin() as conn:
        order = _get_order_for_update(conn, order_no)
        if order.get("status") not in {"approved", "pending"}:
            raise ValueError("只有待审核/已通过订单可以标记配货")
        quantity = int(order.get("quantity") or 0)
        old_allocated = int(order.get("allocated_qty") or 0)
        next_allocated = min(quantity, old_allocated + allocated_qty)
        next_status = "allocated" if next_allocated >= quantity else "approved"
        conn.execute(
            text(
                "UPDATE dealer_orders SET allocated_qty=:allocated_qty, status=:status, "
                "v7_order_no=:v7_order_no, reviewed_at=COALESCE(reviewed_at, NOW()), "
                "reviewed_by=CASE WHEN COALESCE(reviewed_by, '')='' THEN :reviewer ELSE reviewed_by END "
                "WHERE order_no=:order_no"
            ),
            {
                "order_no": order_no,
                "allocated_qty": next_allocated,
                "status": next_status,
                "v7_order_no": v7_order_no,
                "reviewer": reviewer,
            },
        )
    return preview_dealer_order(order_no)
