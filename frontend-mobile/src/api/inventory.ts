import request from './index'

export const inventoryApi = {
  getInventoryList: (params: { skip?: number; limit?: number; status?: string; model?: string }) =>
    request.get('/inventory', { params }),
  getLayout: () => request.get('/inventory/layout/default'),
}
