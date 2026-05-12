/**
 * @platform/widget-sdk — Dashboard widget contracts
 *
 * A dashboard widget is a self-contained Vue component + descriptor object.
 * The component must accept the props defined in DashboardWidgetProps.
 * Everything else is widget-specific and documented by the widget author.
 *
 * Design note: TypeScript cannot statically enforce Vue SFC props types across
 * package boundaries. The contract is enforced by:
 *   1. The descriptor `contract.acceptsProps` declaration (human + agent readable)
 *   2. The template in `templates/DashboardWidgetTemplate.vue` showing the expected pattern
 *   3. Runtime: BrowserSidebar passes props by name; missing props are undefined
 */

import type { Component, InjectionKey } from "vue";

// ---------------------------------------------------------------------------
// Context injection key
// ---------------------------------------------------------------------------

/** Injection key for the shared dashboard context Record passed by BrowserSidebar */
export const BROWSER_DASHBOARD_KEY: InjectionKey<Record<string, unknown>> =
  Symbol("browserDashboard");

// ---------------------------------------------------------------------------
// Widget descriptor
// ---------------------------------------------------------------------------

export interface SidebarWidgetCapability {
  /**
   * Context keys this widget reads via inject().
   * Declare accurately — used by agents to decide which surfaces to show the widget on.
   */
  reads: string[];
  /** Intent types this widget may dispatch via the interaction context. */
  emits: string[];
}

export interface SidebarWidgetSelfTestScenario {
  name: string;
  objective: string;
  steps: string[];
  expected: string[];
}

export interface WidgetContract {
  displayName: string;
  description: string;
  /** Names of props the panel descriptor's `props` bag may set. */
  acceptsProps: string[];
  capabilities: SidebarWidgetCapability;
  selfTests: SidebarWidgetSelfTestScenario[];
}

export interface DashboardWidgetDescriptor {
  /**
   * Unique string key used in panel descriptors' `component` field.
   * Convention: kebab-case, e.g. "my-heatmap"
   */
  key: string;
  /** Lazy or eager Vue component. Must accept DashboardWidgetProps. */
  component: Component;
  contract: WidgetContract;
}

// ---------------------------------------------------------------------------
// Props that every dashboard widget component must accept
// ---------------------------------------------------------------------------

/**
 * Every dashboard widget component must declare these props with defineProps<>.
 * They are passed by BrowserSidebar and carry the panel's static configuration.
 *
 * Usage in your .vue file:
 *   const props = withDefaults(defineProps<DashboardWidgetProps & MyOwnProps>(), { ... })
 */
export interface DashboardWidgetProps {
  /**
   * Arbitrary data payload.  Convention:
   *   props.data.inline.* — data inlined into the panel descriptor by the view
   *   props.data.*        — other data shapes (agent-supplied, etc.)
   */
  data?: Record<string, unknown>;
  /**
   * Widget behavioural configuration (e.g. interaction.collection, maxPoints).
   * Shape is widget-specific and documented in the widget's contract.acceptsProps.
   */
  config?: Record<string, unknown>;
  /** Size hint: controls how much vertical space the panel requests. */
  size?: "compact" | "normal" | "large";
}

// ---------------------------------------------------------------------------
// Helper
// ---------------------------------------------------------------------------

/**
 * Validates and returns the descriptor (provides a typed creation point).
 * Throws in development if required fields are missing.
 */
export function defineDashboardWidget(
  descriptor: DashboardWidgetDescriptor,
): DashboardWidgetDescriptor {
  if (!descriptor.key || descriptor.key.trim() === "") {
    throw new Error("[widget-sdk] defineDashboardWidget: key must not be empty");
  }
  if (!descriptor.component) {
    throw new Error(
      `[widget-sdk] defineDashboardWidget(${descriptor.key}): component must be provided`,
    );
  }
  if (!descriptor.contract.displayName) {
    throw new Error(
      `[widget-sdk] defineDashboardWidget(${descriptor.key}): contract.displayName must not be empty`,
    );
  }
  return descriptor;
}
