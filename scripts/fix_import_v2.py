import re

def fix_sql_files():
    # 1. Update insert_units_from_fg.sql
    with open('d:/CURSORpj/V7STD1.0/scripts/insert_units_from_fg.sql', 'r', encoding='utf-8') as f:
        content = f.read()

    # Define the new fg_matched CTE with joins
    new_fg_matched = """fg_matched AS (
    SELECT
        fg.`流水号`  AS serial_no,
        fg.`机型`    AS model_name,
        COALESCE(NULLIF(TRIM(fg.`合同号`), ''), fp.`合同号`) AS contract_no,
        COALESCE(NULLIF(TRIM(fg.`客户`), ''), so.`客户名`, fp.`客户名`) AS customer,
        COALESCE(NULLIF(TRIM(fg.`代理商`), ''), so.`代理商`, fp.`代理商`) AS dealer_name,
        CONCAT_WS(' | ', 
            NULLIF(TRIM(fg.`订单备注`), ''), 
            NULLIF(TRIM(fg.`机台备注/配置`), ''),
            NULLIF(TRIM(so.`备注`), ''),
            NULLIF(TRIM(fp.`备注`), '')
        ) AS order_remark,
        COALESCE(so.`发货时间`, fp.`要求交期`) AS due_date,
        b.batch_id
    FROM finished_goods_data fg
    INNER JOIN batches b
            ON CONVERT(b.batch_code USING utf8mb4) COLLATE utf8mb4_general_ci
             = CONVERT(fg.`批次号`  USING utf8mb4) COLLATE utf8mb4_general_ci
           AND b.status IN ('Predicted', 'Confirmed', 'In_Production')
    LEFT JOIN sales_orders so ON so.`订单号` = fg.`占用订单号`
    LEFT JOIN factory_plan fp ON fp.`订单号` = fg.`占用订单号`
    WHERE fg.`状态` IN ('待入库', '库存中', '待发货', '已出库')
"""

    # Replace the old fg_matched block. We use a regex to find the start and end of the CTE.
    content = re.sub(r"fg_matched AS \(\n    SELECT.*?FROM finished_goods_data fg.*?WHERE fg\.`状态` IN \(.*?\)", new_fg_matched, content, flags=re.DOTALL)

    # Add due_date to alloc CTE
    content = content.replace("fm.order_remark,", "fm.order_remark,\n        fm.due_date,")

    # Add due_date to INSERT INTO
    if "due_date" not in content.split("INSERT INTO units (")[1].split(")")[0]:
        content = content.replace(
            "    order_remark,",
            "    order_remark,\n    due_date,"
        )

    # Add due_date to final SELECT
    content = content.replace("order_remark,", "order_remark,\n    due_date,")

    # Add due_date to ON DUPLICATE KEY UPDATE
    if "due_date = VALUES(due_date)" not in content.split("ON DUPLICATE KEY UPDATE")[1]:
        content = content.replace(
            "order_remark = VALUES(order_remark),",
            "order_remark = VALUES(order_remark),\n    due_date = VALUES(due_date),"
        )

    with open('d:/CURSORpj/V7STD1.0/scripts/insert_units_from_fg.sql', 'w', encoding='utf-8') as f:
        f.write(content)


    # 2. Update assign_fg_to_lines.sql
    with open('d:/CURSORpj/V7STD1.0/scripts/assign_fg_to_lines.sql', 'r', encoding='utf-8') as f:
        content2 = f.read()

    new_fg_candidates = """fg_candidates AS (
    SELECT 
        fg.`流水号` AS serial_no,
        fg.`机型`   AS model_name,
        fg.`批次号` AS fg_batch_code,
        COALESCE(NULLIF(TRIM(fg.`合同号`), ''), fp.`合同号`) AS contract_no,
        COALESCE(NULLIF(TRIM(fg.`客户`), ''), so.`客户名`, fp.`客户名`) AS customer,
        COALESCE(NULLIF(TRIM(fg.`代理商`), ''), so.`代理商`, fp.`代理商`) AS dealer_name,
        CONCAT_WS(' | ', 
            NULLIF(TRIM(fg.`订单备注`), ''), 
            NULLIF(TRIM(fg.`机台备注/配置`), ''),
            NULLIF(TRIM(so.`备注`), ''),
            NULLIF(TRIM(fp.`备注`), '')
        ) AS order_remark,
        COALESCE(so.`发货时间`, fp.`要求交期`) AS due_date,
        b.batch_id,
        b.production_line_id,
        ROW_NUMBER() OVER (PARTITION BY b.batch_id ORDER BY fg.`流水号`) AS slot_index
    FROM finished_goods_data fg
    INNER JOIN batches b 
       ON CONVERT(b.batch_code USING utf8mb4) COLLATE utf8mb4_general_ci = 
          CONVERT(fg.`批次号` USING utf8mb4) COLLATE utf8mb4_general_ci
      AND b.batch_id LIKE 'BATCH-SYNC-%'
    LEFT JOIN sales_orders so ON so.`订单号` = fg.`占用订单号`
    LEFT JOIN factory_plan fp ON fp.`订单号` = fg.`占用订单号`
    WHERE fg.`状态` IN ('待入库', '库存中', '待发货', '已出库')
"""

    content2 = re.sub(r"fg_candidates AS \(\n    SELECT.*?FROM finished_goods_data fg.*?WHERE fg\.`状态` IN \(.*?\)", new_fg_candidates, content2, flags=re.DOTALL)

    # Add due_date to INSERT INTO
    if "due_date" not in content2.split("INSERT INTO units (")[1].split(")")[0]:
        content2 = content2.replace(
            "    order_remark,",
            "    order_remark,\n    due_date,"
        )

    # Add due_date to final SELECT
    content2 = content2.replace("order_remark,", "order_remark,\n    due_date,")

    # Add due_date to ON DUPLICATE KEY UPDATE
    if "due_date = VALUES(due_date)" not in content2.split("ON DUPLICATE KEY UPDATE")[1]:
        content2 = content2.replace(
            "order_remark = VALUES(order_remark),",
            "order_remark = VALUES(order_remark),\n    due_date = VALUES(due_date),"
        )

    with open('d:/CURSORpj/V7STD1.0/scripts/assign_fg_to_lines.sql', 'w', encoding='utf-8') as f:
        f.write(content2)

if __name__ == "__main__":
    fix_sql_files()
