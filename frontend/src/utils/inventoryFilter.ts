export type InventoryFilterParams = {
  selectedModels: string[]
  statusFilter: string
  searchQuery: string
  highOnly: boolean
}

export type IndexedInventoryRow = {
  row: any
  searchText: string
  model: string
  status: string
  highHint: string
}

export const buildInventoryIndex = (rows: any[]): IndexedInventoryRow[] => {
  return rows.map((row) => {
    const model = String(row['机型'] || '')
    const status = String(row['状态'] || '')
    const highHint = `${model}|${String(row['机台备注/配置'] || '')}|${String(row['订单备注'] || '')}`
    const searchText = `${String(row['流水号'] || '')}|${model}|${String(row['批次号'] || '')}|${String(row['客户'] || '')}`.toLowerCase()
    return { row, searchText, model, status, highHint }
  })
}

export const filterInventoryRows = (indexedRows: IndexedInventoryRow[], params: InventoryFilterParams) => {
  const q = params.searchQuery.trim().toLowerCase()
  const pickedModels = params.selectedModels
  const hasModels = pickedModels.length > 0
  const statusPrefix = params.statusFilter

  return indexedRows
    .filter((x) => x.status.startsWith('库存中') || x.status === '待入库')
    .filter((x) => !hasModels || pickedModels.includes(x.model))
    .filter((x) => !statusPrefix || x.status.startsWith(statusPrefix))
    .filter((x) => !q || x.searchText.includes(q))
    .filter((x) => !params.highOnly || x.highHint.includes('加高'))
    .map((x) => x.row)
}
