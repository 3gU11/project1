"""
修复 BATCH-SYNC-04-19 / BATCH-SYNC-04-20 中因 factory_plan LEFT JOIN 笛卡尔积
导致的重复 unit 记录。
逻辑与 sync_batch_app.py 完全一致，仅将 factory_plan JOIN 的条件1加上机型限制。
"""
import pymysql

DB = dict(host="localhost", user="root", password="030705",
          database="rjfinshed", charset="utf8mb4")

# 需要重新同步的批次（batch_code → target_line_id）
BATCHES_TO_FIX = {
    "04-19": "line-05",
    "04-20": "line-06",
}

IMPORT_SQL = """
INSERT INTO units (
    unit_id, serial_no, batch_id, production_line_id, slot_index, model_type,
    contract_no, customer, dealer_name, order_remark, due_date, status, created_at, updated_at
)
SELECT
    CONCAT(b.batch_id, '_', ROW_NUMBER() OVER (PARTITION BY b.batch_id ORDER BY fg.`流水号` COLLATE utf8mb4_general_ci)),
    fg.`流水号`,
    b.batch_id,
    b.production_line_id,
    ROW_NUMBER() OVER (PARTITION BY b.batch_id ORDER BY fg.`流水号` COLLATE utf8mb4_general_ci),
    fg.`机型`,
    COALESCE(
        NULLIF(TRIM(fg.`合同号`), ''),
        fp.`合同号`,
        REGEXP_SUBSTR(fg.`合同备注`, 'HT[0-9]{10,}'),
        REGEXP_SUBSTR(fg.`订单备注`, 'HT[0-9]{10,}'),
        REGEXP_SUBSTR(so.`备注`, 'HT[0-9]{10,}')
    ),
    COALESCE(NULLIF(TRIM(fg.`客户`), ''), so.`客户名`, fp.`客户名`),
    COALESCE(NULLIF(TRIM(fg.`代理商`), ''), so.`代理商`, fp.`代理商`),
    COALESCE(NULLIF(TRIM(fg.`合同备注`), ''), NULLIF(TRIM(fg.`订单备注`), '')),
    COALESCE(
        DATE(so.`发货时间`),
        STR_TO_DATE(NULLIF(TRIM(fp.`要求交期`), ''), '%%Y-%%m-%%d'),
        DATE(fp.`要求交期`)
    ),
    'In_Production',
    NOW(),
    NOW()
FROM finished_goods_data fg
JOIN batches b ON b.batch_code = fg.`批次号` COLLATE utf8mb4_general_ci
LEFT JOIN sales_orders so ON (
    so.`订单号` = fg.`占用订单号` COLLATE utf8mb4_general_ci
    AND NULLIF(TRIM(fg.`占用订单号`), '') IS NOT NULL
)
LEFT JOIN factory_plan fp ON (
    -- 两个分支都加机型限制，防止同一订单多机型时笛卡尔积
    (fp.`订单号` = fg.`占用订单号` COLLATE utf8mb4_general_ci
        AND NULLIF(TRIM(fg.`占用订单号`), '') IS NOT NULL
        AND fp.`机型` = fg.`机型` COLLATE utf8mb4_general_ci)
    OR
    (fp.`合同号` = fg.`合同号` COLLATE utf8mb4_general_ci
        AND NULLIF(TRIM(fg.`合同号`), '') IS NOT NULL
        AND fp.`机型` = fg.`机型` COLLATE utf8mb4_general_ci)
)
WHERE b.batch_id = %s
"""

def resync_batch(cursor, batch_code, line_id):
    batch_id = f"BATCH-SYNC-{batch_code}"
    print(f"\n{'='*55}")
    print(f"  批次: {batch_id}  →  产线: {line_id}")
    print(f"{'='*55}")

    # 重算前先看旧数量
    cursor.execute("SELECT COUNT(*), COUNT(DISTINCT contract_no) FROM units WHERE batch_id = %s", (batch_id,))
    old_cnt, old_contracts = cursor.fetchone()
    print(f"  修复前: {old_cnt} 条 unit（{old_contracts} 个合同）")

    # 删除旧 unit 数据
    cursor.execute("DELETE FROM units WHERE batch_id = %s", (batch_id,))
    print(f"  已删除旧数据 ({cursor.rowcount} 行)")

    # 重新导入（修复后的 SQL）
    cursor.execute(IMPORT_SQL, (batch_id,))
    new_cnt = cursor.rowcount
    print(f"  重新导入: {new_cnt} 条 unit")

    # 验证重复情况
    cursor.execute("""
        SELECT contract_no, COUNT(*) AS cnt
        FROM units
        WHERE batch_id = %s AND contract_no IS NOT NULL AND TRIM(contract_no) != ''
        GROUP BY contract_no
        HAVING cnt > 5
        ORDER BY cnt DESC
        LIMIT 5
    """, (batch_id,))
    leftovers = cursor.fetchall()
    if leftovers:
        print(f"  [!]  Still-high-dup contracts: {leftovers}")
    else:
        print(f"  [OK] No abnormal duplicates")

    return old_cnt, new_cnt


def main():
    conn = pymysql.connect(**DB)
    try:
        cursor = conn.cursor()
        results = []
        for batch_code, line_id in BATCHES_TO_FIX.items():
            old, new = resync_batch(cursor, batch_code, line_id)
            results.append((batch_code, old, new))
        conn.commit()
        print(f"\n{'='*55}")
        print("  汇总")
        print(f"{'='*55}")
        for batch_code, old, new in results:
            delta = old - new
            print(f"  BATCH-SYNC-{batch_code}: {old} → {new}  (减少 {delta} 条重复)")
        print("\n[OK] All done. Changes committed.")
    except Exception as e:
        conn.rollback()
        print(f"\n[ERR] Rolled back: {e}")
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    main()
