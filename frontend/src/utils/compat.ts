type IdleHandle = number
type IdleCb = () => void

export const runWhenIdle = (cb: IdleCb, fallbackDelayMs = 300): IdleHandle => {
  const w = window as any
  if (typeof w.requestIdleCallback === 'function') {
    return w.requestIdleCallback(cb)
  }
  return window.setTimeout(cb, fallbackDelayMs)
}

export const cancelIdleRun = (handle: IdleHandle | null | undefined) => {
  if (!handle && handle !== 0) return
  const w = window as any
  if (typeof w.cancelIdleCallback === 'function') {
    w.cancelIdleCallback(handle)
    return
  }
  window.clearTimeout(handle)
}

const pad2 = (n: number) => String(n).padStart(2, '0')
const toSafeDate = (value: Date | number | string) => {
  const d = value instanceof Date ? value : new Date(value)
  return Number.isNaN(d.getTime()) ? null : d
}

export const formatTimeHMS = (value: Date | number | string = new Date()) => {
  const d = toSafeDate(value)
  if (!d) return 'Unknown'
  return `${d.getFullYear()}-${pad2(d.getMonth() + 1)}-${pad2(d.getDate())}`
}

export const formatYearMonth = (value: Date | number | string, fallback = 'Unknown') => {
  const d = toSafeDate(value)
  if (!d) return fallback
  return `${d.getFullYear()}-${pad2(d.getMonth() + 1)}`
}

export const toTimestampSafe = (value: Date | number | string, fallback = 0) => {
  const d = toSafeDate(value)
  return d ? d.getTime() : fallback
}

export const fullscreenChangeEventNames = [
  'fullscreenchange',
  'webkitfullscreenchange',
  'mozfullscreenchange',
  'MSFullscreenChange',
] as const

export const getFullscreenElementCompat = () => {
  const doc = document as any
  return doc.fullscreenElement || doc.webkitFullscreenElement || doc.mozFullScreenElement || doc.msFullscreenElement || null
}

export const requestFullscreenCompat = async (node: HTMLElement) => {
  const el = node as any
  if (el.requestFullscreen) return el.requestFullscreen()
  if (el.webkitRequestFullscreen) return el.webkitRequestFullscreen()
  if (el.mozRequestFullScreen) return el.mozRequestFullScreen()
  if (el.msRequestFullscreen) return el.msRequestFullscreen()
  throw new Error('fullscreen not supported')
}

export const exitFullscreenCompat = async () => {
  const doc = document as any
  if (doc.exitFullscreen) return doc.exitFullscreen()
  if (doc.webkitExitFullscreen) return doc.webkitExitFullscreen()
  if (doc.mozCancelFullScreen) return doc.mozCancelFullScreen()
  if (doc.msExitFullscreen) return doc.msExitFullscreen()
  throw new Error('exit fullscreen not supported')
}
