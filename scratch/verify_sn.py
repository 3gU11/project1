import sys
import os
import pymysql

# Root directory
ROOT = r"d:\antigraveity_pj\V7STD"

# Manually load config values from config.py if possible, or just use defaults
# Here I'll just try to connect to the DB directly since I have the settings from database.py viewed earlier
DB_CONFIG = {
    'host': 'localhost',
    'user': 'root',
    'password': '', # Assuming empty
    'db': 'v7std',
    'charset': 'utf8mb4'
}

def check_serial(sn):
    try:
        conn = pymysql.connect(**DB_CONFIG)
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM finished_goods_data WHERE 流水号 = %s", (sn,))
        row = cursor.fetchone()
        print(f"Serial {sn} existence: {row is not None}")
        if row:
            print(f"Data: {row}")
        conn.close()
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    check_serial("96-03-187")
