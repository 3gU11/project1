import { defineStore } from 'pinia'
import { ref } from 'vue'
import { apiGet, getApiErrorMessage } from '../utils/request'
import { useCacheStore } from './cache'

type ListResponse<T = any> = { data: T[]; total?: number; skip?: number; limit?: number }

export const useInventoryStore = defineStore('inventory', () => {
  const list = ref<any[]>([])
  const loading = ref(false)
  const error = ref('')
  const cacheStore = useCacheStore()
  const CACHE_KEY = 'inventory:list'
  const PAGE_SIZE = 1000

  const fetchAllInventoryRows = async () => {
    let skip = 0
    let total = Number.POSITIVE_INFINITY
    const rows: any[] = []
    while (skip < total) {
      const res = await apiGet<ListResponse>(`/inventory/?skip=${skip}&limit=${PAGE_SIZE}`)
      const chunk = res.data || []
      const safeTotal = Number.isFinite(Number(res.total)) ? Number(res.total) : chunk.length
      total = safeTotal
      rows.push(...chunk)
      if (chunk.length === 0) break
      skip += chunk.length
      if (chunk.length < PAGE_SIZE) break
    }
    return rows
  }

  const fetchInventory = async (force = false) => {
    loading.value = true
    error.value = ''
    try {
      if (!force) {
        const cached = cacheStore.get<any[]>(CACHE_KEY)
        if (cached) {
          list.value = cached
          return list.value
        }
      }
      list.value = await fetchAllInventoryRows()
      cacheStore.set(CACHE_KEY, list.value, 12_000)
      return list.value
    } catch (err: any) {
      error.value = getApiErrorMessage(err) || '读取库存失败'
      throw err
    } finally {
      loading.value = false
    }
  }

  return { list, loading, error, fetchInventory }
})
