import { flushPromises, shallowMount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const mocks = vi.hoisted(() => ({ apiGet: vi.fn(), apiGetAll: vi.fn(), apiPost: vi.fn() }))
vi.mock('../src/utils/request', () => ({ ...mocks, getApiErrorMessage: () => '' }))
vi.mock('vue-router', () => ({ useRoute: () => ({ query: {} }) }))
vi.mock('element-plus', async (importOriginal) => ({
  ...await importOriginal<typeof import('element-plus')>(),
  ElMessage: { error: vi.fn(), warning: vi.fn(), success: vi.fn() },
  ElMessageBox: { confirm: vi.fn() },
}))
import OrderAllocation from '../src/views/OrderAllocation.vue'

const order = (id: string) => ({ '订单号': id, '客户名': id, '需求机型': 'FR-600G*1', status: 'active' })
const deferred = () => {
  let resolve!: (value: any) => void
  let reject!: (reason: Error) => void
  const promise = new Promise<any>((res, rej) => { resolve = res; reject = rej })
  return { promise, resolve, reject }
}
const start = async () => {
  const wrapper = shallowMount(OrderAllocation, { global: { directives: { loading: () => {} } } })
  await flushPromises()
  return wrapper
}

describe('allocation request consistency', () => {
  beforeEach(() => {
    vi.resetAllMocks()
    mocks.apiGetAll.mockResolvedValue([order('A'), order('B')])
  })

  it('merges repeated clicks and publishes demand and machines only when both are ready', async () => {
    const details = deferred(), allocations = deferred()
    mocks.apiGet.mockImplementation((url: string) => url.endsWith('/details') ? details.promise : allocations.promise)
    const wrapper = await start(), vm = wrapper.vm as any
    const first = vm.selectOrder(order('A'))
    const second = vm.selectOrder(order('A'))
    expect(mocks.apiGet).toHaveBeenCalledTimes(2)
    details.resolve({ order: order('A'), source: 'sales_orders', details: [] })
    await flushPromises()
    expect(vm.contextReady).toBe(false)
    allocations.resolve({ data: [{ '流水号': 'A-1' }] })
    await Promise.all([first, second])
    expect(vm.allocations).toEqual([{ '流水号': 'A-1' }])
    expect(vm.contextReady).toBe(true)
    wrapper.unmount()
  })

  it('ignores an older order response after switching orders', async () => {
    const oldDetails = deferred(), oldAllocations = deferred()
    mocks.apiGet.mockImplementation((url: string) => {
      if (url.includes('/A/')) return url.endsWith('/details') ? oldDetails.promise : oldAllocations.promise
      return Promise.resolve(url.endsWith('/details') ? { order: order('B'), details: [] } : { data: [{ '流水号': 'B-1' }] })
    })
    const wrapper = await start(), vm = wrapper.vm as any
    const old = vm.selectOrder(order('A'))
    await vm.selectOrder(order('B'))
    oldDetails.resolve({ order: order('A'), details: [] })
    oldAllocations.resolve({ data: [{ '流水号': 'A-1' }] })
    await old
    expect(vm.selectedOrderId).toBe('B')
    expect(vm.selectedOrder['订单号']).toBe('B')
    expect(vm.allocations).toEqual([{ '流水号': 'B-1' }])
    wrapper.unmount()
  })

  it('keeps actions blocked after a partial load failure and allows retry', async () => {
    mocks.apiGet.mockImplementation((url: string) => url.endsWith('/details')
      ? Promise.resolve({ order: order('A'), details: [] }) : Promise.reject(new Error('offline')))
    const wrapper = await start(), vm = wrapper.vm as any
    await vm.selectOrder(order('A'))
    await vm.completeAllocation()
    expect(vm.contextReady).toBe(false)
    expect(mocks.apiPost).not.toHaveBeenCalled()
    mocks.apiGet.mockResolvedValue({ order: order('A'), details: [], data: [] })
    await vm.selectOrder(order('A'))
    expect(vm.contextReady).toBe(true)
    wrapper.unmount()
  })

  it('keeps a forced refresh when an older request for the same order completes later', async () => {
    const oldDetails = deferred(), oldAllocations = deferred()
    mocks.apiGet.mockImplementationOnce(() => oldDetails.promise).mockImplementationOnce(() => oldAllocations.promise)
      .mockImplementation((url: string) => Promise.resolve(url.endsWith('/details')
        ? { order: { ...order('A'), status: 'ready' }, details: [] } : { data: [{ '流水号': 'LATEST' }] }))
    const wrapper = await start(), vm = wrapper.vm as any
    const old = vm.selectOrder(order('A'))
    await vm.loadSelectedOrderContext(true)
    oldDetails.resolve({ order: order('A'), details: [] })
    oldAllocations.resolve({ data: [{ '流水号': 'STALE' }] })
    await old
    expect(vm.selectedOrder.status).toBe('ready')
    expect(vm.allocations).toEqual([{ '流水号': 'LATEST' }])
    expect(vm.contextReady).toBe(true)
    wrapper.unmount()
  })
})
