import { describe, expect, it, beforeEach } from 'vitest'
import {
  addSlot,
  buildSlotStats,
  defaultSlots,
  persistLayoutToLocal,
  removeSlot,
  restoreLayoutFromLocal,
  SLOT_CAPACITY
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

  it('persists and restores layout from localStorage', () => {
    const slots = [{ id: 's2', code: 'B01', x: 12, y: 15, w: 120, h: 80 }]
    persistLayoutToLocal('test-layout', slots)
    const restored = restoreLayoutFromLocal('test-layout')
    expect(restored).toEqual(slots)
  })
})
