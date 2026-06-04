"""
检查完工报表数据完整性的脚本
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from database import get_engine
from sqlalchemy import text


def check_completion_data():
    """检查完工报表数据情况"""
    print("=" * 60)
    print("完工报表数据检查")
    print("=" * 60)

    with get_engine().connect() as conn:
        # 1. 检查 production_history_ledger 表是否存在
        print("\n1. 检查表是否存在...")
        result = conn.execute(text("""
            SELECT COUNT(*) FROM information_schema.tables
            WHERE table_schema = DATABASE()
            AND table_name = 'production_history_ledger'
        """)).fetchone()

        if result[0] == 0:
            print("   ❌ production_history_ledger 表不存在")
            return
        else:
            print("   ✓ production_history_ledger 表存在")

        # 2. 统计总记录数
        print("\n2. 统计记录数...")
        result = conn.execute(text("""
            SELECT
                COUNT(*) AS total,
                SUM(CASE WHEN status = 'Completed' THEN 1 ELSE 0 END) AS completed,
                SUM(CASE WHEN status = 'In_Production' THEN 1 ELSE 0 END) AS in_production,
                SUM(CASE WHEN status = 'Cancelled' THEN 1 ELSE 0 END) AS cancelled
            FROM production_history_ledger
        """)).fetchone()

        print(f"   总记录数: {result[0]}")
        print(f"   已完工: {result[1]}")
        print(f"   生产中: {result[2]}")
        print(f"   已撤销: {result[3]}")

        # 3. 检查流水号情况
        print("\n3. 检查流水号绑定情况...")
        result = conn.execute(text("""
            SELECT
                COUNT(*) AS total_completed,
                SUM(CASE WHEN u.serial_no IS NOT NULL AND u.serial_no != '' THEN 1 ELSE 0 END) AS has_serial,
                SUM(CASE WHEN u.serial_no IS NULL OR u.serial_no = '' THEN 1 ELSE 0 END) AS no_serial
            FROM production_history_ledger phl
            LEFT JOIN units u ON u.unit_id = phl.unit_id
            WHERE phl.status = 'Completed'
        """)).fetchone()

        if result[0] > 0:
            print(f"   已完工机台: {result[0]}")
            print(f"   有流水号: {result[1]} ({result[1]/result[0]*100:.1f}%)")
            print(f"   无流水号: {result[2]} ({result[2]/result[0]*100:.1f}%)")
        else:
            print("   暂无已完工机台")

        # 4. 检查最近完工记录
        print("\n4. 最近完工记录（前5条）...")
        result = conn.execute(text("""
            SELECT
                phl.unit_id,
                phl.model_type,
                phl.batch_code,
                DATE_FORMAT(phl.completed_at, '%Y-%m-%d %H:%i') AS completed_at,
                COALESCE(u.serial_no, u.forecast_serial_no, '无') AS serial_no,
                phl.customer,
                phl.contract_no
            FROM production_history_ledger phl
            LEFT JOIN units u ON u.unit_id = phl.unit_id
            WHERE phl.status = 'Completed'
            ORDER BY phl.completed_at DESC
            LIMIT 5
        """)).fetchall()

        if result:
            print(f"\n   {'机台ID':<15} {'机型':<15} {'完工时间':<20} {'流水号':<20} {'客户':<15}")
            print("   " + "-" * 90)
            for row in result:
                print(f"   {row[0]:<15} {row[1]:<15} {row[3]:<20} {row[4]:<20} {row[5] or '无':<15}")
        else:
            print("   暂无完工记录")

        # 5. 按月统计完工数量
        print("\n5. 按月统计完工数量...")
        result = conn.execute(text("""
            SELECT
                DATE_FORMAT(completed_at, '%Y-%m') AS month,
                COUNT(*) AS count
            FROM production_history_ledger
            WHERE status = 'Completed'
            GROUP BY DATE_FORMAT(completed_at, '%Y-%m')
            ORDER BY month DESC
            LIMIT 6
        """)).fetchall()

        if result:
            print(f"\n   {'月份':<15} {'完工数量':<10}")
            print("   " + "-" * 30)
            for row in result:
                print(f"   {row[0]:<15} {row[1]:<10}")
        else:
            print("   暂无完工记录")

        # 6. 对比 finished_goods_data 中的数据
        print("\n6. 对比实际库存数据...")
        result = conn.execute(text("""
            SELECT
                COUNT(DISTINCT fg.流水号) AS total_in_fgd,
                COUNT(DISTINCT phl.unit_id) AS total_completed_in_phl
            FROM finished_goods_data fg
            LEFT JOIN units u ON u.serial_no = fg.流水号
            LEFT JOIN production_history_ledger phl ON phl.unit_id = u.unit_id AND phl.status = 'Completed'
        """)).fetchone()

        print(f"   finished_goods_data 中的机台数: {result[0]}")
        print(f"   production_history_ledger 中已完工: {result[1]}")

        if result[0] > result[1]:
            print(f"   ⚠️  差异: {result[0] - result[1]} 台机器在库存中但没有完工记录")
            print("   可能原因: 历史数据、直接导入、或未通过沙盘系统生产")

        print("\n" + "=" * 60)
        print("检查完成")
        print("=" * 60)


if __name__ == "__main__":
    check_completion_data()
