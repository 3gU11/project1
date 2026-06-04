"""
Analyze the column logic in the code
"""

model_columns = ["300", "400", "500", "600", "7055", "8055"]
headers = ["批次号"] + model_columns + ["合计"]

print("列结构分析:")
print(f"model_columns = {model_columns} (长度: {len(model_columns)})")
print(f"headers = {headers} (长度: {len(headers)})")
print()

total_cols = len(headers)
print(f"total_cols = {total_cols}")
print()

print("列索引映射:")
for idx, col_name in enumerate(headers, 1):
    print(f"  列{idx}: {col_name}")

print()
print("代码中的列索引:")
print(f"  批次号列: 1")
print(f"  机型列开始: 2 (对应 {model_columns[0]})")
print(f"  机型列结束: {1 + len(model_columns)} (对应 {model_columns[-1]})")
print(f"  合计列 (total_cols - 1): {total_cols - 1} (对应 {headers[total_cols - 2]})")
print(f"  最后一列 (total_cols): {total_cols} (对应 {headers[total_cols - 1]})")
print()

print("问题分析:")
print(f"  headers有{len(headers)}列: {headers}")
print(f"  但代码写入了{total_cols}列数据")
print(f"  其中 total_cols-1 = {total_cols-1} 是合计列")
print(f"  total_cols = {total_cols} 是最后一列")
print()

if total_cols == len(headers):
    print("[OK] 列数匹配")
    print()
    print("但是！代码在第2179行写入了 total_cols 列（第9列）")
    print("这意味着代码认为有9列，但headers只定义了8列！")
    print()
    print("原因：代码还在写入'预计入库时间'数据到最后一列！")
else:
    print("[ERROR] 列数不匹配")

