from database import get_engine
from sqlalchemy import text
engine = get_engine()
with engine.connect() as conn:
    print('Column collations (factory_plan):')
    rows = conn.execute(text("SHOW FULL COLUMNS FROM factory_plan")).fetchall()
    for row in rows: print(row[0], row[2])
    print('\nColumn collations (finished_goods_data):')
    rows = conn.execute(text("SHOW FULL COLUMNS FROM finished_goods_data")).fetchall()
    for row in rows: print(row[0], row[2])
