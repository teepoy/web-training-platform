import type { ComputedRef, InjectionKey } from "vue";

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

export interface SidebarWidgetCapability {
  reads: SidebarWidgetContextKey[];
  emits: SidebarWidgetIntentType[];
}

export interface SidebarWidgetSelfTestScenario {
  name: string;
  objective: string;
  steps: string[];
  expected: string[];
}

export interface SidebarWidgetAuthorContract {
  displayName: string;
  description: string;
  acceptsProps: string[];
  capabilities: SidebarWidgetCapability;
  selfTests: SidebarWidgetSelfTestScenario[];
}

export interface SidebarWidgetDefinition {
  key: string;
  component: unknown;
  contract: SidebarWidgetAuthorContract;
}

export interface SidebarWidgetSelfTestCheck {
  name: string;
  passed: boolean;
  detail: string;
}

export interface SidebarWidgetSelfTestResult {
  widgetKey: string;
  passed: boolean;
  checks: SidebarWidgetSelfTestCheck[];
}

export const BROWSER_DASHBOARD_KEY: InjectionKey<Record<string, unknown>> = Symbol("browserDashboard");

export const SIDEBAR_WIDGET_INTERACTION_KEY: InjectionKey<
  ComputedRef<SidebarWidgetInteractionContext>
> = Symbol("sidebarWidgetInteraction");

const VALID_CONTEXT_KEYS: SidebarWidgetContextKey[] = [
  "classify-dashboard",
  "interaction-state",
  "prediction-grid-items",
  "browser-dashboard",
  "browser-items",
];

const VALID_INTENT_TYPES: SidebarWidgetIntentType[] = [
  "select-samples",
  "select-labels",
  "select-predictions",
  "apply-filter",
  "clear-selection",
  "focus-item",
];

export function defineSidebarWidget(
  definition: SidebarWidgetDefinition,
): SidebarWidgetDefinition {
  return definition;
}

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
  if (!nextLabel) {
    return null;
  }

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
  const incoming = values.filter((value) => value.trim().length > 0);

  if (operation === "clear") {
    return [];
  }

  if (operation === "replace") {
    return [...new Set(incoming)];
  }

  if (operation === "add") {
    incoming.forEach((value) => current.add(value));
    return Array.from(current);
  }

  if (operation === "remove") {
    incoming.forEach((value) => current.delete(value));
    return Array.from(current);
  }

  if (operation === "toggle") {
    incoming.forEach((value) => {
      if (current.has(value)) {
        current.delete(value);
      } else {
        current.add(value);
      }
    });
    return Array.from(current);
  }

  return currentIds;
}

