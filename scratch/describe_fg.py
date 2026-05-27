import sys
sys.path.insert(0, 'd:/CURSORpj/V7STD1.0')
from sqlalchemy import text
from database import get_engine
import pandas as pd

engine = get_engine()
with engine.connect() as conn:
    cols = pd.read_sql("SHOW COLUMNS FROM finished_goods_data", conn)
    print(cols.to_string())
