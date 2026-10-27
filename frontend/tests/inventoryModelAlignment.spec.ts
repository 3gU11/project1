import { describe, expect, it } from 'vitest'
import { buildModelInventorySummary } from '../src/utils/inventoryStats'
import { normalizeModelName, setModelOrderList } from '../src/utils/modelOrder'

describe('机型严格对齐机型字典', () => {
  it('normalizeModelName 去掉半角/全角加高后缀', () => {
    expect(normalizeModelName('FR-400G(加高)')).toBe('FR-400G')
    expect(normalizeModelName('FR-400G（加高）')).toBe('FR-400G')
    expect(normalizeModelName('FR-400G')).toBe('FR-400G')
  })

  it('buildModelInventorySummary 把历史加高机型合并到字典基础机型，加高只进加高列', () => {
    setModelOrderList(['FR-400G', 'FH-300C'])

    const summary = buildModelInventorySummary([
      { 机型: 'FR-400G(加高)', 状态: '库存中', 批次号: 'B1', 合同备注: '' },
      { 机型: 'FR-400G', 状态: '库存中', 批次号: 'B2', 合同备注: '' },
      { 机型: 'FH-300C', 状态: '库存中', 批次号: 'B3', 合同备注: '' },
      { 机型: 'NOT-IN-DICT', 状态: '库存中', 批次号: 'B4', 合同备注: '' },
    ])

    const fr = summary.find((row) => row.机型 === 'FR-400G')
    expect(fr?.全部).toBe(2)
    expect(fr?.加高).toBe(1)
    expect(summary.some((row) => row.机型.includes('加高'))).toBe(false)
    // 不在机型字典里的机型不进统计表
    expect(summary.some((row) => row.机型 === 'NOT-IN-DICT')).toBe(false)
  })
})
