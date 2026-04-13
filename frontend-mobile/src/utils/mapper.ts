export type MobileMachine = {
  id: string
  serialNo: string
  model: string
  batchNo: string
  slotCode: string
  status: string
  updatedAt: string
}

export type MobileSlot = {
  code: string
  status: string
  current: number
  max: number
}

export const mapMachine = (raw: Record<string, unknown>, index = 0): MobileMachine => {
  const serialNo = String(raw.serialNo ?? raw['流水号'] ?? '').trim()
  const model = String(raw.model ?? raw['机型'] ?? '').trim()
  const batchNo = String(raw.batchNo ?? raw['批次号'] ?? '').trim()
  const slotCode = String(raw.slotCode ?? raw.Location_Code ?? '').trim()
  const status = String(raw.status ?? raw['状态'] ?? '').trim()
  const updatedAt = String(raw.updatedAt ?? raw['更新时间'] ?? '').trim()
  return {
    id: serialNo || `${index}`,
    serialNo,
    model,
    batchNo,
    slotCode,
    status,
    updatedAt,
  }
}

export const mapLayoutSlots = (raw: any, inventoryRows: Record<string, unknown>[] = []): MobileSlot[] => {
  const maxCapacity = 5
  const inventoryCountMap = inventoryRows.reduce<Record<string, number>>((acc, row) => {
    const slotCode = String(row.Location_Code ?? row['Location_Code'] ?? '').trim()
    const status = String(row.status ?? row['状态'] ?? '').trim()
    if (slotCode && status.includes('库存中')) {
      acc[slotCode] = (acc[slotCode] || 0) + 1
    }
    return acc
  }, {})

  const slots = raw?.layout_json?.slots
  if (Array.isArray(slots) && slots.length > 0) {
    return slots.map((s: any) => ({
      code: String(s.code ?? s.slotCode ?? ''),
      status: String(s.status ?? '正常'),
      current: inventoryCountMap[String(s.code ?? s.slotCode ?? '')] || 0,
      max: maxCapacity,
    }))
  }
  const defaults: MobileSlot[] = []
  for (let row = 1; row <= 3; row += 1) {
    for (let col = 1; col <= 6; col += 1) {
      const code = `A-${row}-${String(col).padStart(2, '0')}`
      defaults.push({
        code,
        status: '正常',
        current: inventoryCountMap[code] || 0,
        max: maxCapacity,
      })
    }
  }
  return defaults
}
