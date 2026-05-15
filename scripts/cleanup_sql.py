import io

def fix_sql_content():
    # Fix insert_units_from_fg.sql
    path1 = 'd:/CURSORpj/V7STD1.0/scripts/insert_units_from_fg.sql'
    with io.open(path1, 'r', encoding='utf-8') as f:
        lines = f.readlines()
    
    new_lines = []
    seen_due_date_insert = False
    seen_due_date_select = False
    
    for i, line in enumerate(lines):
        # Fix lines 88-89 area (INSERT INTO)
        if "due_date," in line and 77 <= i + 1 <= 92:
            if not seen_due_date_insert:
                new_lines.append(line)
                seen_due_date_insert = True
            continue
        
        # Fix lines 109-110 area (SELECT in CTE)
        if "due_date," in line and "COALESCE" not in line and 100 <= i + 1 <= 120:
             continue
        
        new_lines.append(line)
    
    # Also need to check if there are duplicates in ON DUPLICATE KEY
    final_lines = []
    seen_due_date_update = False
    for line in new_lines:
        if "due_date = VALUES(due_date)," in line:
            if not seen_due_date_update:
                final_lines.append(line)
                seen_due_date_update = True
            continue
        final_lines.append(line)

    with io.open(path1, 'w', encoding='utf-8') as f:
        f.writelines(final_lines)

    # Fix assign_fg_to_lines.sql (similar issue likely)
    path2 = 'd:/CURSORpj/V7STD1.0/scripts/assign_fg_to_lines.sql'
    with io.open(path2, 'r', encoding='utf-8') as f:
        lines2 = f.readlines()
    
    new_lines2 = []
    seen_due_date_insert2 = False
    for line in lines2:
        if "due_date," in line and "INSERT INTO units" in "".join(lines2[max(0, lines2.index(line)-20):lines2.index(line)]):
             if not seen_due_date_insert2:
                 new_lines2.append(line)
                 seen_due_date_insert2 = True
             continue
        
        if "due_date," in line and "COALESCE" not in line and "fg_candidates" in "".join(lines2[max(0, lines2.index(line)-20):lines2.index(line)]):
            continue
            
        new_lines2.append(line)

    # Simple cleanup for duplicates
    content2 = "".join(new_lines2)
    content2 = content2.replace("due_date,\n    due_date,", "due_date,")
    content2 = content2.replace("due_date = VALUES(due_date),\n    due_date = VALUES(due_date),", "due_date = VALUES(due_date),")
    
    with io.open(path2, 'w', encoding='utf-8') as f:
        f.write(content2)

if __name__ == "__main__":
    fix_sql_content()
