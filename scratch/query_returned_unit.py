import sys
from pathlib import Path
sys.path.append(str(Path(__file__).resolve().parents[1]))

from database import get_engine
from sqlalchemy import text

engine = get_engine()
with engine.connect() as conn:
    # Query unit details for returned contracts
    print("Units for contract HT202605218269:")
    units = conn.execute(text("SELECT * FROM units WHERE contract_no = 'HT202605218269'")).mappings().fetchall()
    for u in units:
        print(dict(u))

    # Query production_lines
    lines = conn.execute(text("SELECT * FROM production_lines")).mappings().fetchall()
    print("\nProduction Lines:")
    for l in lines:
        print(dict(l))

