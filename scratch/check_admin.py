from database import get_engine
from sqlalchemy import text
engine = get_engine()
with engine.connect() as conn:
    rows = conn.execute(text("SELECT username, password FROM users WHERE username IN ('boss', 'sales', 'prod', 'inbound')")).mappings().all()
    for row in rows:
        print(row)
