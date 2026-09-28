import { defineStore } from 'pinia'
import { authApi } from '@/api/auth'

type UserInfo = {
  username: string
  role: string
  name: string
  permissions?: string[]
}

let pendingRefresh: Promise<boolean> | null = null

export const useUserStore = defineStore('user', {
  state: () => ({
    token: '',
    userInfo: null as UserInfo | null,
    userRefreshedAt: 0,
  }),
  getters: {
    isAuthed: (state) => !!state.token,
  },
  actions: {
    async login(username: string, password: string) {
      const res = await authApi.login(username, password)
      this.token = res.access_token
      this.userInfo = res.user
      this.userRefreshedAt = Date.now()
    },
    async refreshUser(force = false) {
      if (!this.token) return false
      const now = Date.now()
      if (!force && this.userInfo && now - this.userRefreshedAt < 30_000) return true
      if (pendingRefresh) return pendingRefresh
      const request = (async () => {
        try {
          const res = await authApi.me()
          if (!res?.user) return false
          this.userInfo = res.user
          this.userRefreshedAt = Date.now()
          return true
        } catch {
          return false
        }
      })()
      pendingRefresh = request
      try { return await request } finally { pendingRefresh = null }
    },
    logout() {
      this.token = ''
      this.userInfo = null
      this.userRefreshedAt = 0
    },
    hasRole(roles: string[]) {
      const role = String(this.userInfo?.role || '').toLowerCase()
      return roles.map((x) => x.toLowerCase()).includes(role)
    },
    hasPermission(permission: string) {
      return (this.userInfo?.permissions || []).includes(permission)
    },
    hasAnyPermission(permissions: string[]) {
      const owned = new Set(this.userInfo?.permissions || [])
      return permissions.some((permission) => owned.has(permission))
    },
  },
  persist: {
    key: 'v8-mobile-user',
    pick: ['token', 'userInfo'],
  },
})
