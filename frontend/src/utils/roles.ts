export const normalizeRole = (role?: string | null) => {
  const raw = String(role || '').trim()
  if (!raw) return ''
  const lower = raw.toLowerCase()
  if (lower === 'admin' || raw === '管理员') return 'Admin'
  if (lower === 'boss' || raw === '老板') return 'Boss'
  if (lower === 'sales' || raw === '销售员') return 'Sales'
  if (lower === 'prod' || raw === '生产员') return 'Prod'
  if (lower === 'inbound' || raw === '入库员') return 'Inbound'
  return raw
}

export const roleIn = (role: string | null | undefined, roles?: string[]) => {
  if (!roles || roles.length === 0) return true
  const r = normalizeRole(role)
  return roles.map((x) => normalizeRole(x)).includes(r)
}
