import type { Ref } from 'vue'
import { ElMessage } from 'element-plus'
import { getApiErrorMessage } from '../utils/request'

type SubmitOptions<T> = {
  successMessage?: string
  errorMessage?: string
  onSuccess?: (result: T) => void | Promise<void>
  onError?: (error: any) => void | Promise<void>
  rethrow?: boolean
}

export const useFormSubmit = () => {
  const submitWithLock = async <T>(
    loadingRef: Ref<boolean>,
    task: () => Promise<T>,
    options: SubmitOptions<T> = {}
  ): Promise<T | undefined> => {
    if (loadingRef.value) return
    loadingRef.value = true
    try {
      const result = await task()
      if (options.successMessage) ElMessage.success(options.successMessage)
      if (options.onSuccess) await options.onSuccess(result)
      return result
    } catch (err: any) {
      const msg = getApiErrorMessage(err) || options.errorMessage || '操作失败'
      ElMessage.error(msg)
      if (options.onError) await options.onError(err)
      if (options.rethrow) throw err
      return
    } finally {
      loadingRef.value = false
    }
  }

  return { submitWithLock }
}
