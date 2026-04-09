import { describe, it, expect } from 'vitest'
import { buildInventoryIndex, filterInventoryRows } from '../src/utils/inventoryFilter'

const makeRows = (count: number) => {
  const rows: any[] = []
  for (let i = 0; i < count; i += 1) {
    rows.push({
      流水号: `SN-${i}`,
      机型: i % 3 === 0 ? 'FH-260C(加高)' : 'FH-260C',
      批次号: `B-${Math.floor(i / 10)}`,
      客户: i % 2 === 0 ? 'A' : 'B',
      状态: i % 5 === 0 ? '待入库' : '库存中-1',
      '机台备注/配置': i % 7 === 0 ? '加高配置' : '',
      订单备注: '',
    })
  }
  return rows
}

describe('inventoryFilter performance', () => {
  it('filters 20k rows under 1s', () => {
    const rows = makeRows(20_000)
    const indexed = buildInventoryIndex(rows)
    const t0 = performance.now()
    const result = filterInventoryRows(indexed, {
      selectedModels: ['FH-260C(加高)'],
      statusFilter: '库存中',
      searchQuery: 'SN-1',
      highOnly: true,
    })
    const dt = performance.now() - t0
    expect(result.length).toBeGreaterThan(0)
    expect(dt).toBeLessThan(1000)
  })
})
