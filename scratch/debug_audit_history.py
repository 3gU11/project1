# -*- coding: utf-8 -*-
import sys
sys.path.insert(0, 'd:/CURSORpj/V7STD1.0')
from sqlalchemy import text
from database import get_engine
import pandas as pd

engine = get_engine()
with engine.connect() as conn:
    print("=== audit_log ===")
    try:
        df_audit = pd.read_sql("SELECT * FROM audit_log ORDER BY timestamp DESC LIMIT 50", conn)
        print(df_audit.to_string())
    except Exception as e:
        print("Error:", e)

    print("\n=== operation_log ===")
    try:
        # show columns
        cols = pd.read_sql("SHOW COLUMNS FROM operation_log", conn)
        print("Columns:", cols['Field'].tolist())
        df_op = pd.read_sql("SELECT * FROM operation_log LIMIT 50", conn)
        print(df_op.to_string())
    except Exception as e:
        print("Error:", e)
