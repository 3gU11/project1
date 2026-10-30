import { beforeAll, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import ElementPlus, { ElMessageBox, ElTable } from 'element-plus'
import ShippingReview from '../src/views/ShippingReview.vue'
import { apiGet, apiPost } from '../src/utils/request'

vi.mock('../src/utils/request', () => ({ apiGet: vi.fn(), apiPost: vi.fn(), getApiErrorMessage: () => '' }))
vi.mock('../src/store/cache', () => ({ useCacheStore: () => ({ remove: vi.fn() }) }))
beforeAll(() => {
  globalThis.ResizeObserver = class { observe() {} unobserve() {} disconnect() {} } as any
})

it('recalls selected pending machines without confirming shipment', async () => {
  const machine = { 流水号: 'M-1', 占用订单号: 'ORDER-1', 客户: '测试客户', 机型: 'X1', 状态: '待发货' }
  let recalled = false
  vi.mocked(apiGet).mockImplementation(async (url) => {
    if (url.includes('/inventory/shipping/pending')) {
      return { data: recalled ? [] : [machine] } as any
    }
    return { data: [] } as any
  })
  vi.mocked(apiPost).mockImplementation(async () => {
    recalled = true
    return { data: { status: '待派生处理' } } as any
  })
  const prompt = vi.spyOn(ElMessageBox, 'prompt').mockResolvedValue({ value: '误发货', action: 'confirm' } as any)
  const wrapper = mount(ShippingReview, { global: { plugins: [ElementPlus] }, attachTo: document.body })
  await flushPromises()

  // 左侧选中订单后，右侧出现该订单的待发货机台清单
  const orderButton = wrapper.find('button.order-item')
  expect(orderButton.exists()).toBe(true)
  await orderButton.trigger('click')
  await flushPromises()

  const table = wrapper.findAllComponents(ElTable).find(item => item.text().includes('M-1'))!
  expect(table).toBeTruthy()
  table.vm.$emit('selection-change', [machine])
  await flushPromises()

  const recall = wrapper.findAll('button').find(item => item.text().includes('发货撤回'))!
  expect(recall.attributes('disabled')).toBeUndefined()
  await recall.trigger('click')
  await flushPromises()

  expect(apiPost).toHaveBeenCalledOnce()
  expect(apiPost).toHaveBeenCalledWith('/workflows/reverse/instances', expect.objectContaining({
    workflow_key: 'allocation-recall',
    business_id: 'ORDER-1',
    reason: '误发货',
    items: [{ object_type: '机台', object_id: 'M-1' }],
  }))
  const tablesAfter = wrapper.findAllComponents(ElTable).map(item => item.text()).join(' | ')
  expect(tablesAfter).not.toContain('M-1')
  wrapper.unmount()
  prompt.mockRestore()
})
