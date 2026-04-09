import { defineStore } from 'pinia'
import { ref } from 'vue'
import { apiGet, getApiErrorMessage } from '../utils/request'
import { useCacheStore } from './cache'

type ListResponse<T = any> = { data: T[] }

export const usePlanningStore = defineStore('planning', () => {
  const planList = ref<any[]>([])
  const orderList = ref<any[]>([])
  const inventoryList = ref<any[]>([])
  const loading = ref(false)
  const error = ref('')
  const cacheStore = useCacheStore()

  const fetchPlanningDashboard = async (force = false) => {
    loading.value = true
    error.value = ''
    try {
      if (!force) {
        const planCached = cacheStore.get<any[]>('planning:list')
        const orderCached = cacheStore.get<any[]>('planning:orders')
        const invCached = cacheStore.get<any[]>('planning:inventory')
        if (planCached && orderCached && invCached) {
          planList.value = planCached
          orderList.value = orderCached
          inventoryList.value = invCached
          return { planList: planList.value, orderList: orderList.value, inventoryList: inventoryList.value }
        }
      }
      const [planRes, orderRes, invRes] = await Promise.all([
        apiGet<ListResponse>('/planning/'),
        apiGet<ListResponse>('/planning/orders'),
        apiGet<ListResponse>('/inventory/'),
      ])
      planList.value = planRes.data || []
      orderList.value = orderRes.data || []
      inventoryList.value = invRes.data || []
      cacheStore.set('planning:list', planList.value, 10_000)
      cacheStore.set('planning:orders', orderList.value, 10_000)
      cacheStore.set('planning:inventory', inventoryList.value, 8_000)
      return { planList: planList.value, orderList: orderList.value, inventoryList: inventoryList.value }
    } catch (err: any) {
      error.value = getApiErrorMessage(err) || '读取统筹数据失败'
      throw err
    } finally {
      loading.value = false
    }
  }

  return { planList, orderList, inventoryList, loading, error, fetchPlanningDashboard }
})
