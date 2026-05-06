import { describe, it, expect } from 'vitest'
import { defaultPanels, datasetPanels, previewPanels } from './sidebarConfig'

describe('sidebarConfig panel presets', () => {
  describe('defaultPanels (classify)', () => {
    it('contains a wafer-map panel', () => {
      const components = defaultPanels.map((p) => p.component)
      expect(components).toContain('wafer-map')
    })

    it('does NOT contain an interactive-scatter panel', () => {
      const components = defaultPanels.map((p) => p.component)
      expect(components).not.toContain('interactive-scatter')
    })
  })

  describe('datasetPanels', () => {
    it('contains a wafer-map panel', () => {
      const components = datasetPanels.map((p) => p.component)
      expect(components).toContain('wafer-map')
    })

    it('does NOT contain an interactive-scatter panel', () => {
      const components = datasetPanels.map((p) => p.component)
      expect(components).not.toContain('interactive-scatter')
    })
  })

  describe('previewPanels', () => {
    it('contains a wafer-map panel', () => {
      const components = previewPanels.map((p) => p.component)
      expect(components).toContain('wafer-map')
    })

    it('does NOT contain an interactive-scatter panel', () => {
      const components = previewPanels.map((p) => p.component)
      expect(components).not.toContain('interactive-scatter')
    })
  })
})
