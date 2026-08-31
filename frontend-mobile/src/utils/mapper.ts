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
  max: number | null
  unlimited: boolean
}

const normalizeSlotIdentity = (value: unknown) => String(value ?? '').replace(/\s+/g, '').trim()

export const prioritizeOldFactorySlots = <T extends { code: string }>(slots: T[]): T[] => {
  const oldFactory: T[] = []
  const other: T[] = []
  for (const slot of slots) {
    if (normalizeSlotIdentity(slot.code).startsWith('老厂')) {
      oldFactory.push(slot)
    } else {
      other.push(slot)
    }
  }
  return [...oldFactory, ...other]
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
  const inventoryCountMap = inventoryRows.reduce<Record<string, number>>((acc, row) => {
    const slotCode = String(row.Location_Code ?? row['Location_Code'] ?? '').trim()
    const status = String(row.status ?? row['状态'] ?? '').trim()
    if (slotCode && status.includes('库存中')) {
      const identity = normalizeSlotIdentity(slotCode)
      acc[identity] = (acc[identity] || 0) + 1
    }
    return acc
  }, {})

  const slots = raw?.layout_json?.slots
  if (Array.isArray(slots)) {
    return slots.map((s: any) => {
      const code = String(s.code ?? s.slotCode ?? '').trim()
      const unlimited = Boolean(s.unlimited)
      const rawCapacity = Number(s.capacity)
      return {
      code,
      status: String(s.status ?? '正常'),
      current: inventoryCountMap[normalizeSlotIdentity(code)] || 0,
      max: unlimited ? null : (Number.isFinite(rawCapacity) && rawCapacity > 0 ? rawCapacity : 5),
      unlimited,
    }
    }).filter((slot: MobileSlot) => Boolean(slot.code))
  }
  return []
}
