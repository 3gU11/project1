import axios, { type AxiosRequestConfig, type AxiosResponse } from 'axios'
import { ElMessage } from 'element-plus'
import { useUserStore } from '../store/user'
import router from '../router'

const normalizeApiBaseUrl = (raw: string) => {
  const val = String(raw || '').trim()
  if (!val) return '/api/v1'
  if (val.startsWith('http://') || val.startsWith('https://')) return val
  return val.startsWith('/') ? val : `/${val}`
}

const API_BASE_URL = normalizeApiBaseUrl(String(import.meta.env.VITE_API_BASE_URL || '/api/v1'))

const request = axios.create({
  baseURL: API_BASE_URL,
  timeout: 10000,
})

let authRedirecting = false
export const getApiErrorMessage = (error: any) => {
  const detail = error?.response?.data?.detail
  if (typeof detail === 'string' && detail.trim()) return detail
  if (Array.isArray(detail) && detail.length > 0) return String(detail[0]?.msg || '请求参数错误')
  if (detail && typeof detail === 'object' && detail.message) return String(detail.message)
  return ''
}

request.interceptors.request.use(
  (config) => {
    const userStore = useUserStore()
    if (userStore.token) {
      config.headers.Authorization = `Bearer ${userStore.token}`
    }
    return config
  },
  (error) => {
    return Promise.reject(error)
  }
)

request.interceptors.response.use(
  (response) => {
    return response
  },
  (error) => {
    if (error.response) {
      const status = error.response.status
      if (status === 401) {
        if (!authRedirecting) {
          authRedirecting = true
          ElMessage.error('认证失败或登录过期，请重新登录')
          const userStore = useUserStore()
          userStore.logout()
          router.push('/login').finally(() => {
            authRedirecting = false
          })
        }
      } else if (status === 403) {
        ElMessage.error('没有操作权限')
      } else {
        ElMessage.error(getApiErrorMessage(error) || '系统错误')
      }
    } else {
      ElMessage.error('网络连接错误')
    }
    return Promise.reject(error)
  }
)

export type ApiConfig = AxiosRequestConfig
export const apiGet = async <T = any>(url: string, config?: ApiConfig): Promise<T> => {
  const response = await request.get<T>(url, config)
  return response.data
}
export const apiGetAll = async <T = any>(url: string, pageSize = 1000): Promise<T[]> => {
  let skip = 0
  let total = Number.POSITIVE_INFINITY
  const rows: T[] = []
  const sep = url.includes('?') ? '&' : '?'
  while (skip < total) {
    const res = await apiGet<{ data?: T[]; total?: number }>(`${url}${sep}skip=${skip}&limit=${pageSize}`)
    const chunk = res.data || []
    rows.push(...chunk)
    const safeTotal = Number.isFinite(Number(res.total)) ? Number(res.total) : chunk.length
    total = safeTotal
    if (chunk.length === 0) break
    skip += chunk.length
    if (chunk.length < pageSize) break
  }
  return rows
}
export const apiPost = async <T = any>(url: string, data?: any, config?: ApiConfig): Promise<T> => {
  const response = await request.post<T>(url, data, config)
  return response.data
}
export const apiPut = async <T = any>(url: string, data?: any, config?: ApiConfig): Promise<T> => {
  const response = await request.put<T>(url, data, config)
  return response.data
}
export const apiPatch = async <T = any>(url: string, data?: any, config?: ApiConfig): Promise<T> => {
  const response = await request.patch<T>(url, data, config)
  return response.data
}
export const apiDelete = async <T = any>(url: string, config?: ApiConfig): Promise<T> => {
  const response = await request.delete<T>(url, config)
  return response.data
}
export const unwrap = <T = any>(response: AxiosResponse<T>): T => response.data

export default request
