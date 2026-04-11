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

export default request
