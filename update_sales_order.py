import sys

try:
    with open('d:/CURSORpj/V7STD1.0/frontend/src/views/SalesOrder.vue', 'r', encoding='utf-8') as f:
        content = f.read()

    # 1. createManualOrder
    target1 = "  const modelTokens = validRows.map((r) => `${r.model.trim()}${r.high ? '(加高)' : ''}x${r.qty}`)\n  const totalQty = validRows.reduce((sum, r) => sum + Number(r.qty || 0), 0)\n  const rowNotes = validRows.filter((r) => r.rowNote.trim()).map((r) => `${r.model}: ${r.rowNote.trim()}`)"
    replacement1 = "  const modelTokens = validRows.map((r) => `${r.model.trim()}x${r.qty}`)\n  const totalQty = validRows.reduce((sum, r) => sum + Number(r.qty || 0), 0)\n  const rowNotes = validRows\n    .filter((r) => r.rowNote.trim() || r.high)\n    .map((r) => `${r.model}: ${[r.high ? '加高' : '', r.rowNote.trim()].filter(Boolean).join(' | ')}`)"
    if target1 not in content:
        print("Warning: target1 not found!")
    content = content.replace(target1, replacement1)

    # 2. createOrderFromPlanned (push)
    target2 = "modelTokens.push(`${model}${r.high ? '(加高)' : ''}x${qty}`)"
    replacement2 = "modelTokens.push(`${model}x${qty}`)"
    if target2 not in content:
        print("Warning: target2 not found!")
    content = content.replace(target2, replacement2)

    # 3. createOrderFromPlanned (rowNotes)
    target3 = "  const rowNotes = mergeRows.value\n    .filter((r) => r.rowNote.trim())\n    .map((r) => `[${r.sourceContract}] ${r.rowNote.trim()}`)"
    replacement3 = "  const rowNotes = mergeRows.value\n    .filter((r) => r.rowNote.trim() || r.high)\n    .map((r) => `[${r.sourceContract}] ${r.model}: ${[r.high ? '加高' : '', r.rowNote.trim()].filter(Boolean).join(' | ')}`)"
    if target3 not in content:
        print("Warning: target3 not found!")
    content = content.replace(target3, replacement3)

    # 4. mergeRows.value computation (watch selectedImportContractIds)
    target4 = """  mergeRows.value = rows.map((r) => {
    const rawModel = String(r['机型'] || '').trim()
    const high = rawModel.includes('(加高)')
    const model = rawModel.replace('(加高)', '').trim()
    return {
      sourceContract: String(r['合同号'] || ''),
      model,
      high,
      qty: Math.max(1, Number(r['排产数量'] || 1) || 1),
      rowNote: String(r['备注'] || ''),
    }
  })"""
    replacement4 = """  mergeRows.value = rows.map((r) => {
    const rawModel = String(r['机型'] || '').trim()
    const note = String(r['备注'] || '').trim()
    // 兼容旧数据模型自带(加高)，以及新数据订单备注中包含"加高"
    const high = rawModel.includes('(加高)') || note.includes('加高')
    const model = rawModel.replace('(加高)', '').trim()
    
    // 从原始备注中剔除"加高"，避免重复显示
    const cleanNote = note.split('|').map(s => s.trim()).filter(s => s && s !== '加高').join(' | ')
    
    return {
      sourceContract: String(r['合同号'] || ''),
      model,
      high,
      qty: Math.max(1, Number(r['排产数量'] || 1) || 1),
      rowNote: cleanNote,
    }
  })"""
    if target4 not in content:
        print("Warning: target4 not found!")
    content = content.replace(target4, replacement4)

    # 5. openEdit
    target5 = """  for (const token of rawModels) {
    const m = token.match(/^(.*?)(?:\\s*[x×:：]\\s*)(\\d+)$/i)
    const modelRaw = m ? m[1].trim() : token
    const qty = m ? Number(m[2]) : 1
    const high = modelRaw.includes('(加高)')
    parsedRows.push({
      model: modelRaw.replace('(加高)', '').trim(),
      qty: qty > 0 ? qty : 1,
      high,
      rowNote: '',
    })
  }"""
    replacement5 = """  const orderNote = String(row['备注'] || '')
  for (const token of rawModels) {
    const m = token.match(/^(.*?)(?:\\s*[x×:：]\\s*)(\\d+)$/i)
    const modelRaw = m ? m[1].trim() : token
    const qty = m ? Number(m[2]) : 1
    // 兼容旧数据模型自带(加高)，以及新数据订单备注中包含"加高"
    const high = modelRaw.includes('(加高)') || orderNote.includes('加高')
    
    parsedRows.push({
      model: modelRaw.replace('(加高)', '').trim(),
      qty: qty > 0 ? qty : 1,
      high,
      rowNote: '', // 备注作为整体显示，行备注留空供用户重新追加
    })
  }"""
    if target5 not in content:
        print("Warning: target5 not found!")
    content = content.replace(target5, replacement5)

    # 6. saveEdit
    target6 = "  const modelTokens = validRows.map((r) => `${r.model.trim()}${r.high ? '(加高)' : ''}x${r.qty}`)\n  const totalQty = validRows.reduce((sum, r) => sum + Number(r.qty || 0), 0)\n  const lineNotes = validRows.filter((r) => r.rowNote.trim()).map((r) => `${r.model}: ${r.rowNote.trim()}`)"
    replacement6 = "  const modelTokens = validRows.map((r) => `${r.model.trim()}x${r.qty}`)\n  const totalQty = validRows.reduce((sum, r) => sum + Number(r.qty || 0), 0)\n  const lineNotes = validRows\n    .filter((r) => r.rowNote.trim() || r.high)\n    .map((r) => `${r.model}: ${[r.high ? '加高' : '', r.rowNote.trim()].filter(Boolean).join(' | ')}`)"
    if target6 not in content:
        print("Warning: target6 not found!")
    content = content.replace(target6, replacement6)

    with open('d:/CURSORpj/V7STD1.0/frontend/src/views/SalesOrder.vue', 'w', encoding='utf-8') as f:
        f.write(content)

    print("Success")
except Exception as e:
    import traceback
    traceback.print_exc()
