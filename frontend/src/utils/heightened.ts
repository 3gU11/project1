/**
 * 加高判定（统一口径），与后端 utils/heightened.py 保持一致。
 *
 * 备注里既有转合同追加的独立标记，也有说明文字：经销商订单的订单备注
 * （如「400G加高100mm 配单滤水箱」）会被云端复制到每一行，转合同时再逐行写进合同备注。
 * 只看「加高」两个字会把整单所有机型都误判成加高。
 *
 * 加高只认三种信号：
 *   1. 机型名自带「(加高)」/「（加高）」；
 *   2. 转合同时单独追加的「加高」标记（前后是空格）；
 *   3. 不在说明分段里的纯文本备注（历史数据，如「加高500MM」）。
 */
const NOTE_SEGMENT_RE = /\[(?:总|备注|附加|改数)\][^\[]*/g
const HIGH_MARKER_TOKEN_RE = /(?<!\S)加高(?!\S)/

export const hasHighHint = (...values: unknown[]) => {
  for (const value of values) {
    const text = String(value ?? '')
    if (text.replace(NOTE_SEGMENT_RE, ' ').includes('加高')) return true
    if (HIGH_MARKER_TOKEN_RE.test(text)) return true
  }
  return false
}
