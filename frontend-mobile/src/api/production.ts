import request from './index'

export type ProductionLine = Record<string, any>
export type ProductionBatch = Record<string, any>

const normalizeList = <T = any>(res: any, keys: string[]): T[] => {
  if (Array.isArray(res)) return res as T[]
  for (const key of keys) {
    if (Array.isArray(res?.[key])) return res[key] as T[]
  }
  if (Array.isArray(res?.data)) return res.data as T[]
  return []
}

export const productionApi = {
  async getProductionLines() {
    const res = await request.get<any, any>('/sandbox/production-lines')
    return normalizeList<ProductionLine>(res, ['lines', 'production_lines'])
  },
  async getBatches(params?: Record<string, any>) {
    const res = await request.get<any, any>('/sandbox/batches', { params })
    return normalizeList<ProductionBatch>(res, ['batches'])
  },
  assignLine(lineId: string, batchId: string) {
    return request.post(`/sandbox/production-lines/${lineId}/assign`, { batch_id: batchId })
  },
  manualComplete(lineId: string) {
    return request.post(`/sandbox/production-lines/${lineId}/manual-complete`)
  },
  importBatchToFinishedGoods(batchId: string) {
    return request.post(`/sandbox/batches/${batchId}/import-to-finished-goods`)
  },
}
