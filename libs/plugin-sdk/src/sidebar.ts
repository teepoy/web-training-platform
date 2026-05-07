/**
 * @platform/plugin-sdk — Sidebar widget plugin contracts
 *
 * A sidebar plugin is a self-contained Vue component + descriptor object.
 * The component must accept the props defined in SidebarPluginRequiredProps.
 * Everything else is widget-specific and documented by the plugin author.
 *
 * Bidirectional communication:
 *   - App → Widget: via `context` (injected under BROWSER_DASHBOARD_KEY) and
 *     `interactionState` (injected under SIDEBAR_WIDGET_INTERACTION_KEY)
 *   - Widget → App: via `dispatch(SidebarWidgetIntent)` from the interaction context
 *
 * Design note: TypeScript cannot statically enforce Vue SFC props types across
 * package boundaries. The contract is enforced by:
 *   1. The descriptor `contract.acceptsProps` declaration (human + agent readable)
 *   2. The template in `templates/SidebarPluginTemplate.vue` showing the expected pattern
 *   3. Runtime: BrowserSidebar passes props by name; missing props are undefined
 */

import type { Component, InjectionKey, ComputedRef } from "vue";

// ---------------------------------------------------------------------------
// Context injection keys (re-exported so plugins don't import from app code)
// ---------------------------------------------------------------------------

/** Injection key for the shared dashboard context Record passed by BrowserSidebar */
export const BROWSER_DASHBOARD_KEY: InjectionKey<Record<string, unknown>> =
  Symbol("browserDashboard");

/** Injection key for the bidirectional interaction context */
export const SIDEBAR_WIDGET_INTERACTION_KEY: InjectionKey<
  ComputedRef<SidebarWidgetInteractionContext>
> = Symbol("sidebarWidgetInteraction");

// ---------------------------------------------------------------------------
// Interaction system (bidirectional)
// ---------------------------------------------------------------------------

export type SidebarWidgetContextKey =
  | "classify-dashboard"
  | "interaction-state"
  | "prediction-grid-items"
  | "browser-dashboard"
  | "browser-items";

export type SidebarWidgetIntentType =
  | "select-samples"
  | "select-labels"
  | "select-predictions"
  | "apply-filter"
  | "clear-selection"
  | "focus-item";

export type SidebarWidgetOperation =
  | "replace"
  | "add"
  | "remove"
  | "toggle"
  | "clear";

export type SidebarWidgetCollectionEntity = "sample" | "prediction" | "row";
export type SidebarWidgetSource = "scatter" | "table" | "grid" | "external";
export type SidebarWidgetIntentTarget = "selection" | "filter" | "both";
export type SidebarWidgetFilterMode = "all" | "selected-only";

export interface SidebarWidgetIntentMetadata {
  collection?: string;
  entity?: SidebarWidgetCollectionEntity;
  sourceWidget?: SidebarWidgetSource;
  target?: SidebarWidgetIntentTarget;
  filterMode?: SidebarWidgetFilterMode;
  revision?: number;
  [key: string]: unknown;
}

export interface SidebarWidgetIntent {
  type: SidebarWidgetIntentType;
  operation: SidebarWidgetOperation;
  values: string[];
  sourcePanelId?: string;
  metadata?: SidebarWidgetIntentMetadata;
}

export interface SidebarWidgetCollectionSelectionState {
  ids: string[];
  sourcePanelId: string | null;
  revision: number;
}

export interface SidebarWidgetCollectionFilterState {
  ids: string[];
  mode: SidebarWidgetFilterMode;
  sourcePanelId: string | null;
  revision: number;
}

export interface SidebarWidgetCollectionState {
  entity: SidebarWidgetCollectionEntity;
  selection: SidebarWidgetCollectionSelectionState;
  filter: SidebarWidgetCollectionFilterState;
}

export interface SidebarWidgetInteractionState {
  activeLabelFilter: string | null;
  selectedLabels: string[];
  collections?: Record<string, SidebarWidgetCollectionState>;
}

export interface SidebarWidgetInteractionConfig {
  collection: string;
  entity: SidebarWidgetCollectionEntity;
  emitSelection?: boolean;
  followSelection?: boolean;
  filterFromSelection?: boolean;
  clearFilterOnEmptySelection?: boolean;
}

export interface SidebarWidgetInteractionContext {
  state: SidebarWidgetInteractionState;
  dispatch: (intent: SidebarWidgetIntent) => void;
}

// ---------------------------------------------------------------------------
// Plugin descriptor
// ---------------------------------------------------------------------------

export interface SidebarWidgetCapability {
  /**
   * Context keys this widget reads via inject().
   * Declare accurately — used by agents to decide which surfaces to show the widget on.
   */
  reads: SidebarWidgetContextKey[];
  /** Intent types this widget may dispatch via the interaction context. */
  emits: SidebarWidgetIntentType[];
}

export interface SidebarWidgetSelfTestScenario {
  name: string;
  objective: string;
  steps: string[];
  expected: string[];
}

export interface SidebarWidgetContract {
  displayName: string;
  description: string;
  /** Names of props the panel descriptor's `props` bag may set. */
  acceptsProps: string[];
  capabilities: SidebarWidgetCapability;
  selfTests: SidebarWidgetSelfTestScenario[];
}

