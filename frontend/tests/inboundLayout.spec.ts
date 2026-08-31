import { describe, expect, it, beforeEach } from 'vitest'
import {
  addSlot,
  buildSlotStats,
  defaultSlots,
  ensureRequiredSlots,
  getSlotCapacity,
  OLD_FACTORY_SLOT_CODES,
  persistLayoutToLocal,
  prioritizeOldFactorySlots,
  removeSlot,
  restoreLayoutFromLocal,
  SLOT_CAPACITY,
  UNLIMITED_SLOT_CAPACITY
} from '../src/views/inboundLayout'

describe('inboundLayout helpers', () => {
  beforeEach(() => {
    localStorage.clear()
  })

  it('supports adding and removing slots', () => {
    let slots = defaultSlots()
    const originalLength = slots.length
    slots = addSlot(slots, 'C01')
    expect(slots).toHaveLength(originalLength + 1)
    const addedId = slots[slots.length - 1].id
    slots = removeSlot(slots, addedId)
    expect(slots).toHaveLength(originalLength)
  })

  it('marks full and overflow slot states correctly', () => {
    const slots = [{ id: 's1', code: 'A01', x: 0, y: 0, w: 100, h: 60 }]
    const inventory = Array.from({ length: SLOT_CAPACITY + 1 }).map((_, idx) => ({
      Location_Code: 'A01',
      更新时间: `2026-03-20 10:00:0${idx}`
    }))
    const stats = buildSlotStats(inventory, slots)
    expect(stats.A01.count).toBe(SLOT_CAPACITY + 1)
    expect(stats.A01.isFull).toBe(true)
    expect(stats.A01.isOverflow).toBe(true)
    expect(stats.A01.latestInboundTime).toBe('2026-03-20 10:00:05')
  })

  it('adds old factory slots with unlimited capacity', () => {
    const slots = ensureRequiredSlots(defaultSlots())
    const slotCodes = slots.map((slot) => slot.code)
    expect(slotCodes).toContain('老厂一车间400')
    expect(slotCodes).toContain('老厂一车间600')
    for (const code of OLD_FACTORY_SLOT_CODES) {
      expect(slotCodes).toContain(code)
      expect(getSlotCapacity(code)).toBe(UNLIMITED_SLOT_CAPACITY)
    }
  })

  it('includes old factory fourth workshop first floor 500 as unlimited', () => {
    const code = '老厂四车间一楼500'
    expect(OLD_FACTORY_SLOT_CODES).toContain(code)
    expect(getSlotCapacity(code)).toBe(UNLIMITED_SLOT_CAPACITY)
  })

  it('does not mark old factory slots full or overflow', () => {
    const oldFactoryCode = OLD_FACTORY_SLOT_CODES[0]
    const slots = [{ id: 'old-factory', code: oldFactoryCode, x: 0, y: 0, w: 100, h: 60 }]
    const inventory = Array.from({ length: SLOT_CAPACITY + 20 }).map((_, idx) => ({
      Location_Code: oldFactoryCode,
      更新时间: `2026-03-20 10:00:${String(idx).padStart(2, '0')}`
    }))
    const stats = buildSlotStats(inventory, slots)
    expect(stats[oldFactoryCode].count).toBe(SLOT_CAPACITY + 20)
    expect(stats[oldFactoryCode].capacity).toBe(UNLIMITED_SLOT_CAPACITY)
    expect(stats[oldFactoryCode].isFull).toBe(false)
    expect(stats[oldFactoryCode].isOverflow).toBe(false)
  })

  it('treats custom old factory slots as unlimited capacity', () => {
    const customOldFactoryCode = '老厂临时库位'
    const slots = [{ id: 'old-factory-custom', code: customOldFactoryCode, x: 0, y: 0, w: 100, h: 60 }]
    const inventory = Array.from({ length: SLOT_CAPACITY + 20 }).map((_, idx) => ({
      Location_Code: customOldFactoryCode,
      更新时间: `2026-03-20 10:00:${String(idx).padStart(2, '0')}`
    }))
    const stats = buildSlotStats(inventory, slots)
    expect(getSlotCapacity(customOldFactoryCode)).toBe(UNLIMITED_SLOT_CAPACITY)
    expect(stats[customOldFactoryCode].count).toBe(SLOT_CAPACITY + 20)
    expect(stats[customOldFactoryCode].isFull).toBe(false)
    expect(stats[customOldFactoryCode].isOverflow).toBe(false)
  })

  it('keeps old factory 400 and 600 as separate slots', () => {
    const restored = restoreLayoutFromLocal('empty-layout')
    expect(restored).toEqual([])

    persistLayoutToLocal('old-factory-layout', [
      { id: 'old-factory-400', code: '老厂一车间400', x: 0, y: 0, w: 100, h: 60 },
      { id: 'old-factory-600', code: '老厂一车间600', x: 120, y: 0, w: 100, h: 60 },
    ])
    const oldFactoryRestored = restoreLayoutFromLocal('old-factory-layout')
    const slotCodes = oldFactoryRestored.map((slot) => slot.code)
    expect(slotCodes).toContain('老厂一车间400')
    expect(slotCodes).toContain('老厂一车间600')

    const stats = buildSlotStats([
      { Location_Code: '老厂一车间400', 更新时间: '2026-03-20 10:00:00' },
      { Location_Code: '老厂一车间600', 更新时间: '2026-03-20 10:00:01' },
    ], oldFactoryRestored)
    expect(stats['老厂一车间400'].count).toBe(1)
    expect(stats['老厂一车间600'].count).toBe(1)
  })

  it('moves all old factory slots to the front without reordering other slots', () => {
    const slots = [
      { id: 'a', code: 'A01', x: 0, y: 0, w: 100, h: 60 },
      { id: 'old-400', code: '老厂一车间400', x: 0, y: 0, w: 100, h: 60 },
      { id: 'b', code: 'B01', x: 0, y: 0, w: 100, h: 60 },
      { id: 'old-temp', code: '老厂临时库位', x: 0, y: 0, w: 100, h: 60 },
    ]

    const prioritized = prioritizeOldFactorySlots(slots)

    expect(prioritized.map((slot) => slot.code)).toEqual([
      '老厂一车间400',
      '老厂临时库位',
      'A01',
      'B01',
    ])
    expect(slots[0].code).toBe('A01')
  })

  it('persists and restores layout from localStorage', () => {
    const slots = [{ id: 's2', code: 'B01', x: 12, y: 15, w: 120, h: 80 }]
    persistLayoutToLocal('test-layout', slots)
    const restored = restoreLayoutFromLocal('test-layout')
    expect(restored).toEqual(slots)
    expect(defaultSlots()).toHaveLength(3)
  })
})
