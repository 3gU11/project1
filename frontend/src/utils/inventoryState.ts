export const LEGACY_BOUND_STATUS = '已绑定'

export const isPendingInbound = (row: any) =>
  String(row?.['状态'] || '').trim() === '待入库' && row?.pending_inbound_scope !== 'queued'

export const getInventoryLifecycleStatus = (row: any) => {
  const status = String(row?.['状态'] || '').trim()
  return status === LEGACY_BOUND_STATUS ? '待入库' : status
}

export const isContractLinked = (row: any) => {
  return Boolean(String(row?.['合同号'] || '').trim())
}

export const isOrderReserved = (row: any) => {
  return Boolean(String(row?.['占用订单号'] || '').trim())
}

export const isMachineBound = (row: any) => {
  return isContractLinked(row) || isOrderReserved(row)
}

export const getBindingTitle = (row: any) => {
  const contractNo = String(row?.['合同号'] || '').trim()
  const orderNo = String(row?.['占用订单号'] || '').trim()
  return [contractNo ? `合同：${contractNo}` : '', orderNo ? `订单：${orderNo}` : ''].filter(Boolean).join('；')
}

export const isLegacyBound = (row: any) => {
  return String(row?.['状态'] || '').trim() === LEGACY_BOUND_STATUS
}
