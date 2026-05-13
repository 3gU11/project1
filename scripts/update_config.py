import io

def fix_config():
    path = "d:/CURSORpj/V7STD1.0/config.py"
    with io.open(path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    content = content.replace('"label": "👑 老板计划"', '"label": "👑 预测沙盘/生产看板"')
    
    with io.open(path, 'w', encoding='utf-8') as f:
        f.write(content)

if __name__ == "__main__":
    fix_config()