export function reduceCollectionIntent(
  currentCollections: Record<string, SidebarWidgetCollectionState> | undefined,
  intent: SidebarWidgetIntent,
): Record<string, SidebarWidgetCollectionState> | undefined {
  const collectionKey = intent.metadata?.collection;
  if (!collectionKey || collectionKey.trim().length === 0) {
    return currentCollections;
  }

  const collection = collectionKey.trim();
  const existing = currentCollections?.[collection];
  const entity = intent.metadata?.entity ?? existing?.entity ?? "row";
  const revision = Number(intent.metadata?.revision ?? 0);
  const sourcePanelId = intent.sourcePanelId ?? null;

  const nextSelection = {
    ids: existing?.selection.ids ?? [],
    sourcePanelId: existing?.selection.sourcePanelId ?? null,
    revision: existing?.selection.revision ?? 0,
  };

  const nextFilter = {
    ids: existing?.filter.ids ?? [],
    mode: existing?.filter.mode ?? "all",
    sourcePanelId: existing?.filter.sourcePanelId ?? null,
    revision: existing?.filter.revision ?? 0,
  };

  if (
    intent.type === "select-samples" ||
    intent.type === "select-predictions" ||
    intent.type === "select-labels"
  ) {
    nextSelection.ids = applyIdsOperation(
      nextSelection.ids,
      intent.values,
      intent.operation,
    );
    nextSelection.sourcePanelId = sourcePanelId;
    nextSelection.revision = revision > 0 ? revision : nextSelection.revision + 1;
  }

  if (intent.type === "apply-filter") {
    nextFilter.ids = applyIdsOperation(nextFilter.ids, intent.values, intent.operation);
    nextFilter.mode = intent.metadata?.filterMode ?? nextFilter.mode;
    nextFilter.sourcePanelId = sourcePanelId;
    nextFilter.revision = revision > 0 ? revision : nextFilter.revision + 1;
  }

  if (intent.type === "clear-selection" || intent.operation === "clear") {
    const target = intent.metadata?.target ?? "both";
    if (target === "selection" || target === "both") {
      nextSelection.ids = [];
      nextSelection.sourcePanelId = sourcePanelId;
      nextSelection.revision = revision > 0 ? revision : nextSelection.revision + 1;
    }
    if (target === "filter" || target === "both") {
      nextFilter.ids = [];
      nextFilter.mode = "all";
      nextFilter.sourcePanelId = sourcePanelId;
      nextFilter.revision = revision > 0 ? revision : nextFilter.revision + 1;
    }
  }

  const nextCollection: SidebarWidgetCollectionState = {
    entity,
    selection: nextSelection,
    filter: nextFilter,
  };

  return {
    ...(currentCollections ?? {}),
    [collection]: nextCollection,
  };
}

export function runSidebarWidgetSelfTest(
  definition: SidebarWidgetDefinition,
): SidebarWidgetSelfTestResult {
  const { contract } = definition;

  const checks: SidebarWidgetSelfTestCheck[] = [
    {
      name: "widget key",
      passed: definition.key.trim().length > 0,
      detail: "Widget key must be a non-empty string.",
    },
    {
      name: "display name",
      passed: contract.displayName.trim().length > 0,
      detail:
        "Display name must be present for authors and registry consumers.",
    },
    {
      name: "description",
      passed: contract.description.trim().length > 0,
      detail: "Description must explain what the widget renders or controls.",
    },
    {
      name: "accepted props list",
      passed: contract.acceptsProps.every((prop) => prop.trim().length > 0),
      detail:
        "Every accepted prop must be listed explicitly when the widget accepts props.",
    },
    {
      name: "context keys",
      passed: contract.capabilities.reads.every((key) =>
        VALID_CONTEXT_KEYS.includes(key),
      ),
      detail:
        "Read contexts must come from the shared sidebar context vocabulary.",
    },
    {
      name: "intent types",
      passed: contract.capabilities.emits.every((intent) =>
        VALID_INTENT_TYPES.includes(intent),
      ),
      detail:
        "Emitted intents must stay inside the typed interaction vocabulary.",
    },
    {
      name: "self-test scenarios",
      passed: contract.selfTests.length > 0,
      detail:
        "Every widget needs at least one author-facing self-test scenario.",
    },
    {
      name: "scenario completeness",
      passed: contract.selfTests.every(
        (scenario) =>
          scenario.name.trim().length > 0 &&
          scenario.objective.trim().length > 0 &&
          scenario.steps.length > 0 &&
          scenario.expected.length > 0 &&
          scenario.steps.every((step) => step.trim().length > 0) &&
          scenario.expected.every(
            (expectation) => expectation.trim().length > 0,
          ),
      ),
      detail:
        "Each self-test scenario needs a name, objective, steps, and expected outcomes.",
    },
    {
      name: "interactive widgets declare interaction-state",
      passed:
        contract.capabilities.emits.length === 0 ||
        contract.capabilities.reads.includes("interaction-state"),
      detail:
        "Widgets that emit intents should also read from interaction-state.",
    },
  ];

  return {
    widgetKey: definition.key,
    passed: checks.every((check) => check.passed),
    checks,
  };
}
