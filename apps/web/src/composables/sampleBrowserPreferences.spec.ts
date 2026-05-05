import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { useSampleBrowserPrefs } from '../stores/sampleBrowser'

// vitest runs in Node — stub localStorage with an in-memory implementation
function createLocalStorageMock() {
  const store: Record<string, string> = {}
  return {
    getItem: (key: string): string | null => store[key] ?? null,
    setItem: (key: string, val: string) => {
      store[key] = val
    },
    removeItem: (key: string) => {
      delete store[key]
    },
    clear: () => {
      Object.keys(store).forEach((k) => {
        delete store[k]
      })
    },
    get length() {
      return Object.keys(store).length
    },
    key: (idx: number): string | null => Object.keys(store)[idx] ?? null,
  }
}

describe('sampleBrowserPreferences', () => {
  beforeEach(() => {
    vi.stubGlobal('localStorage', createLocalStorageMock())
    setActivePinia(createPinia())
  })

  it('persists layout to localStorage', () => {
    const store = useSampleBrowserPrefs()

    store.setLayout('list')

    expect(localStorage.getItem('sample_browser.layout')).toBe('list')
  })

  it('persists thumb size to localStorage', () => {
    const store = useSampleBrowserPrefs()

    store.setThumbSize(200)

    expect(localStorage.getItem('sample_browser.thumb_size')).toBe('200')
  })

  it('persists sidebar collapse state to localStorage', () => {
    const store = useSampleBrowserPrefs()

    store.setSidebarCollapsed(true)

    expect(localStorage.getItem('sample_browser.sidebar_collapsed')).toBe('true')
  })

  it('uses default values when localStorage is empty', () => {
    const store = useSampleBrowserPrefs()

    expect(store.layout).toBe('grid')
    expect(store.thumbSize).toBe(128)
    expect(store.sidebarCollapsed).toBe(false)
  })

  it('does not include filter, selection, or cursor state', () => {
    const store = useSampleBrowserPrefs()
    const keys = Object.keys(store.$state)

    expect(keys).not.toContain('filter')
    expect(keys).not.toContain('selection')
    expect(keys).not.toContain('cursor')
  })

  it('hydrates new store instances from localStorage', () => {
    const firstStore = useSampleBrowserPrefs()

    firstStore.setLayout('list')
    firstStore.setThumbSize(192)
    firstStore.setSidebarCollapsed(true)

    // Fresh Pinia — state is re-read from localStorage
    setActivePinia(createPinia())
    const secondStore = useSampleBrowserPrefs()

    expect(secondStore.layout).toBe('list')
    expect(secondStore.thumbSize).toBe(192)
    expect(secondStore.sidebarCollapsed).toBe(true)
  })
})
