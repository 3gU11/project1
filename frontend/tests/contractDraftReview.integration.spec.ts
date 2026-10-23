import { defineComponent, h } from 'vue'
import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const mocks = vi.hoisted(() => ({
  order: {
    id: 42,
    order_no: 'DEALER-ORDER-42',
    status: 'pending',
    model: 'TEST-MODEL',
    quantity: 2,
    items: [{ line_no: 1, model: 'TEST-MODEL', quantity: 2, status: 'pending' }],
  },
  openForOrder: vi.fn(),
  apiGet: vi.fn(),
  apiGetAll: vi.fn(),
  apiPost: vi.fn(),
  getApiErrorMessage: vi.fn(() => ''),
  ensureLoaded: vi.fn(async () => []),
  routerPush: vi.fn(),
}))

vi.mock('../src/utils/request', () => ({
  apiGet: mocks.apiGet,
  apiGetAll: mocks.apiGetAll,
  apiPost: mocks.apiPost,
  getApiErrorMessage: mocks.getApiErrorMessage,
}))

vi.mock('../src/store/modelDictionary', () => ({
  useModelDictionaryStore: () => ({ rows: [], ensureLoaded: mocks.ensureLoaded }),
}))

vi.mock('vue-router', () => ({
  useRouter: () => ({ push: mocks.routerPush }),
}))

vi.mock('element-plus', () => ({
  ElMessage: { error: vi.fn(), info: vi.fn(), success: vi.fn(), warning: vi.fn() },
  ElMessageBox: { confirm: vi.fn(), prompt: vi.fn() },
}))

vi.mock('@element-plus/icons-vue', () => ({
  Loading: defineComponent({ render: () => null }),
}))

vi.mock('../src/components/ContractDraftReview.vue', async () => {
  const { defineComponent, h } = await import('vue')
  return {
    default: defineComponent({
      name: 'ContractDraftReview',
      props: ['canApproveOrder', 'confirmOrderApprove'],
      emits: ['done', 'approve-order'],
      setup(_, { expose }) {
        expose({ openForOrder: mocks.openForOrder })
        return () => h('div', { 'data-test': 'contract-draft-review' })
      },
    }),
  }
})

import DealerOrderReview from '../src/views/DealerOrderReview.vue'
import ContractDraftReview from '../src/components/ContractDraftReview.vue'

const ButtonStub = defineComponent({
  props: ['disabled'],
  setup(props, { attrs, slots }) {
    return () => h('button', {
      ...attrs,
      disabled: props.disabled,
      onClick: attrs.onClick,
    }, slots.default?.())
  },
})

const TableColumnStub = defineComponent({
  setup(_, { slots }) {
    return () => h('div', slots.default?.({ row: {
      ...mocks.order,
      ...mocks.order.items[0],
      _order: mocks.order,
      _row_key: 'DEALER-ORDER-42-1',
    } }))
  },
})

const NullStub = defineComponent({ render: () => null })

describe('dealer order contract draft entry', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mocks.ensureLoaded.mockResolvedValue([])
    mocks.apiGet.mockImplementation(async (url: string) => {
      if (url === '/dealer-orders/pending-count') return { total: 1, pending: 1, factory_pending: 0 }
      if (url === '/dealer-orders/cloud-sync-status') return { pending: 0, failed: 0, recent_failed: [] }
      if (url.startsWith('/dealer-orders/')) return { data: [mocks.order], total: 1 }
      return {}
    })
  })

  it('opens the contract review for the exact order selected from its row', async () => {
    const wrapper = mount(DealerOrderReview, {
      global: {
        config: { warnHandler: () => {} },
        stubs: {
          'el-button': ButtonStub,
          'el-table': defineComponent({ setup(_, { slots }) { return () => h('div', slots.default?.()) } }),
          'el-table-column': TableColumnStub,
          'el-dialog': NullStub,
          'el-drawer': NullStub,
        },
      },
    })
    await flushPromises()

    const action = wrapper.findAll('button').find((button) => button.text().includes('预览并审批'))
    expect(action, 'the order row should provide a contract preview and approval action').toBeDefined()
    await action!.trigger('click')

    expect(mocks.openForOrder).toHaveBeenCalledWith('DEALER-ORDER-42')
    const review = wrapper.findComponent(ContractDraftReview)
    expect(review.props('canApproveOrder')).toBe(true)
    expect(review.props('confirmOrderApprove')).toEqual(expect.any(Function))
    await expect((review.props('confirmOrderApprove') as () => Promise<boolean>)()).resolves.toBe(true)
    expect(mocks.apiPost).toHaveBeenCalledWith('/dealer-orders/DEALER-ORDER-42/approve', { note: '' })

    const orderListCalls = mocks.apiGet.mock.calls.filter(([url]) => url === '/dealer-orders/').length
    review.vm.$emit('done')
    await flushPromises()
    expect(mocks.apiGet.mock.calls.filter(([url]) => url === '/dealer-orders/').length).toBeGreaterThan(orderListCalls)

    wrapper.unmount()
  })
})
