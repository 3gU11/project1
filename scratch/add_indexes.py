from database import get_engine
from sqlalchemy import text
engine = get_engine()
with engine.begin() as conn:
    try:
        conn.execute(text("ALTER TABLE factory_plan ADD INDEX idx_fp_order (`订单号`)"))
        print("Added idx_fp_order")
    except Exception as e:
        print(f"factory_plan index error: {e}")
    try:
        conn.execute(text("ALTER TABLE finished_goods_data ADD INDEX idx_fg_order (`占用订单号`)"))
        print("Added idx_fg_order")
    except Exception as e:
        print(f"fg_data index error: {e}")
