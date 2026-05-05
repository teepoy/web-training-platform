import { defineStore } from 'pinia'

const LAYOUT_KEY = 'sample_browser.layout'
const THUMB_SIZE_KEY = 'sample_browser.thumb_size'
const SIDEBAR_COLLAPSED_KEY = 'sample_browser.sidebar_collapsed'

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

export const useSampleBrowserPrefs = defineStore('sampleBrowserPrefs', {
  state: () => ({
    layout: getStoredLayout() as 'grid' | 'list',
    thumbSize: getStoredThumbSize() as number,
    sidebarCollapsed: getStoredSidebarCollapsed() as boolean,
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
  },
})
