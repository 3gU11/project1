import sys
from pathlib import Path
sys.path.append(str(Path(__file__).resolve().parents[1]))

from database import get_engine
from sqlalchemy import text

engine = get_engine()
with engine.connect() as conn:
    row = conn.execute(text("SELECT * FROM batches WHERE batch_id = 'BATCH-202605-G-001-36132449'")).mappings().fetchone()
    print("Batch details:")
    print(dict(row) if row else "Batch not found")

    # Let's also check if there are other batches starting with BATCH-202605-G-001
    rows = conn.execute(text("SELECT batch_id, model_type, status FROM batches WHERE batch_id LIKE 'BATCH-202605-G-001%'")).mappings().fetchall()
    print("\nAll matching batches:")
    for r in rows:
        print(dict(r))
