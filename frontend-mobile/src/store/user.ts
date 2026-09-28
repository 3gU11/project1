import { defineStore } from 'pinia'
import { authApi } from '@/api/auth'

type UserInfo = {
  username: string
  role: string
  name: string
  permissions?: string[]
}

export const useUserStore = defineStore('user', {
  state: () => ({
    token: '',
    userInfo: null as UserInfo | null,
  }),
  getters: {
    isAuthed: (state) => !!state.token,
  },
  actions: {
    async login(username: string, password: string) {
      const res = await authApi.login(username, password)
      this.token = res.access_token
      this.userInfo = res.user
    },
    async refreshUser() {
      if (!this.token) return false
      try {
        const res = await authApi.me()
        if (!res?.user) return false
        this.userInfo = res.user
        return true
      } catch {
        return false
      }
    },
    logout() {
      this.token = ''
      this.userInfo = null
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
