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

  it('persists sidebar width to localStorage', () => {
    const store = useSampleBrowserPrefs()

    store.setSidebarWidth(312)

    expect(localStorage.getItem('sample_browser.sidebar_width')).toBe('312')
  })

  it('uses default values when localStorage is empty', () => {
    const store = useSampleBrowserPrefs()

    expect(store.layout).toBe('grid')
    expect(store.thumbSize).toBe(128)
    expect(store.sidebarCollapsed).toBe(false)
    expect(store.sidebarWidth).toBe(280)
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
    firstStore.setSidebarWidth(336)

    // Fresh Pinia — state is re-read from localStorage
    setActivePinia(createPinia())
    const secondStore = useSampleBrowserPrefs()

    expect(secondStore.layout).toBe('list')
    expect(secondStore.thumbSize).toBe(192)
    expect(secondStore.sidebarCollapsed).toBe(true)
    expect(secondStore.sidebarWidth).toBe(336)
  })

  it('hydrates a valid stored sidebar width', () => {
    localStorage.setItem('sample_browser.sidebar_width', '344')

    const store = useSampleBrowserPrefs()

    expect(store.sidebarWidth).toBe(344)
  })

  it('clamps an over-max stored sidebar width', () => {
    localStorage.setItem('sample_browser.sidebar_width', '999')

    const store = useSampleBrowserPrefs()

    expect(store.sidebarWidth).toBe(520)
    expect(localStorage.getItem('sample_browser.sidebar_width')).toBe('520')
  })

  it('clamps an under-min stored sidebar width', () => {
    localStorage.setItem('sample_browser.sidebar_width', '120')

    const store = useSampleBrowserPrefs()

    expect(store.sidebarWidth).toBe(200)
    expect(localStorage.getItem('sample_browser.sidebar_width')).toBe('200')
  })

  it.each(['missing', 'null', 'undefined'])('falls back to default for %s stored sidebar width', (value) => {
    if (value === 'missing') {
      localStorage.removeItem('sample_browser.sidebar_width')
    } else {
      localStorage.setItem('sample_browser.sidebar_width', value)
    }

    const store = useSampleBrowserPrefs()

    expect(store.sidebarWidth).toBe(280)
    expect(localStorage.getItem('sample_browser.sidebar_width')).toBeNull()
  })

  it.each(['NaN', 'abc'])('falls back to default for non-numeric sidebar width %s', (value) => {
    localStorage.setItem('sample_browser.sidebar_width', value)

    const store = useSampleBrowserPrefs()

    expect(store.sidebarWidth).toBe(280)
    expect(localStorage.getItem('sample_browser.sidebar_width')).toBeNull()
  })

  it('collapse does not change sidebar width', () => {
    const store = useSampleBrowserPrefs()

    store.setSidebarWidth(304)
    store.setSidebarCollapsed(true)

    expect(store.sidebarWidth).toBe(304)
  })

  it('retains sidebar width after collapse then expand', () => {
    const store = useSampleBrowserPrefs()

    store.setSidebarWidth(352)
    store.setSidebarCollapsed(true)
    store.setSidebarCollapsed(false)

    expect(store.sidebarWidth).toBe(352)
  })
})
