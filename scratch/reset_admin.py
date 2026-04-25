from database import get_engine
from sqlalchemy import text
engine = get_engine()
with engine.begin() as conn:
    conn.execute(
        text("UPDATE users SET password = :p WHERE username = 'admin'"),
        {"p": "888"}
    )
print("Admin password reset to 888 (plain text)")
