"""
回填入库历史数据脚本
从 transaction_log 和 shipping_history 表中提取历史入库记录
"""
from sqlalchemy import text
from database import get_engine
from crud.inbound_history import backfill_inbound_history_from_logs, ensure_inbound_history_table

def main():
    print("开始回填入库历史数据...")

    with get_engine().begin() as conn:
        # 确保表存在
        ensure_inbound_history_table(conn)

        # 查询回填前记录数
        result = conn.execute(text("SELECT COUNT(*) FROM inbound_history")).fetchone()
        before_count = result[0] if result else 0
        print(f"回填前记录数: {before_count}")

        # 执行回填
        inserted = backfill_inbound_history_from_logs(conn)
        print(f"新插入记录数: {inserted}")

        # 查询回填后记录数
        result = conn.execute(text("SELECT COUNT(*) FROM inbound_history")).fetchone()
        after_count = result[0] if result else 0
        print(f"回填后记录数: {after_count}")

        # 获取统计信息
        print("\n数据来源统计:")
        stats = conn.execute(text("""
            SELECT
                source AS `来源`,
                COUNT(*) AS `记录数`,
                MIN(DATE_FORMAT(inbound_time, '%Y-%m-%d')) AS `最早日期`,
                MAX(DATE_FORMAT(inbound_time, '%Y-%m-%d')) AS `最晚日期`
            FROM inbound_history
            GROUP BY source
            ORDER BY COUNT(*) DESC
        """)).fetchall()

        for row in stats:
            print(f"  {row[0]}: {row[1]} 条记录 ({row[2]} ~ {row[3]})")

        # 按月份统计
        print("\n按月份统计:")
        monthly = conn.execute(text("""
            SELECT
                DATE_FORMAT(inbound_time, '%Y-%m') AS `月份`,
                COUNT(*) AS `记录数`
            FROM inbound_history
            GROUP BY DATE_FORMAT(inbound_time, '%Y-%m')
            ORDER BY `月份` DESC
            LIMIT 12
        """)).fetchall()

        for row in monthly:
            print(f"  {row[0]}: {row[1]} 条记录")

    print("\n✅ 回填完成！")

if __name__ == "__main__":
    main()
