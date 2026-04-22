import type { ComputedRef, InjectionKey } from "vue";

export type SidebarWidgetContextKey =
  | "classify-dashboard"
  | "interaction-state"
  | "prediction-grid-items";

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

export const SIDEBAR_WIDGET_INTERACTION_KEY: InjectionKey<
  ComputedRef<SidebarWidgetInteractionContext>
> = Symbol("sidebarWidgetInteraction");

const VALID_CONTEXT_KEYS: SidebarWidgetContextKey[] = [
  "classify-dashboard",
  "interaction-state",
  "prediction-grid-items",
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