export interface SidebarPluginDescriptor {
  /**
   * Unique string key used in panel descriptors' `component` field.
   * Convention: kebab-case, e.g. "my-heatmap"
   */
  key: string;
  /** Lazy or eager Vue component. Must accept SidebarPluginRequiredProps. */
  component: Component;
  contract: SidebarWidgetContract;
}

// ---------------------------------------------------------------------------
// Props that every sidebar plugin component must accept
// ---------------------------------------------------------------------------

/**
 * Every sidebar widget component must declare these props with defineProps<>.
 * They are passed by BrowserSidebar and carry the panel's static configuration.
 *
 * Usage in your .vue file:
 *   const props = withDefaults(defineProps<SidebarPluginRequiredProps & MyOwnProps>(), { ... })
 */
export interface SidebarPluginRequiredProps {
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
export function defineSidebarPlugin(
  descriptor: SidebarPluginDescriptor,
): SidebarPluginDescriptor {
  if (!descriptor.key || descriptor.key.trim() === "") {
    throw new Error("[plugin-sdk] defineSidebarPlugin: key must not be empty");
  }
  if (!descriptor.component) {
    throw new Error(
      `[plugin-sdk] defineSidebarPlugin(${descriptor.key}): component must be provided`,
    );
  }
  if (!descriptor.contract.displayName) {
    throw new Error(
      `[plugin-sdk] defineSidebarPlugin(${descriptor.key}): contract.displayName must not be empty`,
    );
  }
  return descriptor;
}

// ---------------------------------------------------------------------------
// Interaction reducers (shared logic, usable by both app and plugins)
// ---------------------------------------------------------------------------

export function reduceLabelFilterIntent(
  currentLabelFilter: string | null,
  intent: SidebarWidgetIntent,
): string | null {
  if (intent.type === "clear-selection" || intent.operation === "clear") {
    return null;
  }
  if (intent.type !== "select-labels" && intent.type !== "apply-filter") {
    return currentLabelFilter;
  }
  const nextLabel = intent.values[0] ?? null;
  if (!nextLabel) return null;
  if (intent.operation === "toggle") {
    return currentLabelFilter === nextLabel ? null : nextLabel;
  }
  if (intent.operation === "remove") {
    return currentLabelFilter === nextLabel ? null : currentLabelFilter;
  }
  if (intent.operation === "add" || intent.operation === "replace") {
    return nextLabel;
  }
  return currentLabelFilter;
}

function applyIdsOperation(
  currentIds: string[],
  values: string[],
  operation: SidebarWidgetOperation,
): string[] {
  const current = new Set(currentIds);
  const incoming = values.filter((v) => v.trim().length > 0);

  if (operation === "clear") return [];
  if (operation === "replace") return [...new Set(incoming)];
  if (operation === "add") {
    incoming.forEach((id) => current.add(id));
    return [...current];
  }
  if (operation === "remove") {
    incoming.forEach((id) => current.delete(id));
    return [...current];
  }
  if (operation === "toggle") {
    incoming.forEach((id) => {
      if (current.has(id)) current.delete(id);
      else current.add(id);
    });
    return [...current];
  }
  return currentIds;
}

function buildEmptyCollectionState(
  entity: SidebarWidgetCollectionEntity,
): SidebarWidgetCollectionState {
  return {
    entity,
    selection: { ids: [], sourcePanelId: null, revision: 0 },
    filter: { ids: [], mode: "all", sourcePanelId: null, revision: 0 },
  };
}

export function reduceCollectionIntent(
  collections: Record<string, SidebarWidgetCollectionState> | undefined,
  intent: SidebarWidgetIntent,
): Record<string, SidebarWidgetCollectionState> {
  const collectionKey = intent.metadata?.collection;
  if (!collectionKey) return collections ?? {};

  const current = collections ?? {};
  const entity: SidebarWidgetCollectionEntity =
    intent.metadata?.entity ?? "sample";
  const existing = current[collectionKey] ?? buildEmptyCollectionState(entity);
  const target = intent.metadata?.target ?? "selection";

  if (intent.type === "clear-selection" || intent.operation === "clear") {
    return {
      ...current,
      [collectionKey]: buildEmptyCollectionState(entity),
    };
  }

  let nextSelection = existing.selection;
  let nextFilter = existing.filter;

  if (target === "selection" || target === "both") {
    nextSelection = {
      ids: applyIdsOperation(existing.selection.ids, intent.values, intent.operation),
      sourcePanelId: intent.sourcePanelId ?? null,
      revision: existing.selection.revision + 1,
    };
  }

  if (target === "filter" || target === "both") {
    const filterMode =
      intent.metadata?.filterMode ??
      (intent.values.length > 0 ? "selected-only" : "all");
    nextFilter = {
      ids: applyIdsOperation(existing.filter.ids, intent.values, intent.operation),
      mode: filterMode,
      sourcePanelId: intent.sourcePanelId ?? null,
      revision: existing.filter.revision + 1,
    };
  }

  return {
    ...current,
    [collectionKey]: { entity, selection: nextSelection, filter: nextFilter },
  };
}
