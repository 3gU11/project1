with open("api/routes/sandbox.py", "rb") as f:
    content = f.read()

lines = content.split(b"\n")
for idx in [196, 197, 198, 199, 224, 225, 226, 227]:
    if idx < len(lines):
        line_bytes = lines[idx]
        print(f"Line {idx+1} hex: {line_bytes.hex()}")
        try:
            print(f"Line {idx+1} utf8: {line_bytes.decode('utf-8')}")
        except Exception as e:
            print(f"Line {idx+1} utf8 error: {e}")
        try:
            print(f"Line {idx+1} gbk: {line_bytes.decode('gbk')}")
        except Exception as e:
            print(f"Line {idx+1} gbk error: {e}")
        print()
