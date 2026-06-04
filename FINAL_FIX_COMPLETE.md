# 排产台账Excel格式修复 - 最终版本

## 修复时间
2026-06-01

## 发现的问题

### 根本原因
代码在写入列数据时，列索引计算错误：

**错误的代码（第2167行）：**
```python
ws.cell(row=start_row, column=total_cols - 1).value = total_qty  # 写入第7列（8055列）
```

**错误的代码（第2179行）：**
```python
ws.cell(row=start_row, column=total_cols).value = due_date_str  # 写入第8列（合计列）
```

这导致：
- **8055列（第7列）被写入了合计数据** ❌
- **合计列（第8列）被写入了预计入库时间数据** ❌
- **8055系列机型数据无处显示** ❌

## 修复方案

### 1. 修正合计列索引（第2167行）
```python
# 修复前
ws.cell(row=start_row, column=total_cols - 1).value = total_qty

# 修复后
ws.cell(row=start_row, column=total_cols).value = total_qty
```

### 2. 删除预计入库时间写入代码（第2171-2181行）
完全删除以下代码：
```python
due_dates_list = []
for d in batch["due_dates"]:
    try:
        dt = pd.to_datetime(d)
        due_dates_list.append(f"预计{dt.year}. {dt.month}. {dt.day}")
    except:
        due_dates_list.append(str(d))
due_date_str = ", ".join(sorted(due_dates_list)) if due_dates_list else "-"
ws.cell(row=start_row, column=total_cols).value = due_date_str
if end_row > start_row:
    ws.merge_cells(start_row=start_row, start_column=total_cols, end_row=end_row, end_column=total_cols)
```

## 修复后的列结构

```
列号 | 列名   | 列宽 | 数据内容
-----|--------|------|----------------------------------
1    | 批次号 | 10   | 批次编号
2    | 300    | 14   | FR-300系列机型
3    | 400    | 20   | FR-400系列机型
4    | 500    | 20   | FR-500系列机型
5    | 600    | 20   | FR-600系列 + FR-8060系列
6    | 7055   | 20   | FR-7055系列机型 ✓
7    | 8055   | 20   | FR-8055系列机型 ✓
8    | 合计   | 8    | 总数量 ✓
```

## 验证结果

### 模拟测试通过 ✓
```
批次: 06-01
  FR-400AUTO -> 400列
  FR-500AUTO -> 500列
  FR-7055AUTO -> 7055列
  FR-8055AUTO -> 8055列 ✓
  FR-8055XS(PRO) -> 8055列 ✓
  合计: 5 (写入第8列) ✓

批次: 06-02
  FR-8060AUTO -> 600列
  FR-7055XS(PRO) -> 7055列
  FR-8055AUTO -> 8055列 ✓
  合计: 3 (写入第8列) ✓
```

### 数据验证 ✓
- ✓ 8055列有数据: ['FR-8055AUTO 1', 'FR-8055XS(PRO) 1', 'FR-8055AUTO 1']
- ✓ 合计列数据: [5.0, 3.0]
- ✓ 列结构正确: ['批次号', '300', '400', '500', '600', '7055', '8055', '合计']

## 修改的文件

**api/routes/planning.py**
- 第2167行：修正合计列索引 `total_cols - 1` → `total_cols`
- 第2169行：修正合并单元格列索引
- 第2171-2181行：删除预计入库时间写入代码

## API服务状态

✓ API已重启（进程ID: 27548 → 新进程）  
✓ 代码修改已生效  
✓ 模拟测试通过

## 如何验证

1. 登录系统
2. 进入排产管理页面
3. 点击"导出排产台账"
4. 下载并打开Excel文件

**预期结果：**
- 8列：批次号、300、400、500、600、7055、8055、合计
- **7055列显示FR-7055系列机型**
- **8055列显示FR-8055系列机型** ✓ 修复
- **合计列显示总数量** ✓ 修复
- 没有"预计入库时间"列

## 测试文件

- `simulate_excel_generation.py` - 模拟Excel生成逻辑（已验证通过）
- `simulated_export.xlsx` - 模拟生成的Excel文件（可查看效果）

## 总结

✓ **根本问题已修复** - 列索引计算错误  
✓ **8055列现在显示正确的机型数据**  
✓ **合计列现在显示正确的总数量**  
✓ **预计入库时间列已完全移除**  
✓ **模拟测试通过**  

**请重新导出Excel文件验证实际效果！**
