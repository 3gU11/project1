import { getInventoryLifecycleStatus, isMachineBound, isPendingInbound, isProductionBound } from './inventoryState'
import { hasHighHint } from './heightened'
import { normalizeModelName } from './modelOrder'

export type InventoryFilterParams = {
  selectedModels: string[]
  statusFilter: string
  searchQuery: string
  highOnly: boolean
  relationFilter?: 'bound' | ''
  includeProductionBound?: boolean
}

export type IndexedInventoryRow = {
  row: any
  searchText: string
  model: string
  status: string
  highHint: string
  bound: boolean
}

export const buildInventoryIndex = (rows: any[]): IndexedInventoryRow[] => {
  return rows.map((row) => {
    const rawModel = String(row['机型'] || '')
    // 筛选/统计按机型字典的基础机型匹配，加高只作为规格属性，不再参与机型拆分。
    const model = normalizeModelName(rawModel)
    const status = getInventoryLifecycleStatus(row)
    const highHint = hasHighHint(rawModel, row['合同备注']) ? '加高' : ''
    const searchText = `${String(row['流水号'] || '')}|${rawModel}|${String(row['批次号'] || '')}|${String(row['客户'] || '')}`.toLowerCase()
    return {
      row,
      searchText,
      model,
      status,
      highHint,
      bound: isMachineBound(row),
    }
  })
}

export const filterInventoryRows = (indexedRows: IndexedInventoryRow[], params: InventoryFilterParams) => {
  const q = params.searchQuery.trim().toLowerCase()
  const pickedModels = params.selectedModels
  const hasModels = pickedModels.length > 0
  const statusPrefix = params.statusFilter

  return indexedRows
    .filter((x) => x.status.startsWith('库存中') || isPendingInbound(x.row) || (params.includeProductionBound && isProductionBound(x.row)))
    .filter((x) => !hasModels || pickedModels.includes(x.model))
    .filter((x) => !statusPrefix || x.status.startsWith(statusPrefix))
    .filter((x) => !q || x.searchText.includes(q))
    .filter((x) => !params.highOnly || x.highHint.includes('加高'))
    .filter((x) => params.relationFilter !== 'bound' || x.bound)
    .map((x) => x.row)
}
