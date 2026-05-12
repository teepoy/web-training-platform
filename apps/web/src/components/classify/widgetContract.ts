/**
 * widgetContract.ts — backward-compatible re-export shim.
 *
 * All shared types and injection keys are now authoritative in @platform/widget-sdk.
 * This file re-exports them so existing imports keep working without change.
 * New code should import directly from @platform/widget-sdk.
 */

// ---------------------------------------------------------------------------
// Re-export from SDK — injection keys MUST be the same Symbol instances so that
// provide() in BrowserSidebar and inject() in widgets resolve to the same slot.
// ---------------------------------------------------------------------------

export {
  BROWSER_DASHBOARD_KEY,
  SIDEBAR_WIDGET_INTERACTION_KEY,
  reduceCollectionIntent,
  reduceLabelFilterIntent,
} from "@platform/widget-sdk";

export type {
  SidebarWidgetContextKey,
  SidebarWidgetIntentType,
  SidebarWidgetOperation,
  SidebarWidgetCollectionEntity,
  SidebarWidgetSource,
  SidebarWidgetIntentTarget,
  SidebarWidgetFilterMode,
  SidebarWidgetIntentMetadata,
  SidebarWidgetIntent,
  SidebarWidgetCollectionSelectionState,
  SidebarWidgetCollectionFilterState,
  SidebarWidgetCollectionState,
  SidebarWidgetInteractionState,
  SidebarWidgetInteractionConfig,
  SidebarWidgetInteractionContext,
  SidebarWidgetCapability,
  SidebarWidgetSelfTestScenario,
} from "@platform/widget-sdk";

// ---------------------------------------------------------------------------
// App-local legacy types kept for backward compat with sidebarConfig.ts
// and the existing widget self-test infrastructure.
// These will be removed once all widgets are migrated to DashboardWidgetDescriptor.
// ---------------------------------------------------------------------------

import type {
  SidebarWidgetContextKey,
  SidebarWidgetIntentType,
  SidebarWidgetCapability,
  SidebarWidgetSelfTestScenario,
} from "@platform/widget-sdk";

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

export function defineSidebarWidget(
  definition: SidebarWidgetDefinition,
): SidebarWidgetDefinition {
  return definition;
}

// ---------------------------------------------------------------------------
// Self-test runner (app-local — not in SDK)
// ---------------------------------------------------------------------------

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
