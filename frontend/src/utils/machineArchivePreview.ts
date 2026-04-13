import request from './request'

export const getMachineArchivePreviewObjectUrl = async (serialNo: string, fileName: string) => {
  const response = await request.get(
    `/inventory/machine-archive/${encodeURIComponent(serialNo)}/files/${encodeURIComponent(fileName)}/preview`,
    { responseType: 'blob' }
  )
  const blob = response.data instanceof Blob ? response.data : new Blob([response.data])
  return URL.createObjectURL(blob)
}
