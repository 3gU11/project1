import os

log_path = r"C:\Users\zc123\.gemini\antigravity\brain\1fe1221a-f42e-46b8-b75a-60d9facb6018\.system_generated\tasks\task-692.log"
if not os.path.exists(log_path):
    print("Log file does not exist:", log_path)
    # Check parent directory
    parent = os.path.dirname(log_path)
    if os.path.exists(parent):
        print("Files in parent dir:", os.listdir(parent))
else:
    print("Log file exists. Size:", os.path.getsize(log_path))
    with open(log_path, 'r', encoding='utf-8', errors='ignore') as f:
        lines = f.readlines()
    print("Total lines:", len(lines))
    print("\n=== Matching lines ===")
    for i, line in enumerate(lines):
        if any(w in line for w in ['reject', 'DO2026', '500', 'Exception', 'Error', 'fail', '驳回']):
            print(f"{i+1}: {line.strip()}")
