export const SANDBOX_CATEGORIES = ['中小型G', '中小型XS', '中大型XS', '中小型AUTO', '中大型AUTO', '特殊'] as const
export type SandboxCategory = typeof SANDBOX_CATEGORIES[number]

export function normalizeMajorFamily(value: string) {
  const v = normalizeSandboxCategory(String(value || '').trim())
  if (!v) return ''
  if (v.includes('特殊')) return 'SPECIAL'
  if (v.includes('AUTO') || v.includes('中大型AUTO') || v.includes('中小型AUTO')) return 'AUTO'
  if (v.includes('XS') || v.includes('中大型XS') || v.includes('中小型XS') || v.includes('中小型XS')) return 'XS'
  if (v.includes('G') || v.includes('中小型G')) return 'G'
  return ''
}

export function categoryOfModel(modelType: string, modelFamily?: string): SandboxCategory | '' {
  const dictFamily = normalizeSandboxCategory(String(modelFamily || '').trim())
  const raw = dictFamily && !['G', 'XS', 'AUTO'].includes(dictFamily.toUpperCase())
    ? dictFamily
    : String(modelType || '').trim()
  if (!raw) return ''
  if (raw.includes('特殊')) return '特殊'
  if (raw.includes('中小型G')) return '中小型G'
  if (raw.includes('中大型XS')) return '中大型XS'
  if (raw.includes('中小型XS') || raw.includes('中小型XS')) return '中小型XS'
  if (raw.includes('中大型AUTO')) return '中大型AUTO'
  if (raw.includes('中小型AUTO')) return '中小型AUTO'
  const upper = raw.toUpperCase()
  if (upper === 'FH-300C') return '中小型G'
  if (upper.includes('AUTO')) return upper.includes('8055') || upper.includes('7055') || upper.includes('8060') ? '中大型AUTO' : '中小型AUTO'
  if (upper.includes('XS')) return upper.includes('8055') || upper.includes('7055') || upper.includes('8060') ? '中大型XS' : '中小型XS'
  if (upper === 'G' || upper.endsWith('G')) return '中小型G'
  return ''
}

export function normalizeSandboxCategory(value: string) {
  const v = String(value || '').trim()
  const aliases: Record<string, SandboxCategory> = {
    小机G: '中小型G',
    小机XS: '中小型XS',
    '小机/XS': '中小型XS',
    小机AUTO: '中小型AUTO',
    大机XS: '中大型XS',
    大机AUTO: '中大型AUTO',
    SPECIAL: '特殊'
  }
  return aliases[v] || v
}
