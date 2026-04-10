import { defineStore } from 'pinia'
import { ref } from 'vue'
import { apiGet, getApiErrorMessage } from '../utils/request'
import { useCacheStore } from './cache'

type ListResponse<T = any> = { data: T[]; total?: number; skip?: number; limit?: number }

export const usePlanningStore = defineStore('planning', () => {
  const planList = ref<any[]>([])
  const orderList = ref<any[]>([])
  const inventoryList = ref<any[]>([])
  const loading = ref(false)
  const error = ref('')
  const cacheStore = useCacheStore()
  const PAGE_SIZE = 1000

  const fetchAllPages = async (path: string) => {
    let skip = 0
    let total = Number.POSITIVE_INFINITY
    const rows: any[] = []
    while (skip < total) {
      const res = await apiGet<ListResponse>(`${path}?skip=${skip}&limit=${PAGE_SIZE}`)
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
      const [planRows, orderRows, invRows] = await Promise.all([
        fetchAllPages('/planning/'),
        fetchAllPages('/planning/orders'),
        fetchAllPages('/inventory/'),
      ])
      planList.value = planRows
      orderList.value = orderRows
      inventoryList.value = invRows
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
