import sys
from pathlib import Path
sys.path.append(str(Path(__file__).resolve().parents[1]))

from database import get_engine
from sqlalchemy import text

engine = get_engine()
with engine.connect() as conn:
    print("Logs for contract HT202605218269:")
    rows = conn.execute(text("SELECT * FROM operation_log WHERE detail LIKE '%HT202605218269%' OR target_id = '167' ORDER BY created_at DESC")).mappings().fetchall()
    for r in rows:
        print(dict(r))
