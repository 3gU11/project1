import re

try:
    with open('d:/CURSORpj/V7STD1.0/frontend/src/views/SalesOrder.vue', 'r', encoding='utf-8') as f:
        content = f.read()

    # 1. createManualOrder
    content = re.sub(
        r'const modelTokens = validRows\.map\(\(r\) => `\$\{r\.model\.trim\(\)\}\$\{r\.high \? \'\(\u52a0\u9ad8\)\' : \'\'\}x\$\{r\.qty\}`\)\s+const totalQty = validRows\.reduce\(\(sum, r\) => sum \+ Number\(\s*r\.qty \|\| 0\s*\), 0\)\s+const rowNotes = validRows\.filter\(\(r\) => r\.rowNote\.trim\(\)\)\.map\(\(r\) => `\$\{r\.model\}: \$\{r\.rowNote\.trim\(\)\}`\)',
        '''const modelTokens = validRows.map((r) => `${r.model.trim()}x${r.qty}`)
  const totalQty = validRows.reduce((sum, r) => sum + Number(r.qty || 0), 0)
  const rowNotes = validRows
    .filter((r) => r.rowNote.trim() || r.high)
    .map((r) => `${r.model}: ${[r.high ? '加高' : '', r.rowNote.trim()].filter(Boolean).join(' | ')}`)''',
        content
    )

    # 2. createOrderFromPlanned (push)
    content = re.sub(
        r'modelTokens\.push\(`\$\{model\}\$\{r\.high \? \'\(\u52a0\u9ad8\)\' : \'\'\}x\$\{qty\}`\)',
        'modelTokens.push(`${model}x${qty}`)',
        content
    )

    # 3. createOrderFromPlanned (rowNotes)
    content = re.sub(
        r'const rowNotes = mergeRows\.value\s+\.filter\(\(r\) => r\.rowNote\.trim\(\)\)\s+\.map\(\(r\) => `\[\$\{r\.sourceContract\}\] \$\{r\.rowNote\.trim\(\)\}`\)',
        '''const rowNotes = mergeRows.value
    .filter((r) => r.rowNote.trim() || r.high)
    .map((r) => `[${r.sourceContract}] ${r.model}: ${[r.high ? '加高' : '', r.rowNote.trim()].filter(Boolean).join(' | ')}`)''',
        content
    )

    # 4. mergeRows.value computation
    content = re.sub(
        r'const rawModel = String\(r\[\'机型\'\] \|\| \'\'\)\.trim\(\)\s+const high = rawModel\.includes\(\'\(\u52a0\u9ad8\)\'\)\s+const model = rawModel\.replace\(\'\(\u52a0\u9ad8\)\', \'\'\)\.trim\(\)\s+return \{\s+sourceContract: String\(r\[\'合同号\'\] \|\| \'\'\),\s+model,\s+high,\s+qty: Math\.max\(1, Number\(r\[\'排产数量\'\] \|\| 1\) \|\| 1\),\s+rowNote: String\(r\[\'备注\'\] \|\| \'\'\),\s+\}',
        '''const rawModel = String(r['机型'] || '').trim()
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
    }''',
        content
    )

    # 5. openEdit
    content = re.sub(
        r'const m = token\.match\(\/\^\(\.\*\?\)\(\?:\\\\s\*\[x×:：\]\\\\s\*\)\(\\\\d\+\)\$\/i\)\s+const modelRaw = m \? m\[1\]\.trim\(\) : token\s+const qty = m \? Number\(m\[2\]\) : 1\s+const high = modelRaw\.includes\(\'\(\u52a0\u9ad8\)\'\)\s+parsedRows\.push\(\{\s+model: modelRaw\.replace\(\'\(\u52a0\u9ad8\)\', \'\'\)\.trim\(\),\s+qty: qty > 0 \? qty : 1,\s+high,\s+rowNote: \'\',\s+\}\)',
        '''const m = token.match(/^(.*?)(?:\\s*[x×:：]\\s*)(\\d+)$/i)
    const modelRaw = m ? m[1].trim() : token
    const qty = m ? Number(m[2]) : 1
    const orderNote = String(row['备注'] || '')
    // 兼容旧数据模型自带(加高)，以及新数据订单备注中包含"加高"
    const high = modelRaw.includes('(加高)') || orderNote.includes('加高')
    
    parsedRows.push({
      model: modelRaw.replace('(加高)', '').trim(),
      qty: qty > 0 ? qty : 1,
      high,
      rowNote: '', // 备注作为整体显示，行备注留空供用户重新追加
    })''',
        content
    )

    # 6. saveEdit
    content = re.sub(
        r'const modelTokens = validRows\.map\(\(r\) => `\$\{r\.model\.trim\(\)\}\$\{r\.high \? \'\(\u52a0\u9ad8\)\' : \'\'\}x\$\{r\.qty\}`\)\s+const totalQty = validRows\.reduce\(\(sum, r\) => sum \+ Number\(\s*r\.qty \|\| 0\s*\), 0\)\s+const lineNotes = validRows\.filter\(\(r\) => r\.rowNote\.trim\(\)\)\.map\(\(r\) => `\$\{r\.model\}: \$\{r\.rowNote\.trim\(\)\}`\)',
        '''const modelTokens = validRows.map((r) => `${r.model.trim()}x${r.qty}`)
  const totalQty = validRows.reduce((sum, r) => sum + Number(r.qty || 0), 0)
  const lineNotes = validRows
    .filter((r) => r.rowNote.trim() || r.high)
    .map((r) => `${r.model}: ${[r.high ? '加高' : '', r.rowNote.trim()].filter(Boolean).join(' | ')}`)''',
        content
    )

    with open('d:/CURSORpj/V7STD1.0/frontend/src/views/SalesOrder.vue', 'w', encoding='utf-8') as f:
        f.write(content)
    print("Regex replacement completed successfully.")
except Exception as e:
    import traceback
    traceback.print_exc()
