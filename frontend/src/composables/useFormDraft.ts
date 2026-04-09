import { onMounted, watch, type Ref } from 'vue'

type DraftOptions<T extends object> = {
  omitKeys?: string[]
  debounceMs?: number
  sanitize?: (value: T) => T
}

const clone = <T>(v: T): T => JSON.parse(JSON.stringify(v))

export const useRefFormDraft = <T extends object>(
  key: string,
  targetRef: Ref<T>,
  options: DraftOptions<T> = {},
) => {
  const storageKey = `form-draft:${key}`
  let timer: number | null = null
  const omit = new Set(options.omitKeys || [])

  onMounted(() => {
    const raw = localStorage.getItem(storageKey)
    if (!raw) return
    try {
      const parsed = JSON.parse(raw) as Partial<T>
      Object.assign(targetRef.value, parsed)
    } catch {
      localStorage.removeItem(storageKey)
    }
  })

  watch(
    targetRef,
    (val) => {
      if (timer) window.clearTimeout(timer)
      timer = window.setTimeout(() => {
        const data = clone(val)
        if (data && typeof data === 'object' && !Array.isArray(data)) {
          for (const k of omit) delete (data as any)[k]
        }
        const finalData = options.sanitize ? options.sanitize(data) : data
        localStorage.setItem(storageKey, JSON.stringify(finalData))
      }, options.debounceMs ?? 200)
    },
    { deep: true },
  )

  return {
    clearDraft() {
      localStorage.removeItem(storageKey)
    },
  }
}

export const useReactiveFormDraft = <T extends object>(
  key: string,
  target: T,
  options: DraftOptions<T> = {},
) => {
  const wrapper = { value: target } as Ref<T>
  return useRefFormDraft(key, wrapper, options)
}
