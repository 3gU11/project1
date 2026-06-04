"""
查询机型大类分布
"""
from sqlalchemy import text
from database import get_engine

def main():
    with get_engine().connect() as conn:
        # 查询所有机型
        result = conn.execute(text("""
            SELECT DISTINCT `机型`
            FROM finished_goods_data
            WHERE `机型` IS NOT NULL AND `机型` != ''
            ORDER BY `机型`
            LIMIT 50
        """)).fetchall()

        print("现有机型列表：")
        for row in result:
            print(f"  {row[0]}")

if __name__ == "__main__":
    main()
