import type { FormItemRule } from 'element-plus'

type Trigger = 'blur' | 'change'

export const requiredRule = (label: string, trigger: Trigger = 'blur'): FormItemRule => ({
  required: true,
  message: `请输入${label}`,
  trigger,
})

export const requiredSelectRule = (label: string): FormItemRule => ({
  required: true,
  message: `请选择${label}`,
  trigger: 'change',
})

export const hasText = (v: unknown) => String(v ?? '').trim().length > 0

export const isPositiveInteger = (v: unknown) => {
  const n = Number(v)
  return Number.isInteger(n) && n > 0
}
