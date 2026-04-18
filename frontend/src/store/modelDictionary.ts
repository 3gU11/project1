import { defineStore } from 'pinia'
import { ref } from 'vue'
import { apiGet, apiPost } from '../utils/request'
import { setModelOrderList } from '../utils/modelOrder'

export interface ModelDictionaryRow {
  id?: number
  model_name: string
  sort_order: number
  enabled: boolean
  remark: string
  updated_at?: string
  _tempId?: string
}

const normalizeRows = (rows: any[]): ModelDictionaryRow[] => {
  return (rows || []).map((r: any, idx: number) => ({
    id: Number.isFinite(Number(r?.id)) ? Number(r.id) : undefined,
    model_name: String(r?.model_name || '').trim(),
    sort_order: idx,
    enabled: Boolean(r?.enabled ?? true),
    remark: String(r?.remark || ''),
    updated_at: String(r?.updated_at || ''),
  }))
}

export const useModelDictionaryStore = defineStore('modelDictionary', () => {
  const rows = ref<ModelDictionaryRow[]>([])

  const applyModelOrder = () => {
    const list = rows.value
      .filter((r) => r.enabled && r.model_name)
      .sort((a, b) => a.sort_order - b.sort_order)
      .map((r) => r.model_name)
    setModelOrderList(list)
  }

  const loadDictionary = async () => {
    const res = await apiGet<{ data?: ModelDictionaryRow[] }>('/model-dictionary/')
    rows.value = normalizeRows(res?.data || [])
    applyModelOrder()
    return rows.value
  }

  const ensureLoaded = async () => {
    if (rows.value.length > 0) return rows.value
    return loadDictionary()
  }

  const saveDictionary = async (nextRows: ModelDictionaryRow[]) => {
    const payload = (nextRows || []).map((r, idx) => ({
      id: Number.isFinite(Number(r.id)) ? Number(r.id) : undefined,
      model_name: String(r.model_name || '').trim(),
      sort_order: idx,
      enabled: Boolean(r.enabled),
      remark: String(r.remark || ''),
    }))
    await apiPost('/model-dictionary/save', { rows: payload })
    return loadDictionary()
  }

  return { rows, loadDictionary, ensureLoaded, saveDictionary, applyModelOrder }
})
