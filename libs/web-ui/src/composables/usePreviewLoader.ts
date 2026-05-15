import { ref, computed, watch, type Ref } from 'vue'
import { listPreviewItems, type PreviewItem } from '@platform/web-ui/api/preview'

export interface UsePreviewLoaderOptions {
  sessionId: string | Ref<string>
  pageSize?: number
}

export function usePreviewLoader(options: UsePreviewLoaderOptions) {
  const resolvedId = typeof options.sessionId === 'string'
    ? ref(options.sessionId)
    : options.sessionId
  const pageSize = options.pageSize ?? 20

  const items = ref<PreviewItem[]>([])
  const estimatedTotal = ref<number | null>(null)
  const isLoading = ref(false)
  const initialized = ref(false)
  const cursor = ref<string | null>(null)
  const hasMore = ref(true)

  const loadedCount = computed(() => items.value.length)

  async function loadMore() {
    if (!resolvedId.value) return
    if (initialized.value && !hasMore.value) return
    if (isLoading.value) return

    isLoading.value = true
    try {
      const page = await listPreviewItems(resolvedId.value, cursor.value, pageSize)
      estimatedTotal.value = page.estimated_total

      const newItems = page.items.filter(newItem =>
        !items.value.some(existing => existing.upstream_item_id === newItem.upstream_item_id)
      )

      items.value = [...items.value, ...newItems]
      cursor.value = page.next_cursor
      hasMore.value = page.has_more
      initialized.value = true
    } finally {
      isLoading.value = false
    }
  }

  function reset() {
    items.value = []
    estimatedTotal.value = null
    cursor.value = null
    hasMore.value = true
    initialized.value = false
    void loadMore()
  }

  watch(resolvedId, () => {
    reset()
  }, { immediate: false })

  return {
    items,
    estimatedTotal,
    loadedCount,
    isLoading,
    hasMore,
    initialized,
    loadMore,
    reset,
  }
}
