from database import get_engine
from sqlalchemy import text
with get_engine().begin() as conn:
    row = conn.execute(text("SELECT status, factory_pending FROM dealer_orders WHERE order_no='DO202605220150464009'")).fetchone()
    print("Database State:", row)
