const MODEL_ORDER_CACHE_KEY = 'v7-model-dictionary-order'

const readCachedOrder = () => {
  try {
    if (typeof window === 'undefined') return [] as string[]
    const raw = window.localStorage.getItem(MODEL_ORDER_CACHE_KEY)
    if (!raw) return [] as string[]
    const parsed = JSON.parse(raw)
    return Array.isArray(parsed) ? parsed.map((item) => String(item || '').trim()).filter((item) => !!item) : []
  } catch {
    return [] as string[]
  }
}

let runtimeModelOrder: string[] = readCachedOrder()
let upperList: string[] = []
let noSpaceList: string[] = []
let noHyphenList: string[] = []

const rebuildOrderCache = () => {
  upperList = runtimeModelOrder.map((item) => item.toUpperCase())
  noSpaceList = runtimeModelOrder.map((item) => item.replace(/\s+/g, '').toUpperCase())
  noHyphenList = runtimeModelOrder.map((item) => item.replace(/-/g, '').toUpperCase())
}
rebuildOrderCache()

export const normalizeModelName = (model: unknown) => {
  return String(model || '').replace('(加高)', '').trim()
}

const isHighModel = (model: unknown) => String(model || '').includes('加高')

export const setModelOrderList = (models: string[]) => {
  const next = Array.from(new Set((models || []).map((m) => normalizeModelName(m)).filter((m) => !!m)))
  runtimeModelOrder = next
  try {
    if (typeof window !== 'undefined') {
      window.localStorage.setItem(MODEL_ORDER_CACHE_KEY, JSON.stringify(runtimeModelOrder))
    }
  } catch {}
  rebuildOrderCache()
}

export const getModelOrderList = () => [...runtimeModelOrder]

export const isModelInDictionary = (model: unknown) => {
  const clean = normalizeModelName(model)
  if (!clean) return false
  return runtimeModelOrder.includes(clean)
}

export const getModelOrderRank = (model: unknown) => {
  const cleanName = normalizeModelName(model)
  if (!cleanName) return 9999

  const direct = runtimeModelOrder.indexOf(cleanName)
  if (direct >= 0) return direct

  const upper = cleanName.toUpperCase()
  const upperIdx = upperList.indexOf(upper)
  if (upperIdx >= 0) return upperIdx

  const noSpace = cleanName.replace(/\s+/g, '').toUpperCase()
  const noSpaceIdx = noSpaceList.indexOf(noSpace)
  if (noSpaceIdx >= 0) return noSpaceIdx

  const noHyphen = cleanName.replace(/-/g, '').toUpperCase()
  const noHyphenIdx = noHyphenList.indexOf(noHyphen)
  if (noHyphenIdx >= 0) return noHyphenIdx

  return 9999
}

export const compareModels = (a: unknown, b: unknown) => {
  const rankA = getModelOrderRank(a)
  const rankB = getModelOrderRank(b)
  if (rankA !== rankB) return rankA - rankB

  const baseA = normalizeModelName(a)
  const baseB = normalizeModelName(b)
  if (baseA !== baseB) {
    return baseA.localeCompare(baseB, 'zh-CN', { numeric: true, sensitivity: 'base' })
  }

  const highA = isHighModel(a) ? 1 : 0
  const highB = isHighModel(b) ? 1 : 0
  if (highA !== highB) return highA - highB

  return String(a || '').localeCompare(String(b || ''), 'zh-CN', { numeric: true, sensitivity: 'base' })
}

export const sortModelStrings = (models: string[]) => {
  return [...models].sort(compareModels)
}

export const sortRowsByModel = <T>(rows: T[], getModel: (row: T) => unknown) => {
  return [...rows].sort((a, b) => compareModels(getModel(a), getModel(b)))
}
