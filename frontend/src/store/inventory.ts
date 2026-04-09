import { defineStore } from 'pinia'
import { ref } from 'vue'
import { apiGet, getApiErrorMessage } from '../utils/request'
import { useCacheStore } from './cache'

type ListResponse<T = any> = { data: T[] }

export const useInventoryStore = defineStore('inventory', () => {
  const list = ref<any[]>([])
  const loading = ref(false)
  const error = ref('')
  const cacheStore = useCacheStore()
  const CACHE_KEY = 'inventory:list'

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
      const res = await apiGet<ListResponse>('/inventory/')
      list.value = res.data || []
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
