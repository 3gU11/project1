export function normalizeModelType(raw: string): string {
  const upper = (raw || '').toUpperCase().trim()
  if (upper === 'FH-300C') return 'G'
  if (upper === 'SPECIAL' || upper === 'FT' || upper.startsWith('FR-1080') || upper.startsWith('FH-') || upper.startsWith('FL-') || upper.startsWith('FR-8060') || upper.startsWith('FR-8080') || upper.startsWith('FR-1100')) return 'SPECIAL'
  if (upper.includes('AUTO')) return 'AUTO'
  if (upper.includes('XS')) return 'XS'
  if (/FR-\d+G/.test(upper) || upper === 'G') return 'G'
  if (upper === 'XS' || upper === 'AUTO') return upper
  return raw
}

export const MODEL_COLORS: Record<string, string> = {
  G: '#4CAF50',
  XS: '#2196F3',
  AUTO: '#FF9800',
  SPECIAL: '#D81B60'
}

export const MODEL_LABELS: Record<string, string> = {
  G: 'G 系列',
  XS: 'XS 系列',
  AUTO: 'AUTO 系列'
}

export function formatDate(dateStr: string | null | undefined): string {
  if (!dateStr) return '-'
  return String(dateStr).slice(0, 10)
}
