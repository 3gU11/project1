import sys
sys.path.insert(0, 'd:/CURSORpj/V7STD1.0')

from database import get_engine
from sqlalchemy import text

order_no = 'DO202605220150464009'

# Restore order to contracted + factory_pending=1 state
with get_engine().begin() as conn:
    conn.execute(
        text("UPDATE dealer_orders SET status='contracted', factory_pending=1 WHERE order_no=:order_no"),
        {'order_no': order_no}
    )
    print(f"Restored {order_no} to contracted + factory_pending=1")

    # Verify
    rows = conn.execute(
        text('SELECT order_no, line_no, status, factory_pending, contract_no, extra_remark FROM dealer_orders WHERE order_no = :order_no'),
        {'order_no': order_no}
    ).fetchall()
    for r in rows:
        print(dict(r._mapping))
