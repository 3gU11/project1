import { AxiosHeaders, type InternalAxiosRequestConfig } from 'axios'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const pushMock = vi.fn(() => Promise.resolve())
const logoutMock = vi.fn()
const messageErrorMock = vi.fn()

vi.mock('element-plus', () => ({
  ElMessage: {
    error: messageErrorMock,
  },
}))

vi.mock('../src/router', () => ({
  default: {
    push: pushMock,
  },
}))

vi.mock('../src/store/user', () => ({
  useUserStore: () => ({
    token: 'unit-test-token',
    logout: logoutMock,
  }),
}))

describe('request auth header', () => {
  beforeEach(() => {
    vi.resetModules()
    pushMock.mockClear()
    logoutMock.mockClear()
  })

  it('adds bearer token automatically', async () => {
    const { default: request } = await import('../src/utils/request')

    const handler = request.interceptors.request.handlers?.[0]
    const next = await handler?.fulfilled?.({
      headers: new AxiosHeaders(),
    } as InternalAxiosRequestConfig)

    expect(next?.headers?.Authorization).toBe('Bearer unit-test-token')
  })

  it('logs out and redirects to login on 401', async () => {
    const { default: request } = await import('../src/utils/request')

    const handler = request.interceptors.response.handlers?.[0]
    await expect(
      handler?.rejected?.({
        response: { status: 401, data: { detail: 'expired' } },
      }),
    ).rejects.toBeTruthy()

    expect(logoutMock).toHaveBeenCalledTimes(1)
    expect(pushMock).toHaveBeenCalledWith('/login')
    expect(messageErrorMock).toHaveBeenCalled()
  })
})
