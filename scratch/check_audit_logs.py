# -*- coding: utf-8 -*-
import sys
sys.path.insert(0, 'd:/CURSORpj/V7STD1.0')
from sqlalchemy import text
from database import get_engine
import pandas as pd

engine = get_engine()
with engine.connect() as conn:
    print("=== audit_log (recent) ===")
    try:
        df_audit = pd.read_sql("SELECT * FROM audit_log ORDER BY timestamp DESC LIMIT 20", conn)
        print(df_audit.to_string())
    except Exception as e:
        print("Error reading audit_log:", e)

    print("\n=== operation_log (recent) ===")
    try:
        df_op = pd.read_sql("SELECT * FROM operation_log ORDER BY id DESC LIMIT 20", conn)
        print(df_op.to_string())
    except Exception as e:
        print("Error reading operation_log:", e)

    print("\n=== cloud_sync_outbox (recent) ===")
    try:
        df_outbox = pd.read_sql("SELECT * FROM cloud_sync_outbox ORDER BY id DESC LIMIT 20", conn)
        print(df_outbox.to_string())
    except Exception as e:
        print("Error reading cloud_sync_outbox:", e)
