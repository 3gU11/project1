import request, { apiGetAll } from './index'

export const inventoryApi = {
  getInventoryList(params?: any) {
    return request.get('/inventory/', { params })
  },
  getInventoryAll(params?: any) {
    return apiGetAll('/inventory/', params)
  },
  getInventory(params?: any) {
    return request.get('/inventory/', { params })
  },
  inboundToSlot(data: { serial_no: string; slot_code: string; is_transfer?: boolean }) {
    return request.post('/inventory/inbound-to-slot', data)
  },
  getLayout() {
    return request.get('/inventory/layout/default')
  },
  getMachineArchive(serial_no: string) {
    return request.get(`/inventory/machine-archive/${serial_no}/files`)
  },
  uploadMachineArchive(serial_no: string, formData: FormData) {
    return request.post(`/inventory/machine-archive/${serial_no}/upload`, formData)
  },
  deleteMachineArchive(serial_no: string, file_name: string) {
    return request.delete(`/inventory/machine-archive/${serial_no}/files/${file_name}`)
  }
}
