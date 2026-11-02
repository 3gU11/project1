"""Transaction-scoped guards for inventory order relationships."""
from sqlalchemy import text


def require_inventory_order(conn, order_id):
    order_id = str(order_id or "").strip()
    if not order_id:
        raise ValueError("待发货机台必须绑定有效订单")
    row = conn.execute(
        text("SELECT `订单号`, `status` FROM sales_orders WHERE `订单号`=:order_id FOR UPDATE"),
        {"order_id": order_id},
    ).mappings().first()
    if row is None or str(row.get("status") or "").strip().lower() in {
        "deleted", "cancelled", "canceled",
    }:
        raise ValueError(f"订单 {order_id} 不存在或已取消，请先核对订单，操作未执行")
    return row


def validate_shipping_rows(conn, rows, serials):
    found = {str(row.get("流水号") or "").strip() for row in rows}
    missing = set(serials) - found
    if missing:
        raise ValueError(f"机台不存在: {', '.join(sorted(missing))}")
    orders = set()
    for row in rows:
        status = str(row.get("状态") or "").strip()
        if status == "已出库":
            continue  # Preserve idempotent confirmation of historical shipments.
        if status != "待发货":
            raise ValueError(f"机台 {row['流水号']} 当前不是待发货，不能确认发货")
        orders.add(str(row.get("占用订单号") or "").strip())
    for order_id in sorted(orders):
        require_inventory_order(conn, order_id)
