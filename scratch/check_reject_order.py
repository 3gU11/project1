import sys
sys.path.insert(0, 'd:/CURSORpj/V7STD1.0')

from database import get_engine
from sqlalchemy import text

order_no = 'DO202605220150464009'

with get_engine().begin() as conn:
    rows = conn.execute(
        text('SELECT order_no, line_no, status, model, quantity, allocated_qty, factory_pending, contract_no, extra_remark, factory_reviewed_at, factory_reviewed_by, remark, review_note FROM dealer_orders WHERE order_no = :order_no ORDER BY line_no'),
        {'order_no': order_no}
    ).fetchall()
    print(f"=== Full order lines for {order_no} ===")
    for r in rows:
        d = dict(r._mapping)
        for k, v in d.items():
            print(f"  {k}: {repr(v)}")
        print("---")

# Now simulate what the reject_dealer_order_extra_review does
print("\n=== Trying reject_dealer_order_extra_review ===")
try:
    from crud.dealer_orders import reject_dealer_order_extra_review
    result = reject_dealer_order_extra_review(order_no, reviewer='test_admin', reason='test reason')
    print("Success!")
except Exception as e:
    print(f"Error type: {type(e).__name__}")
    print(f"Error: {e}")
    import traceback
    traceback.print_exc()
