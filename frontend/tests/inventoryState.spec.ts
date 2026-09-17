import { describe, expect, it, vi } from 'vitest'

vi.mock('../src/utils/modelOrder', () => ({
  compareModels: (a: string, b: string) => a.localeCompare(b),
  isModelInDictionary: () => true,
}))

import { getInventoryLifecycleStatus, isContractLinked, isMachineBound, isOrderReserved } from '../src/utils/inventoryState'
import { buildModelInventorySummary } from '../src/utils/inventoryStats'

describe('inventory relationship states', () => {
  it('normalizes legacy bound status without losing relationship attributes', () => {
    const row = { 状态: '已绑定', 合同号: 'HT-1', 占用订单号: 'SO-1' }
    expect(getInventoryLifecycleStatus(row)).toBe('待入库')
    expect(isContractLinked(row)).toBe(true)
    expect(isOrderReserved(row)).toBe(true)
    expect(isMachineBound(row)).toBe(true)
  })

  it('counts contract linkage and order reservation independently', () => {
    const model = 'TEST-MODEL'
    const rows = [
      { 机型: model, 状态: '待入库', 合同号: 'HT-1', 占用订单号: '' },
      { 机型: model, 状态: '待入库', 合同号: '', 占用订单号: 'SO-1' },
    ]
    const summary = buildModelInventorySummary(rows)[0]
    expect(summary.待入库).toBe(2)
    expect(summary.已绑定).toBe(2)
  })
})
