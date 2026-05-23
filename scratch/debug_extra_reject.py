import sys
sys.path.insert(0, 'd:/CURSORpj/V7STD1.0')

from database import get_engine
from sqlalchemy import text
import traceback

order_no = 'DO202605220150464009'

print(f"=== Full order state ===")
with get_engine().begin() as conn:
    rows = conn.execute(
        text('SELECT * FROM dealer_orders WHERE order_no = :order_no ORDER BY line_no'),
        {'order_no': order_no}
    ).fetchall()
    for r in rows:
        d = dict(r._mapping)
        print(d)

print("\n=== Trying reject_dealer_order_extra_review with traceback ===")
try:
    from crud.dealer_orders import reject_dealer_order_extra_review
    result = reject_dealer_order_extra_review(order_no, reviewer='test_admin', reason='test reason from UI')
    print("Success!")
except Exception as e:
    print(f"Error type: {type(e).__name__}")
    print(f"Error: {e}")
    traceback.print_exc()
