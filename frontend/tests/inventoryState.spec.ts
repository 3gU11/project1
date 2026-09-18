import { describe, expect, it, vi } from 'vitest'

vi.mock('../src/utils/modelOrder', () => ({
  compareModels: (a: string, b: string) => a.localeCompare(b),
  isModelInDictionary: () => true,
}))

import { getInventoryLifecycleStatus, isContractLinked, isMachineBound, isOrderReserved, isPendingInbound } from '../src/utils/inventoryState'
import { buildModelInventorySummary } from '../src/utils/inventoryStats'
import { buildInventoryIndex, filterInventoryRows } from '../src/utils/inventoryFilter'

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
      { 机型: model, 状态: '待入库', pending_inbound_scope: 'production', 合同号: 'HT-1', 占用订单号: '' },
      { 机型: model, 状态: '待入库', pending_inbound_scope: 'production', 合同号: '', 占用订单号: 'SO-1' },
    ]
    const summary = buildModelInventorySummary(rows)[0]
    expect(summary.待入库).toBe(2)
    expect(summary.已绑定).toBe(2)
  })

  it('includes review pending machines but excludes queued cards', () => {
    const rows = [
      { 流水号: 'active', 机型: 'M', 状态: '待入库', pending_inbound_scope: 'production' },
      { 流水号: 'queue', 机型: 'M', 状态: '待入库', pending_inbound_scope: 'queued' },
      { 流水号: 'done', 机型: 'M', 状态: '待入库', pending_inbound_scope: 'review' },
      { 流水号: 'stock', 机型: 'M', 状态: '库存中（D09）', pending_inbound_scope: '' },
      { 流水号: 'shipping', 机型: 'M', 状态: '待发货', pending_inbound_scope: '' },
    ]
    expect(rows.filter(isPendingInbound).map(r => r.流水号)).toEqual(['active', 'done'])
    expect(buildModelInventorySummary(rows)[0].待入库).toBe(2)
    const params = { selectedModels: [], statusFilter: '', searchQuery: '', highOnly: false }
    expect(filterInventoryRows(buildInventoryIndex(rows), params).map(r => r.流水号)).toEqual(['active', 'done', 'stock'])
    expect(filterInventoryRows(buildInventoryIndex(rows), { ...params, statusFilter: '待入库' }).map(r => r.流水号)).toEqual(['active', 'done'])
    expect(isPendingInbound({ 状态: '待入库' })).toBe(true)
  })
})
