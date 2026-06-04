"""
检查2026年2月的入库数据
"""
from sqlalchemy import text
from database import get_engine

def check_february_data():
    print("检查2026年2月的数据...")

    with get_engine().connect() as conn:
        # 1. 检查 inbound_history 表
        print("\n=== 1. 检查 inbound_history 表 ===")
        result = conn.execute(text("""
            SELECT
                DATE_FORMAT(inbound_time, '%Y-%m') AS 月份,
                COUNT(*) AS 记录数
            FROM inbound_history
            WHERE inbound_time >= '2026-01-01' AND inbound_time < '2026-12-31'
            GROUP BY DATE_FORMAT(inbound_time, '%Y-%m')
            ORDER BY 月份
        """)).fetchall()

        if result:
            print("inbound_history 按月统计：")
            for row in result:
                print(f"  {row[0]}: {row[1]} 条")
        else:
            print("inbound_history 表为空")

        # 2. 检查 transaction_log 表
        print("\n=== 2. 检查 transaction_log 表（入库操作）===")
        result = conn.execute(text("""
            SELECT
                DATE_FORMAT(`时间`, '%Y-%m') AS 月份,
                COUNT(DISTINCT `流水号`) AS 机器数
            FROM transaction_log
            WHERE `时间` >= '2026-01-01' AND `时间` < '2026-12-31'
                AND `流水号` IS NOT NULL
                AND TRIM(`流水号`) <> ''
                AND (
                    `操作类型` = '直接配货-自动入库'
                    OR `操作类型` = '配货自动入库'
                    OR (
                        `操作类型` LIKE '%入库%'
                        AND `操作类型` NOT LIKE '%退回%'
                        AND `操作类型` NOT LIKE '%释放%'
                        AND `操作类型` NOT LIKE '%撤回%'
                    )
                )
            GROUP BY DATE_FORMAT(`时间`, '%Y-%m')
            ORDER BY 月份
        """)).fetchall()

        if result:
            print("transaction_log 按月统计（入库操作）：")
            for row in result:
                print(f"  {row[0]}: {row[1]} 台")
        else:
            print("transaction_log 没有入库记录")

        # 3. 检查2月具体的入库操作类型
        print("\n=== 3. 检查2026年2月的入库操作类型 ===")
        result = conn.execute(text("""
            SELECT
                `操作类型`,
                COUNT(DISTINCT `流水号`) AS 机器数
            FROM transaction_log
            WHERE `时间` >= '2026-02-01' AND `时间` < '2026-03-01'
                AND `流水号` IS NOT NULL
                AND TRIM(`流水号`) <> ''
                AND (
                    `操作类型` = '直接配货-自动入库'
                    OR `操作类型` = '配货自动入库'
                    OR (
                        `操作类型` LIKE '%入库%'
                        AND `操作类型` NOT LIKE '%退回%'
                        AND `操作类型` NOT LIKE '%释放%'
                        AND `操作类型` NOT LIKE '%撤回%'
                    )
                )
            GROUP BY `操作类型`
            ORDER BY 机器数 DESC
        """)).fetchall()

        if result:
            print("2月入库操作类型分布：")
            for row in result:
                print(f"  {row[0]}: {row[1]} 台")
        else:
            print("2月没有入库记录")

        # 4. 检查finished_goods_data表中2月的数据
        print("\n=== 4. 检查 finished_goods_data 表 ===")
        result = conn.execute(text("""
            SELECT COUNT(*) AS 总数
            FROM finished_goods_data
            WHERE `更新时间` >= '2026-02-01' AND `更新时间` < '2026-03-01'
        """)).fetchone()

        print(f"finished_goods_data 2月更新的记录: {result[0] if result else 0} 条")

        # 5. 检查所有月份的数据
        print("\n=== 5. 检查所有月份的入库数据 ===")
        result = conn.execute(text("""
            SELECT
                DATE_FORMAT(`时间`, '%Y-%m') AS 月份,
                COUNT(DISTINCT `流水号`) AS 机器数
            FROM transaction_log
            WHERE `时间` >= '2025-01-01'
                AND `流水号` IS NOT NULL
                AND TRIM(`流水号`) <> ''
                AND (
                    `操作类型` = '直接配货-自动入库'
                    OR `操作类型` = '配货自动入库'
                    OR (
                        `操作类型` LIKE '%入库%'
                        AND `操作类型` NOT LIKE '%退回%'
                        AND `操作类型` NOT LIKE '%释放%'
                        AND `操作类型` NOT LIKE '%撤回%'
                    )
                )
            GROUP BY DATE_FORMAT(`时间`, '%Y-%m')
            ORDER BY 月份 DESC
            LIMIT 12
        """)).fetchall()

        if result:
            print("最近12个月的入库统计：")
            for row in result:
                print(f"  {row[0]}: {row[1]} 台")

if __name__ == "__main__":
    check_february_data()
