import io
import re

def final_fix_v6():
    # 1. Update insert_units_from_fg.sql
    path1 = 'd:/CURSORpj/V7STD1.0/scripts/insert_units_from_fg.sql'
    with io.open(path1, 'r', encoding='utf-8') as f:
        content = f.read()

    # Simplify order_remark to only use fg.合同备注 as requested
    new_fg_matched = """fg_matched AS (
    SELECT
        fg.`流水号`  AS serial_no,
        fg.`机型`    AS model_name,
        COALESCE(
            NULLIF(TRIM(fg.`合同号`), ''), 
            fp.`合同号`,
            REGEXP_SUBSTR(fg.`合同备注`, 'HT[0-9]{10,}'),
            REGEXP_SUBSTR(so.`备注`, 'HT[0-9]{10,}')
        ) AS contract_no,
        COALESCE(NULLIF(TRIM(fg.`客户`), ''), so.`客户名`, fp.`客户名`) AS customer,
        COALESCE(NULLIF(TRIM(fg.`代理商`), ''), so.`代理商`, fp.`代理商`) AS dealer_name,
        fg.`合同备注` AS order_remark,
        COALESCE(DATE(so.`发货时间`), 
                 STR_TO_DATE(NULLIF(TRIM(fp.`要求交期`), ''), '%Y-%m-%d'),
                 DATE(fp.`要求交期`)
        ) AS due_date,
        b.batch_id
    FROM finished_goods_data fg
    INNER JOIN batches b
            ON CONVERT(b.batch_code USING utf8mb4) COLLATE utf8mb4_general_ci
             = CONVERT(fg.`批次号`  USING utf8mb4) COLLATE utf8mb4_general_ci
           AND b.status IN ('Predicted', 'Confirmed', 'In_Production')
    LEFT JOIN sales_orders so ON (so.`订单号` = fg.`占用订单号` AND NULLIF(TRIM(fg.`占用订单号`), '') IS NOT NULL)
    LEFT JOIN factory_plan fp ON (
        (fp.`订单号` = fg.`占用订单号` AND NULLIF(TRIM(fg.`占用订单号`), '') IS NOT NULL)
        OR 
        (fp.`合同号` = fg.`合同号` AND NULLIF(TRIM(fg.`合同号`), '') IS NOT NULL AND fp.`机型` = fg.`机型`)
    )
    WHERE fg.`状态` IN ('待入库', '库存中', '待发货', '已出库')
"""
    # Replace the fg_matched block
    content = re.sub(r"fg_matched AS \(\n    SELECT.*?FROM finished_goods_data fg.*?WHERE fg\.`状态` IN \(.*?\)", new_fg_matched, content, flags=re.DOTALL)

    with io.open(path1, 'w', encoding='utf-8') as f:
        f.write(content)


    # 2. Update assign_fg_to_lines.sql
    path2 = 'd:/CURSORpj/V7STD1.0/scripts/assign_fg_to_lines.sql'
    with io.open(path2, 'r', encoding='utf-8') as f:
        content2 = f.read()

    new_fg_candidates = """fg_candidates AS (
    SELECT 
        fg.`流水号` AS serial_no,
        fg.`机型`   AS model_name,
        fg.`批次号` AS fg_batch_code,
        COALESCE(
            NULLIF(TRIM(fg.`合同号`), ''), 
            fp.`合同号`,
            REGEXP_SUBSTR(fg.`合同备注`, 'HT[0-9]{10,}'),
            REGEXP_SUBSTR(so.`备注`, 'HT[0-9]{10,}')
        ) AS contract_no,
        COALESCE(NULLIF(TRIM(fg.`客户`), ''), so.`客户名`, fp.`客户名`) AS customer,
        COALESCE(NULLIF(TRIM(fg.`代理商`), ''), so.`代理商`, fp.`代理商`) AS dealer_name,
        fg.`合同备注` AS order_remark,
        COALESCE(DATE(so.`发货时间`), 
                 STR_TO_DATE(NULLIF(TRIM(fp.`要求交期`), ''), '%Y-%m-%d'),
                 DATE(fp.`要求交期`)
        ) AS due_date,
        b.batch_id,
        b.production_line_id,
        ROW_NUMBER() OVER (PARTITION BY b.batch_id ORDER BY fg.`流水号`) AS slot_index
    FROM finished_goods_data fg
    INNER JOIN batches b 
       ON CONVERT(b.batch_code USING utf8mb4) COLLATE utf8mb4_general_ci = 
          CONVERT(fg.`批次号` USING utf8mb4) COLLATE utf8mb4_general_ci
      AND b.batch_id LIKE 'BATCH-SYNC-%'
    LEFT JOIN sales_orders so ON (so.`订单号` = fg.`占用订单号` AND NULLIF(TRIM(fg.`占用订单号`), '') IS NOT NULL)
    LEFT JOIN factory_plan fp ON (
        (fp.`订单号` = fg.`占用订单号` AND NULLIF(TRIM(fg.`占用订单号`), '') IS NOT NULL)
        OR 
        (fp.`合同号` = fg.`合同号` AND NULLIF(TRIM(fg.`合同号`), '') IS NOT NULL AND fp.`机型` = fg.`机型`)
    )
    WHERE fg.`状态` IN ('待入库', '库存中', '待发货', '已出库')
"""
    content2 = re.sub(r"fg_candidates AS \(\n    SELECT.*?FROM finished_goods_data fg.*?WHERE fg\.`状态` IN \(.*?\)", new_fg_candidates, content2, flags=re.DOTALL)

    with io.open(path2, 'w', encoding='utf-8') as f:
        f.write(content2)

if __name__ == "__main__":
    final_fix_v6()
