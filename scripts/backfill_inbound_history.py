"""
回填入库历史数据脚本
从 transaction_log 表中提取历史入库记录，填充到 inbound_history 表
"""
import sys
from pathlib import Path

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from crud.inbound_history import backfill_inbound_history_from_logs, ensure_inbound_history_table
from database import get_engine


def main():
    """执行历史数据回填"""
    print("=" * 60)
    print("入库历史数据回填工具")
    print("=" * 60)

    try:
        with get_engine().begin() as conn:
            # 确保表存在
            print("\n1. 检查 inbound_history 表...")
            ensure_inbound_history_table(conn)
            print("   ✓ 表结构已就绪")

            # 查询当前记录数
            result = conn.execute("SELECT COUNT(*) FROM inbound_history").fetchone()
            before_count = result[0] if result else 0
            print(f"\n2. 当前历史记录数: {before_count}")

            # 执行回填
            print("\n3. 开始从 transaction_log 回填数据...")
            print("   (这可能需要几分钟，取决于数据量)")
            inserted = backfill_inbound_history_from_logs(conn)

            # 查询回填后记录数
            result = conn.execute("SELECT COUNT(*) FROM inbound_history").fetchone()
            after_count = result[0] if result else 0

            print(f"\n4. 回填完成!")
            print(f"   - 新增记录: {inserted}")
            print(f"   - 总记录数: {after_count}")

            # 显示统计信息
            print("\n5. 数据统计:")
            stats = conn.execute("""
                SELECT
                    source AS `来源`,
                    COUNT(*) AS `记录数`,
                    MIN(DATE_FORMAT(inbound_time, '%Y-%m-%d')) AS `最早日期`,
                    MAX(DATE_FORMAT(inbound_time, '%Y-%m-%d')) AS `最晚日期`
                FROM inbound_history
                GROUP BY source
                ORDER BY COUNT(*) DESC
            """).fetchall()

            if stats:
                print(f"\n   {'来源':<25} {'记录数':>10} {'最早日期':>12} {'最晚日期':>12}")
                print("   " + "-" * 65)
                for row in stats:
                    print(f"   {row[0]:<25} {row[1]:>10} {row[2]:>12} {row[3]:>12}")

            print("\n" + "=" * 60)
            print("✓ 回填成功完成")
            print("=" * 60)

    except Exception as e:
        print(f"\n✗ 回填失败: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
