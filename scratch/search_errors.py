with open('api-launcher.out.log', 'r', encoding='utf-8', errors='ignore') as f:
    lines = f.readlines()

print("Total lines in api-launcher.out.log:", len(lines))
tracebacks = []
for i, line in enumerate(lines):
    if "Traceback" in line or "Exception" in line or "Error" in line or "fail" in line or "detail=" in line:
        tracebacks.append(i)

print("Found lines starting at:", tracebacks)
for idx in tracebacks[-30:]: # last 30
    print(f"\n--- Context for line {idx+1} ---")
    start = max(0, idx - 2)
    end = min(len(lines), idx + 10)
    for j in range(start, end):
        print(f"{j+1}: {lines[j].strip()}")
