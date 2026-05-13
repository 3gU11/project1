import { buildInventoryIndex, filterInventoryRows } from './inventoryFilter'
import { compareModels, isModelInDictionary } from './modelOrder'

export type ModelInventorySummary = {
  机型: string
  库存中: number
  待入库: number
  已绑定: number
  全部: number
}

export type ModelInventoryRatio = {
  model: string
  count: number
  percent: number
  inStock: number
  pending: number
  bound: number
}

export const getActiveInventoryRows = (rows: any[]) => {
  return filterInventoryRows(buildInventoryIndex(rows), {
    selectedModels: [],
    statusFilter: '',
    searchQuery: '',
    highOnly: false,
  })
}

export const buildModelInventorySummary = (rows: any[]): ModelInventorySummary[] => {
  const map = new Map<string, ModelInventorySummary>()
  for (const row of rows) {
    const model = String(row['机型'] || '未知')
    if (!isModelInDictionary(model)) continue
    if (!map.has(model)) map.set(model, { 机型: model, 库存中: 0, 待入库: 0, 已绑定: 0, 全部: 0 })
    const hit = map.get(model)!
    const status = String(row['状态'] || '')
    if (status.startsWith('库存中')) hit.库存中 += 1
    if (status === '待入库') hit.待入库 += 1
    if (status === '已绑定') hit.已绑定 += 1
    hit.全部 += 1
  }
  return Array.from(map.values())
}

export const sortModelInventorySummary = (rows: ModelInventorySummary[]) => {
  return [...rows].sort((a, b) => compareModels(a.机型, b.机型))
}

export const sortModelInventorySummaryByCount = (rows: ModelInventorySummary[]) => {
  return [...rows].sort((a, b) => (b.全部 - a.全部) || compareModels(a.机型, b.机型))
}

export const buildModelInventoryRatios = (rows: any[]): ModelInventoryRatio[] => {
  const summary = sortModelInventorySummaryByCount(buildModelInventorySummary(rows))
  const total = summary.reduce((sum, row) => sum + row.全部, 0)
  return summary.map((row) => ({
    model: row.机型,
    count: row.全部,
    inStock: row.库存中,
    pending: row.待入库,
    bound: row.已绑定,
    percent: total > 0 ? (row.全部 / total) * 100 : 0,
  }))
}
