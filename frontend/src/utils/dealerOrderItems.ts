/**
 * 经销商订单明细 → 转合同明细行。
 *
 * 加高只认明细自己的字段：
 *   1. 云端用 inventory_type = heightened 标记加高（与本地 dealer_orders.inventory_type 同口径）；
 *   2. 有的渠道会把「(加高)」「（加高）」直接拼在机型后面。
 *
 * 不能用 remark / 附加备注判断：云端在没有行备注时会把「订单备注」复制到每一行明细，
 * 订单备注里出现「加高」（例如「400G加高100mm」）就会把整单所有机型误标成加高。
 */

export type DealerOrderLineLike = {
  model?: string
  quantity?: number | string
  batch_no?: string
  inventory_type?: string
  remark?: string
  extra_remark?: string
  factory_remark?: string
  ERMQ?: number | string
}

export type DealerOrderLike = DealerOrderLineLike & {
  items?: DealerOrderLineLike[]
}

export type ConvertItemRow = {
  model: string
  qty: number
  high: boolean
  rowNote: string
  remark: string
  extraRemark: string
  ermq: number
  batch_no: string
  inventory_type: string
}

/** 云端标记加高的 inventory_type 取值（见 crud/local_contract_drafts.py 的 _HEIGHTENED_TYPES）。 */
const HEIGHTENED_INVENTORY_TYPES = new Set(['heightened', 'heighten', 'high', 'tall'])

/** 库存中（现货）来源的 inventory_type 取值，必须与后端判定一致。 */
const STOCK_INVENTORY_TYPES = new Set(['finished', 'stock', '现货'])

/** 库存中（现货）来源的 batch_no 取值，必须与后端判定一致。 */
const STOCK_BATCH_NOS = new Set(['FINISHED-STOCK', '库存中', '现货', '现货库存'])

/** 云端「无货预订/无标识批次需求」的 inventory_type 取值，必须与后端判定一致。 */
const PREORDER_INVENTORY_TYPES = new Set(['unmarked', 'preorder', 'pre_order', '无货预订'])

/**
 * 无货预订行：空批次 + inventory_type=unmarked，代表未来排产需求，
 * 转合同时单独成一张「待规划」合同并进入沙盘。
 */
export const isPreorderLine = (item?: { batch_no?: string; inventory_type?: string } | null) => {
  if (!item) return false
  if (String(item.batch_no ?? '').trim()) return false
  return PREORDER_INVENTORY_TYPES.has(String(item.inventory_type ?? '').trim().toLowerCase())
}

/**
 * 库存中（现货）来源：批次为空、FINISHED-STOCK/库存中/现货/现货库存，
 * 或 inventory_type 为 finished/stock/现货。
 */
export const isStockSourceLine = (item?: { batch_no?: string; inventory_type?: string } | null) => {
  if (!item) return false
  const inventoryType = String(item.inventory_type ?? '').trim().toLowerCase()
  if (STOCK_INVENTORY_TYPES.has(inventoryType)) return true
  const batchNo = String(item.batch_no ?? '').trim()
  if (!batchNo) return true
  if (batchNo.startsWith('现货')) return true
  return STOCK_BATCH_NOS.has(batchNo) || STOCK_BATCH_NOS.has(batchNo.toUpperCase())
}

/** 转合同明细的自动路径文案。 */
export const convertLinePathLabel = (item?: { batch_no?: string; inventory_type?: string } | null) => {
  if (isPreorderLine(item)) return '无货预订 → 待规划（沙盘）'
  if (isStockSourceLine(item)) return '库存中 → 库存配货'
  return `批次 ${String(item?.batch_no ?? '').trim()} → 优先按批次配货`
}

/** 判断一条经销商订单明细是否加高；只看明细自己的字段，不看订单备注。 */
export const isHeightenedDealerOrderLine = (item?: DealerOrderLineLike | null) => {
  if (!item) return false
  const inventoryType = String(item.inventory_type ?? '').trim().toLowerCase()
  if (HEIGHTENED_INVENTORY_TYPES.has(inventoryType)) return true
  return String(item.model ?? '').includes('加高')
}

/**
 * 把经销商订单（含多条明细行）展开成转合同表单行。
 * 订单没有明细时退化成单行（兼容旧接口/测试数据），此时直接读订单自身的字段。
 */
export const normalizeDealerOrderItems = (order: DealerOrderLike): ConvertItemRow[] => {
  const source = order.items?.length ? order.items : [order]
  return source
    .map((item) => {
      const model = String(item.model || '').trim()
      const qty = Math.max(1, Number(item.quantity || 1))
      const remark = String(item.remark || '').trim()
      const extraRemark = String(item.factory_remark || item.extra_remark || '').trim()
      const ermq = Number(item.ERMQ || 0)
      const high = isHeightenedDealerOrderLine(item)
      const batchNo = String(item.batch_no ?? '').trim()
      const inventoryType = String(item.inventory_type ?? '').trim()
      const rowNote = [
        remark ? `[备注]${remark}` : '',
        extraRemark ? `[附加]${extraRemark}` : '',
        ermq > 0 ? `[改数]${ermq}` : '',
      ].filter(Boolean).join(' ')
      return { model, qty, high, rowNote, remark, extraRemark, ermq, batch_no: batchNo, inventory_type: inventoryType }
    })
    .filter((item) => item.model)
}
