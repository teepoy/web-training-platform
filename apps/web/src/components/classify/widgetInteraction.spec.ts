import { describe, expect, it } from 'vitest'
import { reduceLabelFilterIntent, type SidebarWidgetIntent } from './widgetContract'

describe('sidebar widget interaction reducer', () => {
  it('replaces the active label filter on replace intents', () => {
    const intent: SidebarWidgetIntent = {
      type: 'select-labels',
      operation: 'replace',
      values: ['rose'],
      sourcePanelId: 'label-distribution',
    }

    expect(reduceLabelFilterIntent(null, intent)).toBe('rose')
  })

  it('clears the active label filter when the same label is toggled', () => {
    const intent: SidebarWidgetIntent = {
      type: 'select-labels',
      operation: 'toggle',
      values: ['rose'],
      sourcePanelId: 'label-distribution',
    }

    expect(reduceLabelFilterIntent('rose', intent)).toBe(null)
  })

  it('switches the active label filter when a different label is toggled', () => {
    const intent: SidebarWidgetIntent = {
      type: 'select-labels',
      operation: 'toggle',
      values: ['tulip'],
      sourcePanelId: 'label-distribution',
    }

    expect(reduceLabelFilterIntent('rose', intent)).toBe('tulip')
  })

  it('clears the active label filter on clear-selection intents', () => {
    const intent: SidebarWidgetIntent = {
      type: 'clear-selection',
      operation: 'clear',
      values: [],
      sourcePanelId: 'label-distribution',
    }

    expect(reduceLabelFilterIntent('rose', intent)).toBe(null)
  })
})