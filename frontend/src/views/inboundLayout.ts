export type WarehouseSlot = {
  id: string
  code: string
  x: number
  y: number
  w: number
  h: number
  status?: string
  allowed_models?: string
}

export type SlotStat = {
  count: number
  capacity: number
  latestInboundTime: string
  isFull: boolean
  isOverflow: boolean
}

export const SLOT_CAPACITY = 5
export const LARGE_SLOT_CAPACITY = 15
export const SCRAP_SLOT_CAPACITY = 5
export const UNLIMITED_SLOT_CAPACITY = Number.POSITIVE_INFINITY
export const OLD_FACTORY_SLOT_CODES = [
  '老厂一车间400',
  '老厂一车间600',
  '老厂一车间500',
  '老厂四车间二楼400',
  '老厂四车间一楼400',
  '老厂四车间一楼500',
  '老厂四车间一楼600',
]
export const EMERGENCY_BUFFER_SLOT_CODES = [
  '新厂一楼小机床存放区',
  '新厂2楼仓库门口存放区',
]

const normalizeSlotCode = (code: any) => String(code || '').replace(/\s+/g, '').trim()
const largeCapacityPrefixes = ['大机型区域', '闲置区', '实验室区'].map(normalizeSlotCode)
const scrapSlotPrefixes = ['报废区', '整机报废区'].map(normalizeSlotCode)
const oldFactorySlotCodes = OLD_FACTORY_SLOT_CODES.map(normalizeSlotCode)
const unlimitedSlotCodes = [...OLD_FACTORY_SLOT_CODES, ...EMERGENCY_BUFFER_SLOT_CODES].map(normalizeSlotCode)

export const canonicalSlotCode = (code: any) => String(code || '').trim()

export const isScrapSlot = (code: any) => {
  const normalized = normalizeSlotCode(code)
  return scrapSlotPrefixes.some((prefix) => normalized.startsWith(prefix))
}

export const isUnlimitedSlot = (code: any) => {
  const normalized = normalizeSlotCode(code)
  return unlimitedSlotCodes.includes(normalized) || normalized.startsWith('老厂')
}

export const isOldFactorySlot = (code: any) => {
  const normalized = normalizeSlotCode(code)
  return oldFactorySlotCodes.includes(normalized) || normalized.startsWith('老厂')
}

export const prioritizeOldFactorySlots = <T extends { code?: any }>(slots: T[]): T[] => {
  const oldFactory: T[] = []
  const other: T[] = []
  for (const slot of slots) {
    if (normalizeSlotCode(slot.code).startsWith('老厂')) {
      oldFactory.push(slot)
    } else {
      other.push(slot)
    }
  }
  return [...oldFactory, ...other]
}

export const getSlotCapacity = (code: any) => {
  const normalized = normalizeSlotCode(code)
  if (isUnlimitedSlot(code)) {
    return UNLIMITED_SLOT_CAPACITY
  }
  if (largeCapacityPrefixes.some((prefix) => normalized.startsWith(prefix))) {
    return LARGE_SLOT_CAPACITY
  }
  if (scrapSlotPrefixes.some((prefix) => normalized.startsWith(prefix))) {
    return SCRAP_SLOT_CAPACITY
  }
  return SLOT_CAPACITY
}

const requiredSlotCodes = [
  ...Array.from({ length: 15 }, (_, idx) => `大机型区域 ${String(idx + 1).padStart(2, '0')}`),
  '闲置区 01',
  '闲置区 02',
  '实验室区 01',
  ...OLD_FACTORY_SLOT_CODES,
  ...EMERGENCY_BUFFER_SLOT_CODES,
  '报废区 01',
]

