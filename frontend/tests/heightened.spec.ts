import { describe, expect, it } from 'vitest'
import { hasHighHint } from '../src/utils/heightened'

// 云端把订单备注复制到每一行：[总]/[备注] 分段里都带着「400G加高100mm」
const SHARED_NOTE = '[总]400G加高100mm 配单滤水箱 加装割铝装置 [备注]400G加高100mm 配单滤水箱 加装割铝装置'
// 真正的加高行会由转合同单独追加一个「加高」标记（前后空格）
const HIGH_NOTE = '[总]400G加高100mm 配单滤水箱 加装割铝装置 加高 [备注]400G加高100mm 配单滤水箱 加装割铝装置'

describe('hasHighHint 加高判定', () => {
  it('备注说明分段里的「400G加高100mm」不算加高', () => {
    expect(hasHighHint('FH-300C', 'FINISHED-STOCK', SHARED_NOTE)).toBe(false)
    expect(hasHighHint('FR-400AUTO', SHARED_NOTE)).toBe(false)
  })

  it('机型自带 (加高)、单独追加的「加高」标记算加高', () => {
    expect(hasHighHint('FR-400G(加高)')).toBe(true)
    expect(hasHighHint('FR-400G', HIGH_NOTE)).toBe(true)
  })

  it('不在分段里的纯文本备注（历史数据）仍然算加高', () => {
    expect(hasHighHint('备注', '加高500MM')).toBe(true)
    expect(hasHighHint('批次 加高')).toBe(true)
  })
})
