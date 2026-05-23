import sys
from pathlib import Path

# Add project root to sys.path
sys.path.append(str(Path(__file__).resolve().parents[1]))

from database import get_engine
from sqlalchemy import text

engine = get_engine()
with engine.connect() as conn:
    # Query predicted batches
    batches = conn.execute(text("SELECT batch_id, batch_no, status, model_type, capacity FROM batches WHERE status = 'Predicted'")).mappings().fetchall()
    print("Predicted Batches:")
    for b in batches:
        print(dict(b))

    # Query the last operation log for return-to-sandbox to see which unit_id and batch_id were involved
    op_log = conn.execute(text("SELECT * FROM operation_log WHERE action = 'rush_return_to_sandbox' ORDER BY created_at DESC LIMIT 5")).mappings().fetchall()
    print("\nRecent Return Operations:")
    for op in op_log:
        print(dict(op))

    # Query model_dictionary for FT-related models
    models = conn.execute(text("SELECT * FROM model_dictionary WHERE UPPER(model_name) LIKE '%FT%'")).mappings().fetchall()
    print("\nFT Models in model_dictionary:")
    for m in models:
        print(dict(m))

