import request from './index'

export type LoginResponse = {
  access_token: string
  token_type: string
  user: {
    username: string
    role: string
    name: string
  }
}

export type RegisterPayload = {
  username: string
  password: string
  role: 'Boss' | 'Admin' | 'Sales' | 'Prod' | 'Inbound'
  name: string
}

export const authApi = {
  login: (username: string, password: string) => {
    const form = new URLSearchParams()
    form.set('username', username)
    form.set('password', password)
    return request.post<any, LoginResponse>('/auth/login', form, {
      headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    })
  },
  register: (payload: RegisterPayload) => request.post('/users/register', payload),
}
