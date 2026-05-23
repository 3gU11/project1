import sys
sys.path.insert(0, 'd:/CURSORpj/V7STD1.0')
from database import get_engine
from sqlalchemy import text

contract_no = 'HT202605223400'

with get_engine().begin() as conn:
    # Check factory_plan
    fp = conn.execute(
        text("SELECT `合同号`, `订单号`, `状态`, `机型`, `数量` FROM factory_plan WHERE `合同号` = :cn"),
        {'cn': contract_no}
    ).fetchall()
    print(f"=== factory_plan for {contract_no} ===")
    for r in fp:
        print(dict(zip(['合同号', '订单号', '状态', '机型', '数量'], r)))
    
    # Check units
    units = conn.execute(
        text("SELECT serial_no, contract_no, status, is_locked, sales_id FROM units WHERE contract_no = :cn LIMIT 10"),
        {'cn': contract_no}
    ).fetchall()
    print(f"\n=== units for contract {contract_no} ===")
    for r in units:
        print(dict(r._mapping))
    
    # Check sales_orders
    so = conn.execute(
        text("SELECT `订单号`, `状态`, `delete_reason` FROM sales_orders WHERE `订单号` IN (SELECT DISTINCT `订单号` FROM factory_plan WHERE `合同号`=:cn) LIMIT 5"),
        {'cn': contract_no}
    ).fetchall()
    print(f"\n=== sales_orders related to {contract_no} ===")
    for r in so:
        print(dict(zip(['订单号', '状态', 'delete_reason'], r)))

# Now restore the dealer order state
with get_engine().begin() as conn:
    conn.execute(
        text("UPDATE dealer_orders SET status='contracted', factory_pending=1 WHERE order_no='DO202605220150464009'"),
    )
    r = conn.execute(text("SELECT status, factory_pending FROM dealer_orders WHERE order_no='DO202605220150464009'")).fetchone()
    print(f"\nRestored: status={r[0]}, factory_pending={r[1]}")
