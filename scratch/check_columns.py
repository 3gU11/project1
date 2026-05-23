import sys
sys.path.insert(0, 'd:/CURSORpj/V7STD1.0')

from database import get_engine
from sqlalchemy import text
import traceback

# Check units table columns
with get_engine().begin() as conn:
    cols = conn.execute(text("SHOW COLUMNS FROM units")).fetchall()
    print("=== units table columns ===")
    for c in cols:
        print(f"  {c[0]}: {c[1]}")
    
    print()
    # Check if order_remark exists
    col_names = [c[0] for c in cols]
    print(f"order_remark exists: {'order_remark' in col_names}")
    print(f"is_locked exists: {'is_locked' in col_names}")
    
    # also check sales_orders table
    so_cols = conn.execute(text("SHOW COLUMNS FROM sales_orders")).fetchall()
    print("\n=== sales_orders relevant columns ===")
    so_col_names = [c[0] for c in so_cols]
    print(f"delete_reason column exists: {'delete_reason' in so_col_names}")
    
    # Check production_queue table
    try:
        pq_cols = conn.execute(text("SHOW COLUMNS FROM production_queue")).fetchall()
        print("\n=== production_queue exists: yes ===")
        print(f"  columns: {[c[0] for c in pq_cols]}")
    except Exception as e:
        print(f"\nproduction_queue table error: {e}")
    
    # Check rush_order_queue
    try:
        rq_cols = conn.execute(text("SHOW COLUMNS FROM rush_order_queue")).fetchall()
        print("\n=== rush_order_queue exists: yes ===")
        print(f"  columns: {[c[0] for c in rq_cols]}")
    except Exception as e:
        print(f"\nrush_order_queue table error: {e}")
