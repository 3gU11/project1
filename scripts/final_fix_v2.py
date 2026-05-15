import io

def final_fix_v2():
    # 1. Fix insert_units_from_fg.sql
    path1 = 'd:/CURSORpj/V7STD1.0/scripts/insert_units_from_fg.sql'
    with io.open(path1, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Ensure due_date is in the SELECT list
    if "order_remark,\n    due_date,\n    NOW()" not in content:
         content = content.replace("order_remark,\n    due_date,\n    due_date,", "order_remark,\n    due_date,") # Cleanup
         content = content.replace("order_remark,\n    NOW()", "order_remark,\n    due_date,\n    NOW()")

    with io.open(path1, 'w', encoding='utf-8') as f:
        f.write(content)

    # 2. Fix assign_fg_to_lines.sql
    path2 = 'd:/CURSORpj/V7STD1.0/scripts/assign_fg_to_lines.sql'
    with io.open(path2, 'r', encoding='utf-8') as f:
        content2 = f.read()
    
    # Ensure due_date is in the SELECT list
    if "order_remark,\n    due_date,\n    NOW()" not in content2:
        content2 = content2.replace("order_remark,\n    NOW()", "order_remark,\n    due_date,\n    NOW()")

    with io.open(path2, 'w', encoding='utf-8') as f:
        f.write(content2)

if __name__ == "__main__":
    final_fix_v2()
