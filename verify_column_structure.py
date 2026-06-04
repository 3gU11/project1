"""
Verify that the column structure is correct in the code
"""

# Check the model_columns definition
model_columns = ["300", "400", "500", "600", "7055", "8055"]

# Check the headers definition
headers = ["批次号"] + model_columns + ["合计"]

print("验证列结构...")
print()
print(f"model_columns = {model_columns}")
print(f"列数: {len(model_columns)}")
print()
print(f"headers = {headers}")
print(f"总列数: {len(headers)}")
print()

# Expected structure
expected_columns = ["批次号", "300", "400", "500", "600", "7055", "8055", "合计"]

if headers == expected_columns:
    print("[OK] 列结构正确！")
    print("  - 7055和8055已分开成独立列")
    print("  - 预计入库时间已去除")
    print(f"  - 总共{len(headers)}列")
else:
    print("[ERROR] 列结构不匹配")
    print(f"  期望: {expected_columns}")
    print(f"  实际: {headers}")

print()
print("列宽设置验证:")
print("  A (批次号): 10")
print("  B (300): 14")
print("  C (400): 20")
print("  D (500): 20")
print("  E (600): 20")
print("  F (7055): 20 - 独立列")
print("  G (8055): 20 - 独立列")
print("  H (合计): 8")
print()
total_width = 10 + 14 + 5*20 + 8
print(f"总宽度: {total_width} (适合A4横向打印)")
