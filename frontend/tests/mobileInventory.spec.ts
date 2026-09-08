import { describe, expect, it } from 'vitest'
import { mapLayoutSlots, prioritizeOldFactorySlots } from '../../frontend-mobile/src/utils/mapper'
import { summarizeBatchResults } from '../../frontend-mobile/src/utils/batchResults'
import { isInventorySyncMessage } from '../../frontend-mobile/src/utils/inventorySync'


describe('mobile inventory mapping', () => {
  it('uses server capacity metadata and supports unlimited slots', () => {
    const slots = mapLayoutSlots({
      layout_json: {
        slots: [
          { code: '大机型区域06', status: '正常', capacity: 15, unlimited: false },
          { code: '老厂一车间400', status: '正常', capacity: null, unlimited: true },
        ],
      },
    })

    expect(slots[0]).toMatchObject({ code: '大机型区域06', max: 15, unlimited: false })
    expect(slots[1]).toMatchObject({ code: '老厂一车间400', max: null, unlimited: true })
  })

  it('matches inventory counts across harmless slot-code whitespace', () => {
    const slots = mapLayoutSlots(
      { layout_json: { slots: [{ code: '大机型区域06', capacity: 15 }] } },
      [{ Location_Code: '大机型区域 06', 状态: '库存中（大机型区域 06）' }],
    )

    expect(slots[0].current).toBe(1)
  })

  it('does not invent slots when the server layout is empty', () => {
    expect(mapLayoutSlots({ layout_json: { slots: [] } })).toEqual([])
  })

  it('moves old factory slots to the front while preserving stable order', () => {
    const slots = mapLayoutSlots({
      layout_json: {
        slots: [
          { code: 'A01', capacity: 5 },
          { code: '老厂一车间400', unlimited: true },
          { code: 'B01', capacity: 5 },
          { code: '老厂临时库位', unlimited: true },
        ],
      },
    })

    expect(prioritizeOldFactorySlots(slots).map((slot) => slot.code)).toEqual([
      '老厂一车间400',
      '老厂临时库位',
      'A01',
      'B01',
    ])
  })
})


describe('mobile batch result summary', () => {
  it('retains failed serial numbers while reporting successful updates', () => {
    const summary = summarizeBatchResults(
      ['SN-1', 'SN-2', 'SN-3'],
      [
        { status: 'fulfilled', value: { ok: true } },
        { status: 'rejected', reason: new Error('库位已满') },
        { status: 'fulfilled', value: { ok: true } },
      ],
    )

    expect(summary.successCount).toBe(2)
    expect(summary.failedSerialNos).toEqual(['SN-2'])
    expect(summary.failureMessages).toEqual(['库位已满'])
  })
})


describe('mobile inventory synchronization', () => {
  it('recognizes inventory and warehouse layout broadcasts only', () => {
    expect(isInventorySyncMessage({ type: 'INVENTORY_UPDATE' })).toBe(true)
    expect(isInventorySyncMessage({ type: 'WAREHOUSE_LAYOUT_UPDATE' })).toBe(true)
    expect(isInventorySyncMessage({ event: 'dealer_orders_changed' })).toBe(false)
  })
})
