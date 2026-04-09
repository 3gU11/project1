import { defineStore } from 'pinia'
import { ref } from 'vue'
import { apiGet, getApiErrorMessage } from '../utils/request'
import { useCacheStore } from './cache'

type ListResponse<T = any> = { data: T[] }

export const useContractsStore = defineStore('contracts', () => {
  const planningContracts = ref<any[]>([])
  const loading = ref(false)
  const error = ref('')
  const cacheStore = useCacheStore()
  const CACHE_KEY = 'contracts:planning'

  const fetchPlanningContracts = async (force = false) => {
    loading.value = true
    error.value = ''
    try {
      if (!force) {
        const cached = cacheStore.get<any[]>(CACHE_KEY)
        if (cached) {
          planningContracts.value = cached
          return planningContracts.value
        }
      }
      const res = await apiGet<ListResponse>('/planning/')
      planningContracts.value = res.data || []
      cacheStore.set(CACHE_KEY, planningContracts.value, 10_000)
      return planningContracts.value
    } catch (err: any) {
      error.value = getApiErrorMessage(err) || '读取合同数据失败'
      throw err
    } finally {
      loading.value = false
    }
  }

  return { planningContracts, loading, error, fetchPlanningContracts }
})
