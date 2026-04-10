# BossPlanning 支持部分规划保存修改方案 (For Claude Code)

此方案用于解决生产统筹 (BossPlanning) 页面中“必须全部机型分配完毕才能保存”的拦截问题，修改后将允许保存**部分分配的规划进度**，并在全部机型分配完成时才将状态变更为“已规划”。

请阅读并执行以下代码替换。

---

## 1. 前端修改: 解除保存拦截并动态传递状态

**目标文件**：`frontend/src/views/BossPlanning.vue`

定位到 `savePlanning` 方法（约在 1290 行附近）。移除当分配不足时的 `return` 拦截，改为使用 `isFullyAllocated` 变量标记，并动态向后端传递 `mark_to_planned`。

**修改方案：将原 `savePlanning` 替换为以下代码：**

```javascript
const savePlanning = async () => {
  if (!selectedId.value) return
  
  let isFullyAllocated = true

  for (const row of selectedContractRows.value) {
    const key = String(row._idx)
    const draft = planDraft[key] || { spot: 0, batches: {} }
    let allocated = toInt(draft.spot)
    for (const qty of Object.values(draft.batches || {})) {
      allocated += toInt(qty)
    }
    const need = toInt(row['排产数量'])
    
    if (allocated > need) {
      ElMessage.error(`机型 ${row['机型']} 分配超量：${allocated}/${need}`)
      return
    }
    // 如果任何一个机型的分配量小于需求量，标记为未全部分配，但不阻断保存流程
    if (allocated < need) {
      isFullyAllocated = false
    }
  }

  const rows = selectedContractRows.value.map((row: any) => {
    const key = String(row._idx)
    const draft = planDraft[key] || { spot: 0, batches: {} }
    const allocation: Record<string, number> = {}
    if (toInt(draft.spot) > 0) allocation['现货(Spot)'] = toInt(draft.spot)
    for (const [k, v] of Object.entries(draft.batches || {})) {
      const qty = toInt(v)
      if (qty > 0) allocation[k] = qty
    }
    return {
      row_index: Number(row._idx),
      allocation
    }
  })

  await submitWithLock(savingPlan, async () => {
    await apiPost(`/planning/contract/${encodeURIComponent(selectedId.value)}/save-plan`, {
      rows,
      mark_to_planned: isFullyAllocated // 动态传递：只有全部分配才为 true
    })
    await fetchData(true)
    initPlanDraft()
  }, { 
    // 根据是否全部分配动态提示
    successMessage: isFullyAllocated ? '规划已保存' : '规划进度已保存 (部分分配)', 
    errorMessage: '保存规划失败' 
  })
}
```

---

## 2. 后端修改: 支持状态自动回退与条件流转

**目标文件**：`api/routes/planning.py`

定位到 `save_contract_plan` 路由方法（约 631 行附近）。目前的逻辑是只要收到前端传来的 `mark_to_planned: true` 就会强行设为“已规划”。我们需要增加 `else` 分支逻辑：如果 `mark_to_planned` 为 `False`，并且该记录原状态为“已规划”，则将其自动降级回“待规划”。

**修改方案：找到更新状态的相关逻辑段，并替换为如下代码：**

```python
            # ... 前面构建 df_plan.loc[row_mask, "指定批次/来源"] = ... 保持不变
            
            # 状态更新逻辑替换为以下部分：
            if payload.mark_to_planned:
                wait_mask = row_mask & (df_plan["状态"].astype(str) == "待规划")
                if wait_mask.any():
                    df_plan.loc[wait_mask, "状态"] = "已规划"
            else:
                # 核心改动：如果未全部分配（mark_to_planned 为 False），
                # 且数据库中该行状态已是“已规划”，则将其回退为“待规划”
                revert_mask = row_mask & (df_plan["状态"].astype(str) == "已规划")
                if revert_mask.any():
                    df_plan.loc[revert_mask, "状态"] = "待规划"
```

> **注意：** 
> 1. 如果你在前一轮已经让 Claude Code 将后端的 `save_contract_plan` 整体重构为了纯 SQL `UPDATE`（即不使用 DataFrame 的版本），则只需在对应的 SQL `UPDATE` 语句中加入相同的逻辑判断即可（即：当 `payload.mark_to_planned` 为 `False` 时，将 `状态` 字段 `SET` 回 `'待规划'`）。
> 2. 请以当前代码库中实际采用的 `save_contract_plan` 实现版本为准应用逻辑。

---

## 3. 验证方式
1. 打开“生产统筹”菜单，选择一个“待规划”状态的合同。
2. 对其中一台或部分机型进行**不足额的分配**。
3. 点击“保存排产”，此时不应再弹出“规划未完成”的红字拦截，而是应该提示“规划进度已保存 (部分分配)”。
4. 刷新页面，之前部分分配的数量应当正确回显，且合同/机型状态仍为“待规划”。
5. 继续补齐剩余未分配的数量，再次点击保存，此时应提示“规划已保存”，且状态自动变为“已规划”。