# -*- coding: utf-8 -*-
import sys
sys.path.insert(0, 'd:/CURSORpj/V7STD1.0')
from sqlalchemy import text
from database import get_engine
import pandas as pd

engine = get_engine()
with engine.connect() as conn:
    df_audit = pd.read_sql("""
        SELECT * FROM audit_log 
        WHERE timestamp >= '2026-05-23 00:00:00' 
        ORDER BY timestamp DESC
    """, conn)

with open("d:/CURSORpj/V7STD1.0/scratch/debug_audit_output.txt", "w", encoding="utf-8") as f:
    f.write("=== audit_log (May 23) ===\n")
    f.write(df_audit.to_string() + "\n")

print("Done! Check d:/CURSORpj/V7STD1.0/scratch/debug_audit_output.txt")