export const ensureRequiredSlots = (slots: WarehouseSlot[] = []): WarehouseSlot[] => {
  const existing: WarehouseSlot[] = []
  const existingCodes = new Set<string>()
  for (const slot of Array.isArray(slots) ? slots : []) {
    const code = canonicalSlotCode(slot.code)
    const normalized = normalizeSlotCode(code)
    if (!normalized || existingCodes.has(normalized)) continue
    existing.push({ ...slot, code })
    existingCodes.add(normalized)
  }
  const missingCodes = requiredSlotCodes.filter((code) => !existingCodes.has(normalizeSlotCode(code)))
  if (!missingCodes.length) return existing

  const maxBottom = existing.length
    ? Math.max(...existing.map((slot) => Number(slot.y || 0) + Number(slot.h || 160)))
    : 0
  const baseY = Math.max(20, maxBottom + 20)
  const width = 300
  const height = 160
  const gapX = 40
  const gapY = 40
  const cols = 5
  const requiredSlots = missingCodes.map((code, idx) => ({
    id: `required-slot-${normalizeSlotCode(code)}`,
    code,
    x: 20 + (idx % cols) * (width + gapX),
    y: baseY + Math.floor(idx / cols) * (height + gapY),
    w: width,
    h: height,
    status: '正常',
  }))
  return [...existing, ...requiredSlots]
}

export const defaultSlots = (): WarehouseSlot[] => ([
  { id: 'slot-1', code: 'A01', x: 20, y: 20, w: 140, h: 80 },
  { id: 'slot-2', code: 'A02', x: 190, y: 20, w: 140, h: 80 },
  { id: 'slot-3', code: 'B01', x: 20, y: 130, w: 140, h: 80 }
])

export const addSlot = (slots: WarehouseSlot[], code = ''): WarehouseSlot[] => {
  const next = slots.length + 1
  const slotCode = code || `S${String(next).padStart(2, '0')}`
  return [...slots, { id: `slot-${Date.now()}-${next}`, code: slotCode, x: 20, y: 20 + next * 20, w: 140, h: 80 }]
}

export const removeSlot = (slots: WarehouseSlot[], id: string): WarehouseSlot[] => {
  return slots.filter((slot) => slot.id !== id)
}

export const updateSlot = (slots: WarehouseSlot[], id: string, patch: Partial<WarehouseSlot>): WarehouseSlot[] => {
  return slots.map((slot) => (slot.id === id ? { ...slot, ...patch } : slot))
}

export const buildSlotStats = (inventory: any[], slots: WarehouseSlot[]): Record<string, SlotStat> => {
  const stats: Record<string, SlotStat> = {}
  slots.forEach((slot) => {
    const slotCode = canonicalSlotCode(slot.code)
    stats[slotCode] = { count: 0, capacity: getSlotCapacity(slotCode), latestInboundTime: '', isFull: false, isOverflow: false }
  })
  inventory.forEach((item) => {
    const slotCode = canonicalSlotCode(item.Location_Code)
    if (!slotCode || !stats[slotCode]) {
      return
    }
    stats[slotCode].count += 1
    const updateTime = String(item['更新时间'] || '')
    if (!stats[slotCode].latestInboundTime || updateTime > stats[slotCode].latestInboundTime) {
      stats[slotCode].latestInboundTime = updateTime
    }
  })
  Object.keys(stats).forEach((code) => {
    if (isUnlimitedSlot(code)) {
      stats[code].isFull = false
      stats[code].isOverflow = false
      return
    }
    stats[code].isFull = stats[code].count >= stats[code].capacity
    stats[code].isOverflow = stats[code].count > stats[code].capacity
  })
  return stats
}

export const persistLayoutToLocal = (layoutId: string, slots: WarehouseSlot[]) => {
  const key = `warehouse-layout:${layoutId}`
  const payload = JSON.stringify({ slots })
  localStorage.setItem(key, payload)
}

export const restoreLayoutFromLocal = (layoutId: string): WarehouseSlot[] => {
  const key = `warehouse-layout:${layoutId}`
  const raw = localStorage.getItem(key)
  if (!raw) {
    return []
  }
  try {
    const parsed = JSON.parse(raw)
    const list = Array.isArray(parsed?.slots) ? parsed.slots : []
    return list.map((slot: any) => ({
      id: String(slot.id || ''),
      code: String(slot.code || ''),
      x: Number(slot.x || 0),
      y: Number(slot.y || 0),
      w: Number(slot.w || 140),
      h: Number(slot.h || 80),
      ...(slot.status !== undefined ? { status: slot.status } : {}),
      ...(slot.allowed_models !== undefined ? { allowed_models: slot.allowed_models } : {}),
    })).filter((slot: WarehouseSlot) => slot.id && slot.code)
  } catch {
    return []
  }
}
