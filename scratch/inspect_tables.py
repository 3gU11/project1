from database import get_engine
from sqlalchemy import text, inspect
import sys

engine = get_engine()
inspector = inspect(engine)
tables = inspector.get_table_names()
print("All tables in database:", tables)

required_columns = {
    "factory_plan": ["订单号", "合同号", "状态"],
    "finished_goods_data": ["流水号", "占用订单号", "状态", "合同号", "Location_Code", "更新时间"],
    "units": ["contract_no", "customer", "dealer_name", "sales_id", "due_date", "is_locked", "serial_no", "forecast_serial_no", "order_remark"],
    "production_queue": ["contract_no", "status"],
    "rush_order_queue": ["status", "updated_by", "contract_no"],
    "sales_orders": ["status", "delete_reason", "订单号"],
}

print("\nChecking table schemas:")
for table, cols in required_columns.items():
    if table not in tables:
        print(f"  [MISSING TABLE] {table}")
    else:
        print(f"  [FOUND] {table}")
        existing_cols = [c["name"] for c in inspector.get_columns(table)]
        print(f"    Existing columns: {existing_cols}")
        for col in cols:
            if col not in existing_cols:
                print(f"    [MISSING COLUMN] {col} in {table}")
