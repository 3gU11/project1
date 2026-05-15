import pymysql

DB_CONFIG = {
    "host": "localhost",
    "user": "root",
    "password": "030705",
    "database": "rjfinshed",
    "charset": "utf8mb4"
}

MAPPING = [
    ('05-08', 'line-09'),
    ('05-07', 'line-08'),
    ('05-06', 'line-02'),
    ('05-05附加', 'line-18'),
    ('05-02', 'line-04'),
    ('05-05', 'line-12'),
    ('05-04', 'line-03'),
    ('04-06附加', 'line-19'),
    ('03-03附加', 'line-19'),
    ('05-03', 'line-13'),
    ('05-01', 'line-10'),
    ('04-22', 'line-14'),
    ('04-21', 'line-15'),
    ('04-20', 'line-06'),
    ('04-19附加', 'line-19'),
    ('04-19', 'line-05'),
    ('04-18', 'line-07'),
    ('04-16', 'line-11'),
    ('04-14', 'line-01'),
    ('04-10', 'line-17'),
    ('04-09', 'line-16'),
    ('03-16附加', 'line-18'),
    ('02-08附加', 'line-18'),
    ('11-14', 'line-18')
]

def custom_import():
    conn = pymysql.connect(**DB_CONFIG)
    try:
        cursor = conn.cursor()
        
        for batch_code, target_line_id in MAPPING:
            batch_id = f"BATCH-SYNC-{batch_code}"
            
            # Get model type
            cursor.execute("SELECT `机型` FROM finished_goods_data WHERE `批次号` = %s LIMIT 1", (batch_code,))
            row = cursor.fetchone()
            if not row:
                print(f"Skipping batch {batch_code}: No data in finished_goods_data.")
                continue
            model_type = row[0]
            
            print(f"Syncing batch {batch_code} to {target_line_id}...")

            # Insert/Update batch
            cursor.execute("""
                INSERT INTO batches (batch_id, batch_code, batch_no, model_type, production_line_id, status, capacity, source, created_at, updated_at)
                VALUES (%s, %s, 1, %s, %s, 'In_Production', 20, 'manual_sync', NOW(), NOW())
                ON DUPLICATE KEY UPDATE 
                    production_line_id = %s,
                    status = 'In_Production',
                    updated_at = NOW()
            """, (batch_id, batch_code, model_type, target_line_id, target_line_id))

            # Update line status
            cursor.execute("UPDATE production_lines SET status = 'Busy' WHERE line_id = %s", (target_line_id,))

            # Import units
            import_sql = """
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
            print(f"   Done. Imported {cursor.rowcount} units.")
        
        conn.commit()
        print("\nCustom import finished successfully!")

    finally:
        conn.close()

if __name__ == "__main__":
    custom_import()
