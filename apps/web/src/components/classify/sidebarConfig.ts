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
import {
  defineSidebarWidget,
  type SidebarWidgetDefinition,
} from './widgetContract'

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

export const SIDEBAR_WIDGETS: Record<string, SidebarWidgetDefinition> = {
  'annotation-progress': defineSidebarWidget({
    key: 'annotation-progress',
    component: defineAsyncComponent(
      () => import('./widgets/AnnotationProgressWidget.vue'),
    ),
    contract: {
      displayName: 'Annotation Progress',
      description: 'Shows annotation totals, drafts, selected counts, and label breakdowns.',
      acceptsProps: ['chartType', 'showCounts', 'showPercent', 'includeDrafts', 'showLabelBreakdown'],
      capabilities: {
        reads: ['classify-dashboard'],
        emits: [],
      },
      selfTests: [
        {
          name: 'renders dashboard metrics',
          objective: 'Verify the widget renders shared dashboard stats and selection counts.',
          steps: [
            'Provide annotation stats with non-zero totals and selectedCount in the shared context.',
            'Render the widget with showCounts enabled.',
          ],
          expected: [
            'Metric values are visible for annotated, remaining, total, and selected counts when present.',
            'The widget renders without requiring agent-only data.',
          ],
        },
      ],
    },
  }),
  'label-distribution': defineSidebarWidget({
    key: 'label-distribution',
    component: defineAsyncComponent(
      () => import('./widgets/LabelDistributionWidget.vue'),
    ),
    contract: {
      displayName: 'Label Distribution',
      description: 'Displays label counts and now supports click-to-filter behavior for the classify surface.',
      acceptsProps: ['orientation', 'showValues', 'maxBars'],
      capabilities: {
        reads: ['classify-dashboard', 'interaction-state'],
        emits: ['select-labels', 'clear-selection'],
      },
      selfTests: [
        {
          name: 'renders sorted labels',
          objective: 'Verify label counts render and overflow labels can be grouped.',
          steps: [
            'Provide more labels than maxBars in the shared dashboard stats.',
            'Render the widget in horizontal orientation.',
          ],
          expected: [
            'The widget renders without errors.',
            'The chart can group remaining labels into an Other bucket.',
          ],
        },
        {
          name: 'click to filter',
          objective: 'Verify a chart click can update the shared label filter state.',
          steps: [
            'Provide a shared interaction-state with no activeLabelFilter.',
            'Click a concrete label bar in the chart.',
          ],
          expected: [
            'The widget emits a select-labels intent through the shared interaction context.',
            'The active label is visually emphasized once the interaction state updates.',
          ],
        },
      ],
    },
  }),
  'echarts-generic': defineSidebarWidget({
    key: 'echarts-generic',
    component: defineAsyncComponent(
      () => import('./widgets/GenericEChartsWidget.vue'),
    ),
    contract: {
      displayName: 'Generic ECharts',
      description: 'Renders generic ECharts option payloads for static or agent-driven panels.',
      acceptsProps: ['data', 'config', 'size'],
      capabilities: {
        reads: [],
        emits: [],
      },
      selfTests: [
        {
          name: 'renders minimal chart payload',
          objective: 'Verify the widget accepts a minimal chart option payload.',
          steps: [
            'Render the widget with a minimal ECharts option object in panel data.',
          ],
          expected: [
            'The widget renders a chart container without contract validation failures.',
          ],
        },
      ],
    },
  }),
  'markdown-log': defineSidebarWidget({
    key: 'markdown-log',
    component: defineAsyncComponent(
      () => import('./widgets/MarkdownLogWidget.vue'),
    ),
    contract: {
      displayName: 'Markdown Log',
      description: 'Displays log entries or markdown updates in a scrollable widget.',
      acceptsProps: ['data', 'config', 'size'],
      capabilities: {
        reads: [],
        emits: [],
      },
      selfTests: [
        {
          name: 'renders markdown rows',
          objective: 'Verify one or more markdown entries can be shown without layout errors.',
          steps: [
            'Render the widget with a small list of timestamped log entries.',
          ],
          expected: [
            'The widget renders log content without requiring extra shared context.',
          ],
        },
      ],
    },
  }),
  'data-table': defineSidebarWidget({
    key: 'data-table',
    component: defineAsyncComponent(
      () => import('./widgets/DataTableWidget.vue'),
    ),
    contract: {
      displayName: 'Data Table',
      description: 'Renders columns and rows from static or agent-supplied data.',
      acceptsProps: ['data', 'config', 'size'],
      capabilities: {
        reads: [],
        emits: [],
      },
      selfTests: [
        {
          name: 'renders a table row',
          objective: 'Verify the widget handles a minimal columns-and-rows payload.',
          steps: [
            'Render the widget with one column and one row.',
          ],
          expected: [
            'The first row is visible and the widget does not crash on a small dataset.',
          ],
        },
      ],
    },
  }),
  'metric-cards': defineSidebarWidget({
    key: 'metric-cards',
    component: defineAsyncComponent(
      () => import('./widgets/MetricCardsWidget.vue'),
    ),
    contract: {
      displayName: 'Metric Cards',
      description: 'Displays a compact grid of key metric values.',
      acceptsProps: ['data', 'config', 'size'],
      capabilities: {
        reads: [],
        emits: [],
      },
      selfTests: [
        {
          name: 'renders metric cards',
          objective: 'Verify metric labels and values appear for a minimal card set.',
          steps: [
            'Render the widget with at least one metric card payload.',
          ],
          expected: [
            'Metric labels and values are visible without requiring additional context.',
          ],
        },
      ],
    },
  }),
  'sample-viewer': defineSidebarWidget({
    key: 'sample-viewer',
    component: defineAsyncComponent(
      () => import('./widgets/SampleViewerWidget.vue'),
    ),
    contract: {
      displayName: 'Sample Viewer',
      description: 'Shows sample thumbnails or item previews inside the sidebar.',
      acceptsProps: ['data', 'config', 'size'],
      capabilities: {
        reads: ['classify-dashboard'],
        emits: [],
      },
      selfTests: [
        {
          name: 'renders a sample preview',
          objective: 'Verify at least one sample can be shown from panel data.',
          steps: [
            'Render the widget with one valid sample payload.',
          ],
          expected: [
            'A preview element is visible and the widget renders without extra agent wiring.',
          ],
        },
      ],
    },
  }),
  'prediction-summary': defineSidebarWidget({
    key: 'prediction-summary',
    component: defineAsyncComponent(
      () => import('./widgets/PredictionSummaryWidget.vue'),
    ),
    contract: {
      displayName: 'Prediction Summary',
      description: 'Summarizes totals, edited rows, accepted rows, and confidence in prediction review.',
      acceptsProps: [],
      capabilities: {
        reads: ['prediction-grid-items'],
        emits: [],
      },
      selfTests: [
        {
          name: 'renders review totals',
          objective: 'Verify accepted and edited counts reflect injected review grid items.',
          steps: [
            'Provide prediction-grid-items containing accepted and edited items.',
            'Render the widget without additional props.',
          ],
          expected: [
            'Total, Accepted, and Edited values are computed from injected grid items.',
          ],
        },
      ],
    },
  }),
}

export const WIDGET_COMPONENTS: Record<string, Component> = Object.fromEntries(
  Object.entries(SIDEBAR_WIDGETS).map(([key, definition]) => [key, definition.component as Component]),
)

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
