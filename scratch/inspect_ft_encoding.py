import sys
from pathlib import Path
sys.path.append(str(Path(__file__).resolve().parents[1]))

from database import get_engine
from sqlalchemy import text

engine = get_engine()
with engine.connect() as conn:
    row = conn.execute(text("SELECT id, model_name, HEX(model_family), model_family FROM model_dictionary WHERE model_name = 'FT'")).mappings().fetchone()
    print("FT Row Info:")
    print(dict(row))
