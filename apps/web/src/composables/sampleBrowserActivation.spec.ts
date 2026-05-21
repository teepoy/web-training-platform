import { describe, it, expect, vi } from 'vitest'
import { handleBrowserActivation } from '../shared/index'

describe('sampleBrowserActivation', () => {
  it('open mode — plain click calls onOpen', () => {
    const callbacks = { onOpen: vi.fn(), onSelect: vi.fn() }
    handleBrowserActivation('open', 'id-1', { ctrlKey: false, metaKey: false }, callbacks)
    expect(callbacks.onOpen).toHaveBeenCalledWith('id-1')
    expect(callbacks.onSelect).not.toHaveBeenCalled()
  })

  it('open mode — ctrl+click still calls onOpen', () => {
    const callbacks = { onOpen: vi.fn(), onSelect: vi.fn() }
    handleBrowserActivation('open', 'id-2', { ctrlKey: true, metaKey: false }, callbacks)
    expect(callbacks.onOpen).toHaveBeenCalledWith('id-2')
    expect(callbacks.onSelect).not.toHaveBeenCalled()
  })

  it('select mode — plain click calls onSelect with multi=false', () => {
    const callbacks = { onOpen: vi.fn(), onSelect: vi.fn() }
    handleBrowserActivation('select', 'id-3', { ctrlKey: false, metaKey: false }, callbacks)
    expect(callbacks.onSelect).toHaveBeenCalledWith('id-3', false)
    expect(callbacks.onOpen).not.toHaveBeenCalled()
  })

  it('select mode — ctrl+click calls onSelect with multi=true', () => {
    const callbacks = { onOpen: vi.fn(), onSelect: vi.fn() }
    handleBrowserActivation('select', 'id-4', { ctrlKey: true, metaKey: false }, callbacks)
    expect(callbacks.onSelect).toHaveBeenCalledWith('id-4', true)
    expect(callbacks.onOpen).not.toHaveBeenCalled()
  })

  it('select mode — meta+click calls onSelect with multi=true', () => {
    const callbacks = { onOpen: vi.fn(), onSelect: vi.fn() }
    handleBrowserActivation('select', 'id-5', { ctrlKey: false, metaKey: true }, callbacks)
    expect(callbacks.onSelect).toHaveBeenCalledWith('id-5', true)
    expect(callbacks.onOpen).not.toHaveBeenCalled()
  })
})
