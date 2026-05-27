# -*- coding: utf-8 -*-
import sys
sys.path.insert(0, 'd:/CURSORpj/V7STD1.0')
from sqlalchemy import text
from database import get_engine
import pandas as pd

engine = get_engine()
with engine.connect() as conn:
    print("Searching for 96-06-01...")
    # List of tables to check
    tables = ['finished_goods_data', 'units', 'factory_plan', 'batches', 'production_queue', 'sales_orders']
    for t in tables:
        try:
            # check if table exists
            res = conn.execute(text(f"SHOW TABLES LIKE '{t}'")).first()
            if not res:
                continue
            # search for '96-06-01' in columns
            cols_df = pd.read_sql(f"SHOW COLUMNS FROM {t}", conn)
            char_cols = cols_df[cols_df['Type'].str.contains('char|varchar|text|longtext', case=False)]['Field'].tolist()
            if not char_cols:
                continue
            or_clauses = [f"`{c}` LIKE '%%96-06-%%'" for c in char_cols]
            query = f"SELECT * FROM `{t}` WHERE " + " OR ".join(or_clauses)
            df = pd.read_sql(query, conn)
            if not df.empty:
                print(f"Table '{t}' has {len(df)} matching rows:")
                print(df.head(2).to_string())
        except Exception as e:
            print(f"Error checking table '{t}': {e}")
