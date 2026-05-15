const fs = require('fs');

try {
  let content = fs.readFileSync('d:/CURSORpj/V7STD1.0/frontend/src/views/SalesOrder.vue', 'utf-8');

  // 1. createManualOrder
  content = content.replace(
    /const modelTokens = validRows\.map\(\(r\) => `\$\{r\.model\.trim\(\)\}\$\{r\.high \? '\(加高\)' : ''\}x\$\{r\.qty\}`\)\r?\n\s+const totalQty = validRows\.reduce\(\(sum, r\) => sum \+ Number\(r\.qty \|\| 0\), 0\)\r?\n\s+const rowNotes = validRows\.filter\(\(r\) => r\.rowNote\.trim\(\)\)\.map\(\(r\) => `\$\{r\.model\}: \$\{r\.rowNote\.trim\(\)\}`\)/g,
    `const modelTokens = validRows.map((r) => \`\${r.model.trim()}x\${r.qty}\`)
  const totalQty = validRows.reduce((sum, r) => sum + Number(r.qty || 0), 0)
  const rowNotes = validRows
    .filter((r) => r.rowNote.trim() || r.high)
    .map((r) => \`\${r.model}: \${[r.high ? '加高' : '', r.rowNote.trim()].filter(Boolean).join(' | ')}\`)`
  );

  // 2. createOrderFromPlanned (push)
  content = content.replace(
    /modelTokens\.push\(`\$\{model\}\$\{r\.high \? '\(加高\)' : ''\}x\$\{qty\}`\)/g,
    'modelTokens.push(`\\${model}x\\${qty}`)'
  );

  // 3. createOrderFromPlanned (rowNotes)
  content = content.replace(
    /const rowNotes = mergeRows\.value\r?\n\s+\.filter\(\(r\) => r\.rowNote\.trim\(\)\)\r?\n\s+\.map\(\(r\) => `\[\$\{r\.sourceContract\}\] \$\{r\.rowNote\.trim\(\)\}`\)/g,
    `const rowNotes = mergeRows.value
    .filter((r) => r.rowNote.trim() || r.high)
    .map((r) => \`[\${r.sourceContract}] \${r.model}: \${[r.high ? '加高' : '', r.rowNote.trim()].filter(Boolean).join(' | ')}\`)`
  );

  // 4. mergeRows.value computation
  content = content.replace(
    /const rawModel = String\(r\['机型'\] \|\| ''\)\.trim\(\)\r?\n\s+const high = rawModel\.includes\('\(加高\)'\)\r?\n\s+const model = rawModel\.replace\('\(加高\)', ''\)\.trim\(\)\r?\n\s+return \{\r?\n\s+sourceContract: String\(r\['合同号'\] \|\| ''\),\r?\n\s+model,\r?\n\s+high,\r?\n\s+qty: Math\.max\(1, Number\(r\['排产数量'\] \|\| 1\) \|\| 1\),\r?\n\s+rowNote: String\(r\['备注'\] \|\| ''\),\r?\n\s+\}/g,
    `const rawModel = String(r['机型'] || '').trim()
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
    }`
  );

  // 5. openEdit
  content = content.replace(
    /const m = token\.match\(\/\^\(\.\*\?\)\(\?:\\s\*\[x×:：\]\\s\*\)\(\\d\+\)\$\/i\)\r?\n\s+const modelRaw = m \? m\[1\]\.trim\(\) : token\r?\n\s+const qty = m \? Number\(m\[2\]\) : 1\r?\n\s+const high = modelRaw\.includes\('\(加高\)'\)\r?\n\s+parsedRows\.push\(\{\r?\n\s+model: modelRaw\.replace\('\(加高\)', ''\)\.trim\(\),\r?\n\s+qty: qty > 0 \? qty : 1,\r?\n\s+high,\r?\n\s+rowNote: '',\r?\n\s+\}\)/g,
    `const m = token.match(/^(.*?)(?:\\s*[x×:：]\\s*)(\\d+)$/i)
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
    })`
  );

  // 6. saveEdit
  content = content.replace(
    /const modelTokens = validRows\.map\(\(r\) => `\$\{r\.model\.trim\(\)\}\$\{r\.high \? '\(加高\)' : ''\}x\$\{r\.qty\}`\)\r?\n\s+const totalQty = validRows\.reduce\(\(sum, r\) => sum \+ Number\(r\.qty \|\| 0\), 0\)\r?\n\s+const lineNotes = validRows\.filter\(\(r\) => r\.rowNote\.trim\(\)\)\.map\(\(r\) => `\$\{r\.model\}: \$\{r\.rowNote\.trim\(\)\}`\)/g,
    `const modelTokens = validRows.map((r) => \`\${r.model.trim()}x\${r.qty}\`)
  const totalQty = validRows.reduce((sum, r) => sum + Number(r.qty || 0), 0)
  const lineNotes = validRows
    .filter((r) => r.rowNote.trim() || r.high)
    .map((r) => \`\${r.model}: \${[r.high ? '加高' : '', r.rowNote.trim()].filter(Boolean).join(' | ')}\`)`
  );

  fs.writeFileSync('d:/CURSORpj/V7STD1.0/frontend/src/views/SalesOrder.vue', content, 'utf-8');
  console.log("Replacement successful!");
} catch (e) {
  console.error("Error:", e);
}
