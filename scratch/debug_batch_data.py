# -*- coding: utf-8 -*-
import sys
sys.path.insert(0, 'd:/CURSORpj/V7STD1.0')
from sqlalchemy import text
from database import get_engine
import pandas as pd

engine = get_engine()
with engine.connect() as conn:
    df = pd.read_sql("""
        SELECT `流水号`, `批次号`, `预计入库时间`, `机型`, `状态`, `占用订单号`, `客户`, `代理商`
        FROM finished_goods_data
        WHERE `流水号` IN ('96-06-01', '96-06-02', '96-06-03', '96-06-04', '96-06-05', '96-06-06')
    """, conn)

with open("d:/CURSORpj/V7STD1.0/scratch/debug_batch_output.txt", "w", encoding="utf-8") as f:
    f.write("=== finished_goods_data for 96-06-01 to 06 ===\n")
    f.write(df.to_string() + "\n")

print("Done!")
