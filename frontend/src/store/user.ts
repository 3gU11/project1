import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { useCacheStore } from './cache'
import { normalizeRole } from '../utils/roles'

type UserInfo = { username: string; role: string; name: string; permissions: string[] }
const STORAGE_KEY = 'v7ex_auth'

export const useUserStore = defineStore('user', () => {
  const userInfo = ref<UserInfo | null>(null)
  const token = ref<string>('')
  const rememberMe = ref<boolean>(true)
  
  const isAuthenticated = computed(() => !!token.value && !!userInfo.value)

  function loadFromStorage() {
    const raw = localStorage.getItem(STORAGE_KEY) || sessionStorage.getItem(STORAGE_KEY)
    if (!raw) return
    try {
      const parsed = JSON.parse(raw)
      token.value = parsed.token || ''
      userInfo.value = parsed.userInfo ? { ...parsed.userInfo, permissions: Array.isArray(parsed.userInfo.permissions) ? parsed.userInfo.permissions : [] } : null
      rememberMe.value = !!parsed.rememberMe
    } catch {
      // ignore broken storage payload
    }
  }

  function saveToStorage() {
    const payload = JSON.stringify({
      token: token.value,
      userInfo: userInfo.value,
      rememberMe: rememberMe.value,
    })
    localStorage.removeItem(STORAGE_KEY)
    sessionStorage.removeItem(STORAGE_KEY)
    if (!token.value || !userInfo.value) return
    if (rememberMe.value) {
      localStorage.setItem(STORAGE_KEY, payload)
    } else {
      sessionStorage.setItem(STORAGE_KEY, payload)
    }
  }

  function login(userData: UserInfo, jwtToken: string, remember = true) {
    const cacheStore = useCacheStore()
    cacheStore.clear()
    userInfo.value = { ...userData, permissions: Array.isArray(userData.permissions) ? userData.permissions : [] }
    token.value = jwtToken
    rememberMe.value = remember
    saveToStorage()
  }

  function logout() {
    const cacheStore = useCacheStore()
    cacheStore.clear()
    userInfo.value = null
    token.value = ''
    rememberMe.value = true
    localStorage.removeItem(STORAGE_KEY)
    sessionStorage.removeItem(STORAGE_KEY)
  }

  function hasRole(roles?: string[]) {
    if (!roles || roles.length === 0) return true
    const role = normalizeRole(userInfo.value?.role || '')
    return roles.map((r) => normalizeRole(r)).includes(role)
  }

  function hasPermission(permission?: string) {
    if (!permission) return true
    return (userInfo.value?.permissions || []).map((p) => String(p).trim()).includes(permission)
  }

  loadFromStorage()

  return {
    userInfo,
    token,
    rememberMe,
    isAuthenticated,
    login,
    logout,
    hasRole,
    hasPermission,
  }
})
