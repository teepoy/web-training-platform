import { describe, it, expect, vi, beforeEach } from 'vitest'
import { ref, nextTick } from 'vue'
import { usePreviewLoader } from './usePreviewLoader'
import * as api from '../api'

vi.mock('../api', () => ({
  listPreviewItems: vi.fn()
}))

describe('usePreviewLoader', () => {
  beforeEach(() => {
    vi.resetAllMocks()
  })

  it('Cursor pagination — calling loadMore advances cursor', async () => {
    const listSpy = vi.mocked(api.listPreviewItems)
    
    listSpy.mockResolvedValueOnce({
      items: [
        { upstream_item_id: 'item-1', image_uris: [], metadata: {} },
        { upstream_item_id: 'item-2', image_uris: [], metadata: {} }
      ],
      next_cursor: 'cursor-page-2',
      has_more: true,
      estimated_total: 50
    })

    const loader = usePreviewLoader({ sessionId: 'test-session', pageSize: 2 })
    await loader.loadMore()
    
    expect(listSpy).toHaveBeenCalledWith('test-session', null, 2)
    expect(loader.items.value).toHaveLength(2)
    expect(loader.hasMore.value).toBe(true)

    listSpy.mockResolvedValueOnce({
      items: [
        { upstream_item_id: 'item-3', image_uris: [], metadata: {} }
      ],
      next_cursor: 'cursor-page-3',
      has_more: false,
      estimated_total: 50
    })

    await loader.loadMore()
    
    expect(listSpy).toHaveBeenCalledWith('test-session', 'cursor-page-2', 2)
    expect(loader.items.value).toHaveLength(3)
    expect(loader.hasMore.value).toBe(false)
  })

  it('Dedupe — duplicate upstream_item_ids are not added twice', async () => {
    const listSpy = vi.mocked(api.listPreviewItems)
    
    listSpy.mockResolvedValueOnce({
      items: [
        { upstream_item_id: 'item-1', image_uris: [], metadata: {} },
        { upstream_item_id: 'item-2', image_uris: [], metadata: {} }
      ],
      next_cursor: 'cursor-2',
      has_more: true,
      estimated_total: 50
    })

    const loader = usePreviewLoader({ sessionId: 'test-session', pageSize: 2 })
    await loader.loadMore()
    
    listSpy.mockResolvedValueOnce({
      items: [
        { upstream_item_id: 'item-2', image_uris: [], metadata: {} },
        { upstream_item_id: 'item-3', image_uris: [], metadata: {} }
      ],
      next_cursor: 'cursor-3',
      has_more: false,
      estimated_total: 50
    })

    await loader.loadMore()
    
    expect(loader.items.value).toHaveLength(3)
    const ids = loader.items.value.map(i => i.upstream_item_id)
    expect(ids).toEqual(['item-1', 'item-2', 'item-3'])
  })

  it('Reset — changing sessionId resets items and cursor', async () => {
    const listSpy = vi.mocked(api.listPreviewItems)
    
    listSpy.mockResolvedValue({
      items: [
        { upstream_item_id: 'item-1', image_uris: [], metadata: {} }
      ],
      next_cursor: 'cursor-2',
      has_more: true,
      estimated_total: 50
    })

    const sessionIdRef = ref('session-A')
    const loader = usePreviewLoader({ sessionId: sessionIdRef, pageSize: 2 })
    await loader.loadMore()
    
    expect(loader.items.value).toHaveLength(1)
    
    loader.reset()
    
    expect(loader.items.value).toHaveLength(0)
    await nextTick()
    expect(listSpy).toHaveBeenLastCalledWith('session-A', null, 2)
  })
})