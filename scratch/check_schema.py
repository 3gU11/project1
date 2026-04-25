from database import get_engine
from sqlalchemy import text
engine = get_engine()
with engine.connect() as conn:
    rows = conn.execute(text("DESCRIBE sys_operation_log")).fetchall()
    for row in rows:
        print(row)
