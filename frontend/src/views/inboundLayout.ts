export type WarehouseSlot = {
  id: string
  code: string
  x: number
  y: number
  w: number
  h: number
}

export type SlotStat = {
  count: number
  latestInboundTime: string
  isFull: boolean
  isOverflow: boolean
}

export const SLOT_CAPACITY = 5

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
    stats[slot.code] = { count: 0, latestInboundTime: '', isFull: false, isOverflow: false }
  })
  inventory.forEach((item) => {
    const slotCode = String(item.Location_Code || '').trim()
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
    stats[code].isFull = stats[code].count >= SLOT_CAPACITY
    stats[code].isOverflow = stats[code].count > SLOT_CAPACITY
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
      h: Number(slot.h || 80)
    })).filter((slot: WarehouseSlot) => slot.id && slot.code)
  } catch {
    return []
  }
}
