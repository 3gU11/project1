import sys
from pathlib import Path

# Add project root to sys.path
sys.path.append(str(Path(__file__).resolve().parents[1]))

from database import get_engine
from sqlalchemy import text

def inspect_order(target: str):
    engine = get_engine()
    with engine.connect() as conn:
        print(f"=== Inspecting Target: {target} ===")
        
        # 1. dealer_orders
        print("\n--- dealer_orders ---")
        rows = conn.execute(
            text("SELECT id, order_no, status, v7_order_no, contract_no, factory_pending FROM dealer_orders WHERE order_no = :t OR v7_order_no = :t OR contract_no = :t"),
            {"t": target}
        ).mappings().all()
        for r in rows:
            print(dict(r))
            
        # 2. sales_orders
        print("\n--- sales_orders ---")
        rows = conn.execute(
            text("SELECT `订单号`, status, delete_reason FROM sales_orders WHERE `订单号` = :t"),
            {"t": target}
        ).mappings().all()
        for r in rows:
            print(dict(r))
            
        # 3. factory_plan
        print("\n--- factory_plan ---")
        rows = conn.execute(
            text("SELECT `合同号`, `订单号`, `状态` FROM factory_plan WHERE `合同号` = :t OR `订单号` = :t"),
            {"t": target}
        ).mappings().all()
        for r in rows:
            print(dict(r))
            
        # 4. finished_goods_data
        print("\n--- finished_goods_data ---")
        rows = conn.execute(
            text("SELECT `流水号`, `占用订单号`, `合同号`, `状态` FROM finished_goods_data WHERE `占用订单号` = :t OR `合同号` = :t"),
            {"t": target}
        ).mappings().all()
        for r in rows:
            print(dict(r))
            
        # 5. units
        print("\n--- units ---")
        rows = conn.execute(
            text("SELECT id, serial_no, contract_no, sales_id, is_locked FROM units WHERE contract_no = :t OR sales_id = :t"),
            {"t": target}
        ).mappings().all()
        for r in rows:
            print(dict(r))

if __name__ == "__main__":
    target = "SO-20260522-799E"
    if len(sys.argv) > 1:
        target = sys.argv[1]
    inspect_order(target)
