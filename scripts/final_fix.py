import io

def final_fix():
    # Final fix for insert_units_from_fg.sql
    path1 = 'd:/CURSORpj/V7STD1.0/scripts/insert_units_from_fg.sql'
    with io.open(path1, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Correct the alloc CTE duplicates
    content = content.replace("fm.order_remark,\n    due_date,\n        fm.due_date,", "fm.order_remark,\n        fm.due_date,")
    # Correct the final SELECT duplicates
    content = content.replace("order_remark,\n    due_date,\n    due_date,", "order_remark,\n    due_date,")
    # Correct the INSERT INTO duplicates
    content = content.replace("order_remark,\n    due_date,\n    due_date,", "order_remark,\n    due_date,")
    
    with io.open(path1, 'w', encoding='utf-8') as f:
        f.write(content)

    # Final fix for assign_fg_to_lines.sql
    path2 = 'd:/CURSORpj/V7STD1.0/scripts/assign_fg_to_lines.sql'
    with io.open(path2, 'r', encoding='utf-8') as f:
        content2 = f.read()
    
    # Correct the fg_candidates SELECT duplicates
    # Since I don't know the exact spacing, I'll do a line-based cleanup
    lines = content2.splitlines()
    new_lines = []
    last_line = ""
    for line in lines:
        if "due_date" in line and "due_date" in last_line:
            continue
        new_lines.append(line)
        last_line = line
    
    content2 = "\n".join(new_lines)
    
    with io.open(path2, 'w', encoding='utf-8') as f:
        f.write(content2)

if __name__ == "__main__":
    final_fix()
