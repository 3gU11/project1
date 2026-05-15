import pymysql

DB_CONFIG = {
    "host": "localhost",
    "user": "root",
    "password": "030705",
    "database": "rjfinshed",
    "charset": "utf8mb4"
}

def restore_rush_orders():
    conn = pymysql.connect(**DB_CONFIG)
    try:
        cursor = conn.cursor()
        with open("scripts/insert_rush_orders.sql", "r", encoding="utf-8") as f:
            sql = f.read()
        
        # Split by ; if multiple statements, but here it's just one big INSERT SELECT
        cursor.execute(sql)
        count = cursor.rowcount
        conn.commit()
        print(f"Successfully restored {count} rush orders.")
    except Exception as e:
        print(f"Error: {e}")
    finally:
        conn.close()

if __name__ == "__main__":
    restore_rush_orders()
