import { beforeEach, describe, expect, it, vi } from 'vitest'
import { ref, nextTick } from 'vue'
import { usePreviewLoader } from './usePreviewLoader'
import { listPreviewItems } from '@/shared/api/preview'

vi.mock('@/shared/api/preview', () => ({
  listPreviewItems: vi.fn(),
}))

describe('usePreviewLoader', () => {
  beforeEach(() => {
    vi.resetAllMocks()
  })

  it('loadMore accumulates items across pages', async () => {
    vi.mocked(listPreviewItems).mockResolvedValueOnce({
      items: [{ upstream_item_id: 'a', image_uris: ['/a.jpg'] }],
      estimated_total: 100,
      has_more: true,
      next_cursor: 'cursor1'
    } as any).mockResolvedValueOnce({
      items: [{ upstream_item_id: 'b', image_uris: ['/b.jpg'] }],
      estimated_total: 100,
      has_more: false,
      next_cursor: null
    } as any)

    const loader = usePreviewLoader({ sessionId: 'session1' })

    await loader.loadMore()
    expect(loader.items.value.length).toBe(1)
    expect(loader.items.value[0].upstream_item_id).toBe('a')
    expect(loader.hasMore.value).toBe(true)

    await loader.loadMore()
    expect(loader.items.value.length).toBe(2)
    expect(loader.items.value[1].upstream_item_id).toBe('b')
    expect(loader.hasMore.value).toBe(false)
  })

  it('loadMore deduplicates by upstream_item_id', async () => {
    vi.mocked(listPreviewItems).mockResolvedValue({
      items: [{ upstream_item_id: 'a', image_uris: ['/a.jpg'] }],
      estimated_total: 100,
      has_more: true,
      next_cursor: 'c1'
    } as any)

    const loader = usePreviewLoader({ sessionId: 'session1' })

    await loader.loadMore()
    expect(loader.items.value.length).toBe(1)

    // Load again with the same item, it should be deduplicated
    await loader.loadMore()
    expect(loader.items.value.length).toBe(1)
  })

  it('reset() clears items, cursor, hasMore, initialized', async () => {
    vi.mocked(listPreviewItems).mockResolvedValue({
      items: [{ upstream_item_id: 'a', image_uris: ['/a.jpg'] }],
      estimated_total: 100,
      has_more: true,
      next_cursor: 'c1'
    } as any)

    const loader = usePreviewLoader({ sessionId: 'session1' })
    await loader.loadMore()
    expect(loader.items.value.length).toBe(1)
    expect(loader.initialized.value).toBe(true)

    loader.reset()

    expect(loader.items.value.length).toBe(0)
    expect(loader.hasMore.value).toBe(true)
    expect(loader.initialized.value).toBe(false)
    expect(loader.estimatedTotal.value).toBeNull()
  })

  it('auto-resets when sessionId ref changes', async () => {
    vi.mocked(listPreviewItems).mockResolvedValueOnce({
      items: [{ upstream_item_id: 'a', image_uris: ['/a.jpg'] }],
      estimated_total: 100,
      has_more: true,
      next_cursor: 'c1'
    } as any).mockResolvedValueOnce({
      items: [],
      estimated_total: 0,
      has_more: false,
      next_cursor: null
    } as any)

    const sessionId = ref('session1')
    const loader = usePreviewLoader({ sessionId })

    await loader.loadMore()
    expect(loader.items.value.length).toBe(1)

    // Change sessionId
    sessionId.value = 'session2'
    await nextTick()
    await new Promise(r => setTimeout(r, 0))

    expect(loader.items.value.length).toBe(0)
    expect(listPreviewItems).toHaveBeenCalledTimes(2)
    expect(listPreviewItems).toHaveBeenLastCalledWith('session2', null, 20)
  })
})
