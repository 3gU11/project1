import { defineComponent, h } from 'vue'
import { flushPromises, mount } from '@vue/test-utils'
import { describe, expect, it, vi } from 'vitest'

const mocks = vi.hoisted(() => ({
  apiGet: vi.fn(),
  apiPost: vi.fn(),
  apiPut: vi.fn(),
  confirmOrderApprove: vi.fn(async () => false),
}))

vi.mock('../src/utils/request', () => ({
  apiGet: mocks.apiGet,
  apiPost: mocks.apiPost,
  apiPut: mocks.apiPut,
}))

vi.mock('../src/utils/contractPreview', () => ({
  contractPreviewHtml: vi.fn(async () => '<p>Verified contract preview</p>'),
}))

vi.mock('element-plus', async (importOriginal) => {
  const actual = await importOriginal<typeof import('element-plus')>()
  return {
    ...actual,
    ElMessage: { error: vi.fn(), info: vi.fn(), success: vi.fn(), warning: vi.fn() },
    ElMessageBox: { confirm: vi.fn(async () => undefined), prompt: vi.fn() },
  }
})

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

const DialogStub = defineComponent({
  setup(_, { slots }) {
    return () => h('div', [slots.default?.(), slots.footer?.()])
  },
})

describe('contract draft approval ordering', () => {
  it('does not archive the attachment when order approval does not complete', async () => {
    mocks.apiGet.mockImplementation(async (url: string) => {
      if (url === '/contract-drafts/local') {
        return [{
          id: 'draft-1',
          state: 'preview_ready',
          preview_hash: 'preview-hash',
          source_order_no: 'DEALER-ORDER-42',
          created_at: '2026-10-23 10:00:00',
          source_order_snapshot: {},
          fields: {},
          missing_fields: [],
        }]
      }
      return new ArrayBuffer(1)
    })

    const wrapper = mount(ContractDraftReview, {
      props: {
        canApproveOrder: true,
        confirmOrderApprove: mocks.confirmOrderApprove,
      },
      global: {
        config: { warnHandler: () => {} },
        stubs: { 'el-button': ButtonStub, 'el-dialog': DialogStub },
      },
    })

    await (wrapper.vm as any).openForOrder('DEALER-ORDER-42')
    await flushPromises()

    const approveButton = wrapper.findAll('button').find((button) => button.text().includes('审批通过'))
    expect(approveButton, wrapper.html()).toBeDefined()
    await approveButton!.trigger('click')
    await flushPromises()

    expect(mocks.confirmOrderApprove).toHaveBeenCalledOnce()
    expect(mocks.apiPost).not.toHaveBeenCalledWith(
      '/contract-drafts/local/draft-1/review',
      expect.anything(),
      expect.anything(),
    )

    wrapper.unmount()
  })
})
