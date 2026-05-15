import pymysql

DB_CONFIG = {
    "host": "localhost",
    "user": "root",
    "password": "030705",
    "database": "rjfinshed",
    "charset": "utf8mb4"
}

def test_sync(batch_code, target_line_id):
    conn = pymysql.connect(**DB_CONFIG)
    try:
        cursor = conn.cursor()
        batch_id = f"BATCH-SYNC-{batch_code}"
        
        # 0. Get model type
        cursor.execute("SELECT `机型` FROM finished_goods_data WHERE `批次号` = %s LIMIT 1", (batch_code,))
        row = cursor.fetchone()
        model_type = row[0] if row else "Unknown"
        
        print(f"Syncing batch {batch_code} (Model: {model_type}) to {target_line_id}...")

        # 1. Update batch
        cursor.execute("""
            INSERT INTO batches (batch_id, batch_code, batch_no, model_type, production_line_id, status, capacity, source, created_at, updated_at)
            VALUES (%s, %s, 1, %s, %s, 'In_Production', 20, 'manual_sync', NOW(), NOW())
            ON DUPLICATE KEY UPDATE 
                production_line_id = %s,
                status = 'In_Production',
                updated_at = NOW()
        """, (batch_id, batch_code, model_type, target_line_id, target_line_id))

        # 2. Clear old units
        cursor.execute("DELETE FROM units WHERE batch_id = %s", (batch_id,))

        # 3. Import data
        import_sql = """
        INSERT INTO units (
            unit_id, serial_no, batch_id, slot_index, model_type, 
            contract_no, customer, dealer_name, order_remark, due_date, status, created_at, updated_at
        )
        SELECT 
            CONCAT(b.batch_id, '_', ROW_NUMBER() OVER (PARTITION BY b.batch_id ORDER BY fg.`流水号`)),
            fg.`流水号`,
            b.batch_id,
            ROW_NUMBER() OVER (PARTITION BY b.batch_id ORDER BY fg.`流水号`),
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
            COALESCE(DATE(so.`发货时间`), 
                     STR_TO_DATE(NULLIF(TRIM(fp.`要求交期`), ''), '%%Y-%%m-%%d'),
                     DATE(fp.`要求交期`)
            ),
            'In_Production',
            NOW(),
            NOW()
        FROM finished_goods_data fg
        JOIN batches b ON b.batch_code = fg.`批次号` COLLATE utf8mb4_general_ci
        LEFT JOIN sales_orders so ON (so.`订单号` = fg.`占用订单号` COLLATE utf8mb4_general_ci AND NULLIF(TRIM(fg.`占用订单号`), '') IS NOT NULL)
        LEFT JOIN factory_plan fp ON (
            (fp.`订单号` = fg.`占用订单号` COLLATE utf8mb4_general_ci AND NULLIF(TRIM(fg.`占用订单号`), '') IS NOT NULL)
            OR 
            (fp.`合同号` = fg.`合同号` COLLATE utf8mb4_general_ci AND NULLIF(TRIM(fg.`合同号`), '') IS NOT NULL AND fp.`机型` = fg.`机型` COLLATE utf8mb4_general_ci)
        )
        WHERE b.batch_id = %s
        """
        cursor.execute(import_sql, (batch_id,))
        count = cursor.rowcount
        conn.commit()
        print(f"Successfully imported {count} units.")
    finally:
        conn.close()

if __name__ == "__main__":
    test_sync("04-14", "line-1")
