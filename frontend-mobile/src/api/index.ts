import axios from 'axios'
import { showToast } from 'vant'

const request = axios.create({
  baseURL: '/api/v1',
  timeout: 30000,
})

request.interceptors.request.use((config) => {
  const token = localStorage.getItem('token')
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

request.interceptors.response.use(
  (resp) => resp.data,
  (error) => {
    if (error?.response?.status === 401) {
      localStorage.removeItem('token')
      localStorage.removeItem('userInfo')
      if (location.pathname !== '/login') {
        location.href = '/login'
      }
    } else {
      showToast(error?.response?.data?.detail || error.message || '请求失败')
    }
    return Promise.reject(error)
  }
)

export const apiGetAll = async <T = any>(url: string, params: Record<string, any> = {}, pageSize = 1000): Promise<T[]> => {
  let skip = 0
  let total = Number.POSITIVE_INFINITY
  const rows: T[] = []

  while (skip < total) {
    const res = await request.get<any, { data?: T[]; total?: number }>(url, {
      params: {
        ...params,
        skip,
        limit: pageSize,
      },
    })
    const chunk = Array.isArray(res?.data) ? res.data : []
    rows.push(...chunk)

    const nextTotal = Number(res?.total)
    total = Number.isFinite(nextTotal) ? nextTotal : chunk.length

    if (chunk.length === 0) break
    skip += chunk.length
    if (chunk.length < pageSize) break
  }

  return rows
}

export default request
