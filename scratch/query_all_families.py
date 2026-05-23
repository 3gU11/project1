import sys
from pathlib import Path
sys.path.append(str(Path(__file__).resolve().parents[1]))

from database import get_engine
from sqlalchemy import text

engine = get_engine()
with engine.connect() as conn:
    rows = conn.execute(text("SELECT DISTINCT model_family, HEX(model_family) FROM model_dictionary")).fetchall()
    print("Distinct model families in database:")
    for r in rows:
        print(f"family string: {repr(r[0])}, hex: {r[1]}")
