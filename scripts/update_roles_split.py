import io

def fix_roles():
    path = "d:/CURSORpj/V7STD1.0/crud/roles.py"
    with io.open(path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Revert previously changed labels back to original
    content = content.replace('"label": "预测沙盘/生产看板(查看)"', '"label": "预测沙盘(查看)"')
    content = content.replace('"label": "预测沙盘/生产看板(编辑)"', '"label": "预测沙盘(编辑)"')
    
    # Check if KANBAN_VIEW exists
    if '"code": "KANBAN_VIEW"' not in content:
        # Insert KANBAN_VIEW before SANDBOX_VIEW
        content = content.replace(
            '{"code": "SANDBOX_VIEW"',
            '{"code": "KANBAN_VIEW", "label": "生产看板(查看)", "group": "管理与统筹"},\n    {"code": "SANDBOX_VIEW"'
        )
    
    with io.open(path, 'w', encoding='utf-8') as f:
        f.write(content)

def fix_config():
    path = "d:/CURSORpj/V7STD1.0/config.py"
    with io.open(path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Revert config label
    content = content.replace('"label": "👑 预测沙盘/生产看板"', '"label": "👑 预测沙盘"')
    
    # Add KANBAN_VIEW to Admin and Boss
    if '"KANBAN_VIEW"' not in content:
        content = content.replace('"TRACEABILITY", "SANDBOX_VIEW"', '"TRACEABILITY", "KANBAN_VIEW", "SANDBOX_VIEW"')
    
    with io.open(path, 'w', encoding='utf-8') as f:
        f.write(content)

if __name__ == "__main__":
    fix_roles()
    fix_config()
