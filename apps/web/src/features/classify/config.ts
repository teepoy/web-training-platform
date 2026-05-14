/**
 * Classify Sidebar — Panel Configuration
 *
 * Architecture:
 *   Each panel in the sidebar is described by a `SidebarPanelDescriptor`.
 *   The descriptor carries a `component` key (resolved at render time via
 *   widgetRegistry.getWidgetComponent()), a human-readable `title`, and a
 *   flat `props` bag that controls the widget's behaviour.
 *
 * Agent operability:
 *   An agent (or a human) can add, remove, or reconfigure panels by editing
 *   the `defaultPanels` array below.  Each widget documents its accepted
 *   props in its own component directory.
 *
 * Extending:
 *   1. Create the .vue widget in `libs/web-ui/src/components/{name}/{Name}Widget.vue`.
 *   2. Create a widget descriptor in `libs/web-ui/src/components/{name}/index.ts`
 *      that imports the component and exports a `defineDashboardWidget({...})` descriptor.
 *   3. Export the descriptor from `@platform/web-ui` and register in `src/registrations/index.ts`.
 *   4. Add a descriptor entry to the desired panel preset below.
 */

import type { AgentPanelDescriptor } from "../../types";

// ---------------------------------------------------------------------------
// Descriptor shape
// ---------------------------------------------------------------------------

export interface SidebarPanelDescriptor {
  /** Unique identifier for this panel instance. */
  id: string;
  /** Key registered in widgetRegistry via registerWidget(). */
  component: string;
  /** Human-readable title shown in the panel header. */
  title: string;
  /**
   * Widget-specific props.  Flat key/value pairs — each widget documents
   * the props it accepts in its own component directory.
   */
  props: Record<string, unknown>;
  /** If true the panel starts collapsed. Default false. */
  collapsed?: boolean;
  /** Sort order (lower = higher in sidebar). Default 50. */
  order?: number;
  /** Panel size hint passed to agent widgets. */
  size?: "compact" | "normal" | "large";
  /** Whether this panel was injected by the agent. */
  _agentOwned?: boolean;
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
  const agentIds = new Set(agentPanels.map((p) => p.id));

  // Keep static panels that aren't overridden by agent
  const kept = staticPanels
    .filter((p) => !agentIds.has(p.id))
    .map((p, i) => ({ ...p, order: p.order ?? i * 10 }));

  // Convert agent panels to sidebar descriptors
  const converted: SidebarPanelDescriptor[] = agentPanels.map((ap) => ({
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
  }));

  return [...kept, ...converted].sort(
    (a, b) => (a.order ?? 50) - (b.order ?? 50),
  );
}

// ---------------------------------------------------------------------------
// Default panel layout — edit this array to change the sidebar
// ---------------------------------------------------------------------------

/**
 * Default panels shown in the classify sidebar.
 *
 * To add a new panel, append a descriptor here.  To hide one, remove it or
 * set `collapsed: true`.  Props are documented per-widget in its plugin dir.
 */
export const defaultPanels: SidebarPanelDescriptor[] = [
  {
    id: "annotation-progress",
    component: "annotation-progress",
    title: "Annotation Progress",
    props: {
      chartType: "donut",
      showCounts: true,
      showPercent: true,
      includeDrafts: true,
      showLabelBreakdown: true,
    },
  },
  {
    id: "label-distribution",
    component: "label-distribution",
    title: "Label Distribution",
    props: {
      orientation: "horizontal",
      showValues: true,
      maxBars: 20,
    },
  },
  {
    id: "wafer-map",
    component: "wafer-map",
    title: "Wafer Map",
    order: 15,
    size: "normal",
    props: {
      data: {
        inline: {
          points: [],
        },
      },
      config: {
        dataKey: "wafer-points",
        maxPoints: 100000,
      },
    },
  },
  {
    id: "selected-samples",
    component: "sample-viewer",
    title: "Selected Samples",
    order: 16,
    size: "normal",
    props: {
      data: {
        inline: {
          sampleIds: [],
          mode: "grid",
        },
      },
      config: {
        thumbSize: 88,
      },
    },
  },
  {
    id: "blink-table",
    component: "blink-table",
    title: "Blink Comparison",
    order: 17,
    size: "large",
    collapsed: true,
    props: {
      data: {
        inline: {
          rows: [],
          columns: [],
        },
      },
      config: {
        blinkIntervalMs: 1000,
        initialBlinkEnabled: true,
      },
    },
  },
];

// ---------------------------------------------------------------------------
// Dataset browser panel preset — filtering-only, no classify-only widgets
// ---------------------------------------------------------------------------

/**
 * Panels shown in the dataset browser sidebar.
 *
 * Excludes classify-only widgets (`annotation-progress`, `sample-viewer`,
 * `selected-samples`). The wafer map still emits browser-scoped selection and
 * filter intents so box selection can narrow the visible sample set without
 * enabling classify-only editing flows.
 */
export const datasetPanels: SidebarPanelDescriptor[] = [
  {
    id: "label-distribution",
    component: "label-distribution",
    title: "Label Distribution",
    props: {
      orientation: "horizontal",
      showValues: true,
      maxBars: 20,
    },
  },
  {
    id: "wafer-map",
    component: "wafer-map",
    title: "Wafer Map",
    order: 15,
    size: "normal",
    props: {
      data: {
        inline: {
          points: [],
        },
      },
      config: {
        dataKey: "wafer-points",
        maxPoints: 100000,
      },
    },
  },
  {
    id: "browser-summary",
    component: "browser-summary",
    title: "Browser Summary",
    order: 20,
    size: "compact",
    props: {},
  },
  {
    id: "blink-table",
    component: "blink-table",
    title: "Blink Comparison",
    order: 25,
    size: "large",
    collapsed: true,
    props: {
      data: {
        inline: {
          rows: [],
          columns: [],
        },
      },
      config: {
        blinkIntervalMs: 1000,
        initialBlinkEnabled: true,
      },
    },
  },
];

// ---------------------------------------------------------------------------
// Preview browser panel preset — session-scoped browser widgets
// ---------------------------------------------------------------------------

/**
 * Panels shown in the preview browser sidebar.
 *
 * Preview uses session-loaded wafer points inline, so it ships the wafer-map
 * widget directly instead of the dataset browser scatter preset.
 */
export const previewPanels: SidebarPanelDescriptor[] = [
  {
    id: "label-distribution",
    component: "label-distribution",
    title: "Label Distribution",
    props: {
      orientation: "horizontal",
      showValues: true,
      maxBars: 20,
    },
  },
  {
    id: "wafer-map",
    component: "wafer-map",
    title: "Wafer Map",
    order: 15,
    size: "normal",
    props: {
      data: {
        inline: {
          points: [],
        },
      },
      config: {
        maxPoints: 100000,
      },
    },
  },
  {
    id: "browser-summary",
    component: "browser-summary",
    title: "Browser Summary",
    order: 20,
    size: "compact",
    props: {},
  },
];
