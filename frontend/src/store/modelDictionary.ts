import { defineStore } from 'pinia'
import { ref } from 'vue'
import { apiGet, apiPost } from '../utils/request'
import { setModelOrderList } from '../utils/modelOrder'

export type ModelDictionaryRow = {
  id?: number
  model_name: string
  sort_order: number
  enabled: boolean
  remark?: string
  updated_at?: string
  _rowKey?: string
}

export type ModelDictionaryDeleteMetrics = {
  requestMs: number
  reloadMs: number
  totalMs: number
}

const createRowKey = (prefix = 'tmp') => `${prefix}-${Date.now()}-${Math.random().toString(36).slice(2, 10)}`

const normalizeRows = (rows: any[]): ModelDictionaryRow[] => {
  return (rows || []).map((r: any, idx: number) => ({
    id: Number.isFinite(Number(r?.id)) ? Number(r.id) : undefined,
    model_name: String(r?.model_name || '').trim(),
    sort_order: Number.isFinite(Number(r?.sort_order)) ? Number(r.sort_order) : idx,
    enabled: Boolean(r?.enabled ?? true),
    remark: String(r?.remark || ''),
    updated_at: String(r?.updated_at || ''),
    _rowKey: Number.isFinite(Number(r?.id)) ? `db-${Number(r.id)}` : createRowKey(),
  }))
}

export const useModelDictionaryStore = defineStore('modelDictionary', () => {
  const rows = ref<ModelDictionaryRow[]>([])
  const loaded = ref(false)

  const applyModelOrder = () => {
    const list = rows.value
      .filter((r) => r.enabled && r.model_name)
      .sort((a, b) => a.sort_order - b.sort_order)
      .map((r) => r.model_name)
    setModelOrderList(list)
  }

  const loadDictionary = async () => {
    const t = Date.now()
    const res = await apiGet<{ data?: any[] }>(`/model-dictionary/?t=${t}`)
    rows.value = normalizeRows(res?.data || [])
    applyModelOrder()
    loaded.value = true
    return rows.value
  }

  const ensureLoaded = async () => {
    if (loaded.value) return rows.value
    return loadDictionary()
  }

  const saveDictionary = async (nextRows: ModelDictionaryRow[]) => {
    const payload = (nextRows || []).map((r, idx) => ({
      model_name: String(r.model_name || '').trim(),
      sort_order: Number.isFinite(Number(r.sort_order)) ? Number(r.sort_order) : idx,
      enabled: Boolean(r.enabled),
      remark: String(r.remark || ''),
    }))
    await apiPost('/model-dictionary/save', { rows: payload })
    return loadDictionary()
  }

  const deleteOne = async (row: ModelDictionaryRow) => {
    const startedAt = performance.now()
    await apiPost('/model-dictionary/delete', {
      id: Number.isFinite(Number(row?.id)) ? Number(row.id) : undefined,
      model_name: String(row?.model_name || '').trim(),
    })
    const afterDeleteAt = performance.now()
    await loadDictionary()
    const afterReloadAt = performance.now()
    return {
      requestMs: Number((afterDeleteAt - startedAt).toFixed(1)),
      reloadMs: Number((afterReloadAt - afterDeleteAt).toFixed(1)),
      totalMs: Number((afterReloadAt - startedAt).toFixed(1)),
    } satisfies ModelDictionaryDeleteMetrics
  }

  return { rows, loaded, loadDictionary, ensureLoaded, saveDictionary, deleteOne, applyModelOrder }
})
