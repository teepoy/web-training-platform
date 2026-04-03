import { watch, type Ref } from 'vue'
import { useMessage } from 'naive-ui'
import type { ApiError } from '../types'

export function useApiError(error: Ref<unknown>) {
  const message = useMessage()
  watch(error, (err) => {
    if (!err) return
    const detail = (err as ApiError)?.detail ?? (err as Error)?.message ?? 'An unexpected error occurred'
    message.error(detail)
  })
}
