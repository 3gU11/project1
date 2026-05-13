import io

def fix_roles():
    path = "d:/CURSORpj/V7STD1.0/crud/roles.py"
    with io.open(path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    content = content.replace('"label": "预测沙盘(查看)"', '"label": "预测沙盘/生产看板(查看)"')
    content = content.replace('"label": "预测沙盘(编辑)"', '"label": "预测沙盘/生产看板(编辑)"')
    
    with io.open(path, 'w', encoding='utf-8') as f:
        f.write(content)

if __name__ == "__main__":
    fix_roles()
