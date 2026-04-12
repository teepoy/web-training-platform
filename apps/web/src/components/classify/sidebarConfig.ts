/**
 * Classify Sidebar — Widget Registry & Configuration
 *
 * Architecture:
 *   Each panel in the sidebar is described by a `SidebarPanelDescriptor`.
 *   The descriptor carries a `component` key (resolved to a Vue component at
 *   render time), a human-readable `title`, and a flat `props` bag that
 *   controls the widget's behaviour.
 *
 * Agent operability:
 *   An agent (or a human) can add, remove, or reconfigure panels by editing
 *   the `defaultPanels` array below.  Each widget documents its accepted
 *   props inline so plain-language instructions like "hide the percentage
 *   ring" translate to `showPercent: false`.
 *
 * Extending:
 *   1. Create a new `.vue` widget in `./widgets/`.
 *   2. Register its component key in `WIDGET_COMPONENTS` below.
 *   3. Add a descriptor entry to `defaultPanels`.
 */

import { defineAsyncComponent, type Component } from 'vue'
import type { AgentPanelDescriptor } from '../../types'

// ---------------------------------------------------------------------------
// Descriptor shape
// ---------------------------------------------------------------------------

export interface SidebarPanelDescriptor {
  /** Unique identifier for this panel instance. */
  id: string
  /** Key into the WIDGET_COMPONENTS map. */
  component: string
  /** Human-readable title shown in the panel header. */
  title: string
  /**
   * Widget-specific props.  Flat key/value pairs — each widget documents
   * the props it accepts in its own file header.
   */
  props: Record<string, unknown>
  /** If true the panel starts collapsed. Default false. */
  collapsed?: boolean
  /** Sort order (lower = higher in sidebar). Default 50. */
  order?: number
  /** Panel size hint passed to agent widgets. */
  size?: 'compact' | 'normal' | 'large'
  /** Whether this panel was injected by the agent. */
  _agentOwned?: boolean
}

// ---------------------------------------------------------------------------
// Component registry — maps `component` keys to lazy Vue components
// ---------------------------------------------------------------------------

export const WIDGET_COMPONENTS: Record<string, Component> = {
  'annotation-progress': defineAsyncComponent(
    () => import('./widgets/AnnotationProgressWidget.vue'),
  ),
  'label-distribution': defineAsyncComponent(
    () => import('./widgets/LabelDistributionWidget.vue'),
  ),
  // Agent-provided generic widgets
  'echarts-generic': defineAsyncComponent(
    () => import('./widgets/GenericEChartsWidget.vue'),
  ),
  'markdown-log': defineAsyncComponent(
    () => import('./widgets/MarkdownLogWidget.vue'),
  ),
  'data-table': defineAsyncComponent(
    () => import('./widgets/DataTableWidget.vue'),
  ),
  'metric-cards': defineAsyncComponent(
    () => import('./widgets/MetricCardsWidget.vue'),
  ),
  'sample-viewer': defineAsyncComponent(
    () => import('./widgets/SampleViewerWidget.vue'),
  ),
  'prediction-summary': defineAsyncComponent(
    () => import('./widgets/PredictionSummaryWidget.vue'),
  ),
}

// ---------------------------------------------------------------------------
// Merge static panels with agent-controlled panels
// ---------------------------------------------------------------------------

/**
 * Merge the default (static) panels with agent-controlled panels.
 *
 * Static panels always appear first at their original order.
 * Agent panels are appended after, sorted by their `order` field.
 * If an agent panel has the same `id` as a static panel, the agent
 * version replaces the static one.
 */
export function mergePanels(
  staticPanels: SidebarPanelDescriptor[],
  agentPanels: readonly AgentPanelDescriptor[],
): SidebarPanelDescriptor[] {
  const agentIds = new Set(agentPanels.map(p => p.id))

  // Keep static panels that aren't overridden by agent
  const kept = staticPanels
    .filter(p => !agentIds.has(p.id))
    .map((p, i) => ({ ...p, order: p.order ?? i * 10 }))

  // Convert agent panels to sidebar descriptors
  const converted: SidebarPanelDescriptor[] = agentPanels.map(ap => ({
    id: ap.id,
    component: ap.component,
    title: ap.title,
    props: {
      data: ap.data,
      config: ap.config,
      size: ap.size,
    },
    collapsed: ap.collapsed,
    order: ap.order,
    size: ap.size,
    _agentOwned: true,
  }))

  return [...kept, ...converted].sort((a, b) => (a.order ?? 50) - (b.order ?? 50))
}

// ---------------------------------------------------------------------------
// Default panel layout — edit this array to change the sidebar
// ---------------------------------------------------------------------------

/**
 * Default panels shown in the classify sidebar.
 *
 * To add a new panel, append a descriptor here.  To hide one, remove it or
 * set `collapsed: true`.  Props are documented per-widget.
 */
export const defaultPanels: SidebarPanelDescriptor[] = [
  {
    id: 'annotation-progress',
    component: 'annotation-progress',
    title: 'Annotation Progress',
    props: {
      /** 'donut' | 'bar' — chart visualisation style */
      chartType: 'donut',
      /** Show absolute sample counts beside the chart */
      showCounts: true,
      /** Show percentage text in the centre of the donut */
      showPercent: true,
      /** Merge local draft count into the chart as a separate slice */
      includeDrafts: true,
      /** Show per-label breakdown table below the chart */
      showLabelBreakdown: true,
    },
  },
  {
    id: 'label-distribution',
    component: 'label-distribution',
    title: 'Label Distribution',
    props: {
      /** 'horizontal' | 'vertical' — bar direction */
      orientation: 'horizontal',
      /** Show count labels on each bar */
      showValues: true,
      /** Max labels to show before grouping remainder as "Other" */
      maxBars: 20,
    },
  },
]
