import { defineStore } from 'pinia'
import { authApi } from '@/api/auth'

type UserInfo = {
  username: string
  role: string
  name: string
}

export const useUserStore = defineStore('user', {
  state: () => ({
    token: localStorage.getItem('token') || '',
    userInfo: JSON.parse(localStorage.getItem('userInfo') || 'null') as UserInfo | null,
  }),
  getters: {
    isAuthed: (state) => !!state.token,
  },
  actions: {
    async login(username: string, password: string) {
      const res = await authApi.login(username, password)
      this.token = res.access_token
      this.userInfo = res.user
      localStorage.setItem('token', res.access_token)
      localStorage.setItem('userInfo', JSON.stringify(res.user))
    },
    logout() {
      this.token = ''
      this.userInfo = null
      localStorage.removeItem('token')
      localStorage.removeItem('userInfo')
    },
    hasRole(roles: string[]) {
      const role = String(this.userInfo?.role || '').toLowerCase()
      return roles.map((x) => x.toLowerCase()).includes(role)
    },
  },
  persist: true,
})
