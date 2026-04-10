import { defineStore } from 'pinia'
import { ref } from 'vue'
import { apiGetAll, getApiErrorMessage } from '../utils/request'
import { useCacheStore } from './cache'

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
      planningContracts.value = await apiGetAll<any>('/planning/')
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
