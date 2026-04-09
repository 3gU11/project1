import { defineStore } from 'pinia'
import { ref } from 'vue'

type CacheEntry = {
  expiresAt: number
  value: unknown
  touchedAt: number
}

export const useCacheStore = defineStore('cache', () => {
  const bucket = ref<Record<string, CacheEntry>>({})
  const MAX_ENTRIES = 120
  const now = () => Date.now()

  const pruneExpired = () => {
    const ts = now()
    for (const [key, entry] of Object.entries(bucket.value)) {
      if (ts > entry.expiresAt) delete bucket.value[key]
    }
  }

  const ensureCapacity = () => {
    const keys = Object.keys(bucket.value)
    if (keys.length <= MAX_ENTRIES) return
    const overflow = keys.length - MAX_ENTRIES
    const victims = keys
      .map((key) => ({ key, touchedAt: bucket.value[key]?.touchedAt || 0 }))
      .sort((a, b) => a.touchedAt - b.touchedAt)
      .slice(0, overflow)
    for (const v of victims) delete bucket.value[v.key]
  }

  const get = <T = unknown>(key: string): T | null => {
    pruneExpired()
    const entry = bucket.value[key]
    if (!entry) return null
    entry.touchedAt = now()
    return entry.value as T
  }

  const set = <T = unknown>(key: string, value: T, ttlMs = 15_000) => {
    const ts = now()
    bucket.value[key] = {
      value,
      expiresAt: ts + Math.max(0, ttlMs),
      touchedAt: ts,
    }
    pruneExpired()
    ensureCapacity()
  }

  const remove = (key: string) => {
    delete bucket.value[key]
  }

  const clear = () => {
    bucket.value = {}
  }

  return { get, set, remove, clear }
})
