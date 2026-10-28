/**
 * 订单/合同行备注 → 机台「单行备注」（与后端 utils/order_notes.py 同口径）。
 *
 * 优先级：[备注] 原备注 → [附加] 附加备注 → 加高标记 / [改数] 改数量；
 * 整单备注 [总] 不属于单行备注；换行与连续空白统一压成单个空格。
 */
const SEGMENT_RE = /\[(总|备注|附加|改数)\]([^[]*)/g
const HIGH_MARKER_RE = /(?:^|\s)加高(?=\s|$)/

const flatten = (value: unknown) => String(value ?? '').replace(/\s+/g, ' ').trim()

export const singleLineOrderRemark = (value?: unknown): string => {
  const raw = flatten(value)
  if (!raw) return ''

  const segments: Record<string, string> = {}
  for (const match of raw.matchAll(SEGMENT_RE)) {
    const key = match[1]
    const content = flatten(match[2])
    if (content && !segments[key]) segments[key] = content
  }

  if (segments['备注']) return segments['备注']
  if (segments['附加']) return segments['附加']

  const markers: string[] = []
  // 与后端/加高口径一致：转合同追加的「加高」是前后带空格的独立标记。
  if (HIGH_MARKER_RE.test(raw)) markers.push('加高')
  const changeQty = segments['改数'] || ''
  if (/^\d+$/.test(changeQty) && Number(changeQty) > 0) markers.push(`改数${changeQty}`)
  if (markers.length > 0) return markers.join(' ')

  return flatten(raw.replace(SEGMENT_RE, ' '))
}
