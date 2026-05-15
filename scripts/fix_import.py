import re

def fix_sql_files():
    # 1. Update insert_units_from_fg.sql
    with open('d:/CURSORpj/V7STD1.0/scripts/insert_units_from_fg.sql', 'r', encoding='utf-8') as f:
        content = f.read()

    # Remove the 占用订单号 condition
    content = re.sub(r"AND\s+\(fg\.`占用订单号`\s+IS\s+NULL\s+OR\s+fg\.`占用订单号`\s*=\s*''\)\n", "", content)

    # We need to add contract_no, customer, dealer_name, order_remark to fg_matched
    if "fg.`合同号`" not in content:
        content = content.replace(
            "fg.`机型`    AS model_name,",
            "fg.`机型`    AS model_name,\n        fg.`合同号`  AS contract_no,\n        fg.`客户`    AS customer,\n        fg.`代理商`  AS dealer_name,\n        CONCAT_WS(' | ', NULLIF(TRIM(fg.`订单备注`), ''), NULLIF(TRIM(fg.`机台备注/配置`), '')) AS order_remark,"
        )

    # We need to add contract_no, customer, dealer_name, order_remark to alloc
    if "fm.contract_no" not in content:
        content = content.replace(
            "fm.model_name,",
            "fm.model_name,\n        fm.contract_no,\n        fm.customer,\n        fm.dealer_name,\n        fm.order_remark,"
        )

    # We need to add to the INSERT INTO
    if "contract_no" not in content.split("INSERT INTO units (")[1].split(")")[0]:
        content = content.replace(
            "    status,\n    serial_no,\n    created_at,\n    updated_at",
            "    status,\n    serial_no,\n    contract_no,\n    customer,\n    dealer_name,\n    order_remark,\n    created_at,\n    updated_at"
        )
    
    # We need to add to the SELECT before ON DUPLICATE KEY UPDATE
    if "contract_no," not in content.split("ON DUPLICATE KEY UPDATE")[0].split("SELECT")[-1]:
        content = content.replace(
            "    serial_no,\n    NOW()       AS created_at,\n    NOW()       AS updated_at",
            "    serial_no,\n    contract_no,\n    customer,\n    dealer_name,\n    order_remark,\n    NOW()       AS created_at,\n    NOW()       AS updated_at"
        )

    # We need to add to ON DUPLICATE KEY UPDATE
    if "contract_no  = VALUES(contract_no)" not in content.split("ON DUPLICATE KEY UPDATE")[1]:
        content = content.replace(
            "    serial_no  = VALUES(serial_no),\n    updated_at = NOW();",
            "    serial_no  = VALUES(serial_no),\n    contract_no = VALUES(contract_no),\n    customer = VALUES(customer),\n    dealer_name = VALUES(dealer_name),\n    order_remark = VALUES(order_remark),\n    updated_at = NOW();"
        )

    with open('d:/CURSORpj/V7STD1.0/scripts/insert_units_from_fg.sql', 'w', encoding='utf-8') as f:
        f.write(content)


    # 2. Update assign_fg_to_lines.sql
    with open('d:/CURSORpj/V7STD1.0/scripts/assign_fg_to_lines.sql', 'r', encoding='utf-8') as f:
        content2 = f.read()

    # Remove the 占用订单号 condition
    content2 = re.sub(r"AND\s+\(fg\.`占用订单号`\s+IS\s+NULL\s+OR\s+fg\.`占用订单号`\s*=\s*''\)\n", "", content2)

    with open('d:/CURSORpj/V7STD1.0/scripts/assign_fg_to_lines.sql', 'w', encoding='utf-8') as f:
        f.write(content2)

if __name__ == "__main__":
    fix_sql_files()
