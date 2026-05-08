export const SANDBOX_CATEGORIES = ['小机G', '小机XS', '大机XS', '小机AUTO', '大机AUTO', '特殊'] as const
export type SandboxCategory = typeof SANDBOX_CATEGORIES[number]

export function normalizeMajorFamily(value: string) {
  const v = String(value || '').trim()
  if (!v) return ''
  if (v.includes('特殊')) return 'SPECIAL'
  if (v.includes('AUTO') || v.includes('大机AUTO') || v.includes('小机AUTO')) return 'AUTO'
  if (v.includes('XS') || v.includes('大机XS') || v.includes('小机XS') || v.includes('小机/XS')) return 'XS'
  if (v.includes('G') || v.includes('小机G')) return 'G'
  return ''
}

export function categoryOfModel(modelType: string, modelFamily?: string): SandboxCategory | '' {
  const raw = String(modelFamily || modelType || '').trim()
  if (!raw) return ''
  if (raw.includes('特殊')) return '特殊'
  if (raw.includes('小机G')) return '小机G'
  if (raw.includes('大机XS')) return '大机XS'
  if (raw.includes('小机XS') || raw.includes('小机/XS')) return '小机XS'
  if (raw.includes('大机AUTO')) return '大机AUTO'
  if (raw.includes('小机AUTO')) return '小机AUTO'
  const upper = raw.toUpperCase()
  if (upper === 'FH-300C') return '小机G'
  if (upper.includes('AUTO')) return upper.includes('8055') || upper.includes('7055') ? '大机AUTO' : '小机AUTO'
  if (upper.includes('XS')) return upper.includes('8055') || upper.includes('7055') ? '大机XS' : '小机XS'
  if (upper === 'G' || upper.endsWith('G')) return '小机G'
  return ''
}
