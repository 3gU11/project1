import { describe, expect, it } from 'vitest'
import {
  isHeightenedDealerOrderLine,
  normalizeDealerOrderItems,
} from '../src/utils/dealerOrderItems'

// 云端在没有行备注时会把订单备注复制到每一行明细；这段备注里含「加高」。
const SHARED_ORDER_REMARK = '400G加高100mm 配单滤水箱 加装割铝装置'

describe('dealerOrderItems 加高判定', () => {
  it('订单备注被复制到每一行时，只有 inventory_type=heightened 的明细算加高', () => {
    const rows = normalizeDealerOrderItems({
      remark: SHARED_ORDER_REMARK,
      items: [
        { model: 'FH-300C', quantity: 3, inventory_type: 'finished', remark: SHARED_ORDER_REMARK },
        { model: 'FR-400G', quantity: 1, inventory_type: 'heightened', remark: SHARED_ORDER_REMARK },
        { model: 'FR-400AUTO', quantity: 1, inventory_type: 'finished', remark: SHARED_ORDER_REMARK },
        { model: 'FR-500XS(PRO)', quantity: 1, inventory_type: 'finished', remark: SHARED_ORDER_REMARK },
      ],
    })

    expect(rows.map((row) => row.high)).toEqual([false, true, false, false])
    expect(rows.map((row) => row.model)).toEqual(['FH-300C', 'FR-400G', 'FR-400AUTO', 'FR-500XS(PRO)'])
  })

  it('原备注/附加备注里的「加高」不参与判定，只看明细自己的字段', () => {
    expect(
      isHeightenedDealerOrderLine({
        model: 'FH-300C',
        inventory_type: 'finished',
        remark: SHARED_ORDER_REMARK,
        extra_remark: '加高100mm',
      }),
    ).toBe(false)
    expect(isHeightenedDealerOrderLine({ model: 'FH-300C(加高)' })).toBe(true)
    expect(isHeightenedDealerOrderLine({ model: 'FH-300C', inventory_type: 'Heightened' })).toBe(true)
  })

  it('订单没有明细时退化为单行，读订单自身的字段', () => {
    const rows = normalizeDealerOrderItems({
      model: 'FR-400G',
      quantity: 2,
      inventory_type: 'heightened',
      remark: SHARED_ORDER_REMARK,
      ERMQ: 1,
    })

    expect(rows).toHaveLength(1)
    expect(rows[0]).toMatchObject({ model: 'FR-400G', qty: 2, high: true, ermq: 1 })
    expect(rows[0].rowNote).toContain('[改数]1')
    expect(rows[0].rowNote).toContain('[备注]')
  })
})
