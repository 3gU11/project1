import { describe, expect, it } from 'vitest'
import { resolveDealerOrderRowNotes } from '../src/utils/dealerOrderItems'

// 真实订单 DO17942853598375658F9：3 条明细，仅第 3 行有附加备注；
// 订单级 extra_remark 由后端 _summarize_text 汇总成同一文本（云端桥接时等于首行值）。
// 列表行不能把订单级汇总备注回退到每一行，否则多机型订单备注串行。
const ORDER_EXTRA_REMARK = '配:3mm导管·适用数量1'

const rowNotes = (
  order: { remark?: string; extra_remark?: string; items?: Array<Record<string, unknown>> },
  index: number,
) => {
  const items = order.items || []
  return resolveDealerOrderRowNotes(items.length, items[index], order)
}

describe('resolveDealerOrderRowNotes 列表行备注', () => {
  it('多明细订单不把订单级汇总备注回退到每一行', () => {
    const order = {
      remark: '整单原备注',
      extra_remark: ORDER_EXTRA_REMARK,
      items: [
        { line_no: 1, model: 'FH-300C', quantity: 1 },
        { line_no: 2, model: 'FR-400G', quantity: 2 },
      ],
    }

    expect(rowNotes(order, 0)).toEqual({ remark: '', extra_remark: '' })
    expect(rowNotes(order, 1)).toEqual({ remark: '', extra_remark: '' })
  })

  it('多明细订单仅第 3 行显示行级附加备注，其余行保持为空', () => {
    const order = {
      // 桥接订单级值 = 首行明细值
      remark: '首行原备注',
      extra_remark: ORDER_EXTRA_REMARK,
      items: [
        { line_no: 10019, model: 'FH-300C', quantity: 1, remark: '首行原备注', extra_remark: ORDER_EXTRA_REMARK },
        { line_no: 10020, model: 'FR-400G', quantity: 2 },
        {
          line_no: 10021,
          model: 'FR-400AUTO',
          quantity: 1,
          remark: '第三行原备注',
          extra_remark: ORDER_EXTRA_REMARK,
        },
      ],
    }

    expect(rowNotes(order, 0)).toEqual({ remark: '首行原备注', extra_remark: ORDER_EXTRA_REMARK })
    expect(rowNotes(order, 1)).toEqual({ remark: '', extra_remark: '' })
    expect(rowNotes(order, 2)).toEqual({ remark: '第三行原备注', extra_remark: ORDER_EXTRA_REMARK })
  })

  it('单明细订单保留订单级兜底（兼容旧接口）', () => {
    const order = {
      remark: '整单原备注',
      extra_remark: ORDER_EXTRA_REMARK,
      items: [{ line_no: 1, model: 'FR-400G', quantity: 2 }],
    }

    expect(rowNotes(order, 0)).toEqual({ remark: '整单原备注', extra_remark: ORDER_EXTRA_REMARK })
  })

  it('无明细订单保留订单级兜底', () => {
    const order = { remark: '整单原备注', extra_remark: ORDER_EXTRA_REMARK }

    expect(resolveDealerOrderRowNotes(0, undefined, order)).toEqual({
      remark: '整单原备注',
      extra_remark: ORDER_EXTRA_REMARK,
    })
  })

  it('行级备注优先于订单级兜底', () => {
    const order = {
      remark: '整单原备注',
      extra_remark: ORDER_EXTRA_REMARK,
      items: [{ line_no: 1, model: 'FR-400G', quantity: 1, remark: '行级原备注' }],
    }

    expect(rowNotes(order, 0)).toEqual({ remark: '行级原备注', extra_remark: ORDER_EXTRA_REMARK })
  })
})
