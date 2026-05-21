import { defineStore } from 'pinia'

const LAYOUT_KEY = 'sample_browser.layout'
const THUMB_SIZE_KEY = 'sample_browser.thumb_size'
const SIDEBAR_COLLAPSED_KEY = 'sample_browser.sidebar_collapsed'
const SIDEBAR_WIDTH_KEY = 'sample_browser.sidebar_width'

export const DEFAULT_SIDEBAR_WIDTH = 280
export const MIN_SIDEBAR_WIDTH = 200
export const MAX_SIDEBAR_WIDTH = 520
export const COLLAPSED_SIDEBAR_WIDTH = 36

function getStoredLayout(): 'grid' | 'list' {
  const stored = localStorage.getItem(LAYOUT_KEY)
  return stored === 'list' ? 'list' : 'grid'
}

function getStoredThumbSize(): number {
  const stored = localStorage.getItem(THUMB_SIZE_KEY)
  if (!stored) {
    return 128
  }

  const parsed = Number(stored)
  if (Number.isFinite(parsed)) {
    return parsed
  }

  localStorage.removeItem(THUMB_SIZE_KEY)
  return 128
}

function getStoredSidebarCollapsed(): boolean {
  return localStorage.getItem(SIDEBAR_COLLAPSED_KEY) === 'true'
}

function clampSidebarWidth(width: number): number {
  return Math.min(MAX_SIDEBAR_WIDTH, Math.max(MIN_SIDEBAR_WIDTH, width))
}

function getStoredSidebarWidth(): number {
  const stored = localStorage.getItem(SIDEBAR_WIDTH_KEY)
  if (stored === null || stored === '' || stored === 'null' || stored === 'undefined') {
    localStorage.removeItem(SIDEBAR_WIDTH_KEY)
    return DEFAULT_SIDEBAR_WIDTH
  }

  const parsed = Number(stored)
  if (!Number.isFinite(parsed)) {
    localStorage.removeItem(SIDEBAR_WIDTH_KEY)
    return DEFAULT_SIDEBAR_WIDTH
  }

  const clamped = clampSidebarWidth(parsed)
  if (clamped !== parsed) {
    localStorage.setItem(SIDEBAR_WIDTH_KEY, String(clamped))
  }

  return clamped
}

export const useSampleBrowserPrefs = defineStore('sampleBrowserPrefs', {
  state: () => ({
    layout: getStoredLayout() as 'grid' | 'list',
    thumbSize: getStoredThumbSize() as number,
    sidebarCollapsed: getStoredSidebarCollapsed() as boolean,
    sidebarWidth: getStoredSidebarWidth() as number,
  }),
  actions: {
    setLayout(v: 'grid' | 'list') {
      this.layout = v
      localStorage.setItem(LAYOUT_KEY, v)
    },
    setThumbSize(v: number) {
      this.thumbSize = v
      localStorage.setItem(THUMB_SIZE_KEY, String(v))
    },
    setSidebarCollapsed(v: boolean) {
      this.sidebarCollapsed = v
      localStorage.setItem(SIDEBAR_COLLAPSED_KEY, String(v))
    },
    setSidebarWidth(width: number) {
      const clamped = clampSidebarWidth(width)
      this.sidebarWidth = clamped
      localStorage.setItem(SIDEBAR_WIDTH_KEY, String(clamped))
    },
  },
})
