import { flushPromises, shallowMount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const mocks = vi.hoisted(() => ({
  apiGet: vi.fn(), apiDelete: vi.fn(), confirm: vi.fn(),
  success: vi.fn(), error: vi.fn(), warning: vi.fn(),
}))
vi.mock('../src/utils/request', () => ({
  apiGet: mocks.apiGet, apiDelete: mocks.apiDelete,
  apiPost: vi.fn(), apiDownloadBlob: vi.fn(), apiGetBlobUrl: vi.fn(),
  getApiErrorMessage: () => '',
}))
vi.mock('element-plus', async (importOriginal) => ({
  ...await importOriginal<typeof import('element-plus')>(),
  ElMessageBox: { confirm: mocks.confirm },
  ElMessage: { success: mocks.success, error: mocks.error, warning: mocks.warning },
}))
import CustomerFinishedGoods from '../src/views/CustomerFinishedGoods.vue'
import ElementPlus from 'element-plus'

const row = { id: 1, file_name: '不明合同.pdf', status: 'pending' }
const start = async () => {
  const wrapper = shallowMount(CustomerFinishedGoods, {
    global: { plugins: [ElementPlus] },
  })
  await flushPromises()
  return wrapper
}

describe('交付信息删除', () => {
  beforeEach(() => {
    vi.resetAllMocks()
    mocks.apiGet.mockResolvedValue({ data: [row], total: 1 })
    mocks.confirm.mockResolvedValue('confirm')
    mocks.apiDelete.mockResolvedValue({ deleted: true, warnings: [] })
  })

  it('取消确认时保留上传记录，不调用删除接口', async () => {
    mocks.confirm.mockRejectedValue('cancel')
    const wrapper = await start(), vm = wrapper.vm as any
    await vm.deletePendingUpload(row)
    expect(mocks.apiDelete).not.toHaveBeenCalled()
    expect(vm.deliveryUploads).toEqual([row])
    wrapper.unmount()
  })

  it('确认删除后刷新列表、数量并关闭该上传的处理窗口', async () => {
    const wrapper = await start(), vm = wrapper.vm as any
    vm.processUpload = row
    vm.processVisible = true
    mocks.apiGet.mockResolvedValue({ data: [], total: 0 })
    await vm.deletePendingUpload(row)
    expect(mocks.apiDelete).toHaveBeenCalledWith('/inventory/delivery-info-uploads/1')
    expect(vm.deliveryUploads).toEqual([])
    expect(vm.pendingUploadCount).toBe(0)
    expect(vm.processVisible).toBe(false)
    expect(mocks.success).toHaveBeenCalled()
    wrapper.unmount()
  })

  it('删除失败时保留列表，显示错误并允许重试', async () => {
    mocks.apiDelete.mockRejectedValue(new Error('offline'))
    const wrapper = await start(), vm = wrapper.vm as any
    await vm.deletePendingUpload(row)
    expect(vm.deliveryUploads).toEqual([row])
    expect(vm.deletingUploadId).toBeNull()
    expect(mocks.error).toHaveBeenCalled()
    expect(mocks.success).not.toHaveBeenCalled()
    wrapper.unmount()
  })

  it('文件清理失败时展示后端警告', async () => {
    mocks.apiDelete.mockResolvedValue({ deleted: true, warnings: ['附件文件清理失败'] })
    const wrapper = await start(), vm = wrapper.vm as any
    await vm.deletePendingUpload(row)
    expect(mocks.warning).toHaveBeenCalledWith('附件文件清理失败')
    expect(mocks.success).not.toHaveBeenCalled()
    wrapper.unmount()
  })
})
