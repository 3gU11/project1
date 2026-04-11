import request from './index'

export const inboundApi = {
  getPendingList: (skip = 0, limit = 100) =>
    request.get('/inventory/import-staging', { params: { skip, limit } }),
  confirmInbound: (serialNo: string, slotCode: string) =>
    request.post('/inventory/inbound-to-slot', { serial_no: serialNo, slot_code: slotCode }),
  uploadBatch: (file: File) => {
    const form = new FormData()
    form.append('file', file)
    return request.post('/inventory/import-staging/upload', form, {
      headers: { 'Content-Type': 'multipart/form-data' },
    })
  },
  getLayout: () => request.get('/inventory/layout/default'),
}
