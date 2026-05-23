import sys
sys.path.insert(0, r'd:\CURSORpj\V7STD1.0')

from database import get_engine
from sqlalchemy import text

engine = get_engine()
with engine.connect() as conn:
    print('*** sales_orders ***')
    order = conn.execute(text("SELECT * FROM sales_orders WHERE `订单号`='SO-20260522-799E'")).mappings().all()
    for row in order:
        print(dict(row))
    print('\n*** finished_goods_data ***')
    fg = conn.execute(text("SELECT `流水号`, `机型`, `状态`, `占用订单号` FROM finished_goods_data WHERE `占用订单号`='SO-20260522-799E'")).mappings().all()
    for row in fg:
        print(dict(row))
    print('\n*** units ***')
    units = conn.execute(text("SELECT `id`, `serial_no`, `forecast_serial_no`, `customer`, `dealer_name`, `sales_id`, `contract_no` FROM units WHERE `sales_id`='SO-20260522-799E'")).mappings().all()
    for row in units:
        print(dict(row))
