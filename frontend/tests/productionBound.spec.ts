import { expect, it } from 'vitest'
import { buildInventoryIndex, filterInventoryRows } from '../src/utils/inventoryFilter'
import { isProductionBound } from '../src/utils/inventoryState'

it('counts allocated production independently without inflating inventory totals', () => {
  const rows = [
    { 流水号: 'pending', 状态: '待入库', production_bound: 1 },
    { 流水号: 'allocated', 状态: '待发货', production_bound: 1 },
    { 流水号: 'completed', 状态: '待发货', production_bound: 0, 合同号: 'HT1' },
  ]
  const params = { selectedModels: [], statusFilter: '', searchQuery: '', highOnly: false }
  const index = buildInventoryIndex(rows)
  expect(filterInventoryRows(index, params).map(r => r.流水号)).toEqual(['pending'])
  expect(filterInventoryRows(index, { ...params, includeProductionBound: true })
    .filter(isProductionBound).map(r => r.流水号)).toEqual(['pending', 'allocated'])
})
