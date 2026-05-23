import sys
sys.path.insert(0, 'd:/CURSORpj/V7STD1.0')
from database import get_engine
from sqlalchemy import text

with get_engine().begin() as conn:
    conn.execute(
        text("UPDATE dealer_orders SET status='contracted', factory_pending=1 WHERE order_no=:n"),
        {'n': 'DO202605220150464009'}
    )
    r = conn.execute(
        text('SELECT order_no, status, factory_pending, extra_remark FROM dealer_orders WHERE order_no = :n'),
        {'n': 'DO202605220150464009'}
    ).fetchall()
    for row in r:
        print('Restored:', dict(row._mapping))
