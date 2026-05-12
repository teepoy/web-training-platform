/**
 * Page-level provider composable that owns BROWSER_DASHBOARD_KEY and
 * SIDEBAR_WIDGET_INTERACTION_KEY for in-scope pages.
 *
 * Call once per page in `<script setup>`. The composable provides both keys
 * at page level so widgets rendered anywhere in the page tree can inject
 * the same dashboard context and interaction state.
 *
 * Pass the returned `interactionContext` to BrowserSidebar's `:interaction`
 * prop for shared state between in-sidebar and out-of-sidebar widgets.
 *
 * For the full contract specification see:
 *   .sisyphus/notepads/sidebar-layout-decoupling/page-provider-contract.md
 */

import {
  provide,
  computed,
  ref,
  toValue,
  watch,
  shallowReactive,
  type ComputedRef,
  type Ref,
  type ShallowReactive,
} from "vue";
import {
  BROWSER_DASHBOARD_KEY,
  SIDEBAR_WIDGET_INTERACTION_KEY,
  reduceCollectionIntent,
  reduceLabelFilterIntent,
  type SidebarWidgetInteractionContext,
  type SidebarWidgetInteractionState,
  type SidebarWidgetIntent,
} from "@platform/plugin-sdk";
import type { ClassifyDashboardContext } from "../types/sidebar-widgets";

export interface UsePagePanelsOptions {
  /**
   * Dashboard context to provide under BROWSER_DASHBOARD_KEY.
   *
   * Accepts a static Record, a Ref, a ComputedRef, or a plain getter
   * function. The composable keeps a shallow reactive proxy in sync
   * so widgets see property updates without needing to re-inject.
   */
  dashboardContext:
    | Record<string, unknown>
    | Ref<Record<string, unknown>>
    | ComputedRef<Record<string, unknown>>
    | (() => Record<string, unknown>);

  /**
   * Optional backward-compatibility bridge: provide the annotation dashboard
   * under the legacy string key `"classifyDashboard"` so widgets that still
   * inject the old string key (LabelDistributionWidget,
   * AnnotationProgressWidget) continue to work.
   *
   * This can be removed once all consumers have migrated to the
   * Symbol-based injection keys (BROWSER_DASHBOARD_KEY and
   * SIDEBAR_WIDGET_INTERACTION_KEY).
   */
  classifyDashboard?: ClassifyDashboardContext;

  /**
   * Optional callback invoked AFTER the default reducers process an intent.
   * Use for page-specific side effects (e.g., syncing a local labelFilter ref
   * with activeLabelFilter).
   *
   * @param intent        - The dispatched intent
   * @param updatedState  - The interaction state AFTER the reducers ran
   */
  onIntent?: (
    intent: SidebarWidgetIntent,
    updatedState: SidebarWidgetInteractionState,
  ) => void;
}

export interface UsePagePanelsReturn {
  /** Pass to BrowserSidebar's `:interaction` prop for shared widget state. */
  interactionContext: ComputedRef<SidebarWidgetInteractionContext>;
  /** Read-only reactive snapshot of the interaction state. */
  interactionState: ComputedRef<SidebarWidgetInteractionState>;
  /** Low-level dispatch — prefer `interactionContext.value.dispatch` in widgets. */
  dispatchIntent: (intent: SidebarWidgetIntent) => void;
  /** The shallow-reactive dashboard object provided under BROWSER_DASHBOARD_KEY.
   *  Pass this to BrowserSidebar's `:context` prop so sidebar widgets see
   *  the same reactive object as out-of-sidebar widgets. */
  dashboard: ShallowReactive<Record<string, unknown>>;
}

// ---------------------------------------------------------------------------
// Composable
// ---------------------------------------------------------------------------

export function usePagePanels(
  options: UsePagePanelsOptions,
): UsePagePanelsReturn {
  const _dashboard = shallowReactive<Record<string, unknown>>(
    { ...toValue(options.dashboardContext) },
  );

  watch(
    () => toValue(options.dashboardContext),
    (next) => {
      for (const key of Object.keys(_dashboard)) {
        if (!(key in next)) {
          delete _dashboard[key];
        }
      }
      Object.assign(_dashboard, next);
    },
  );

  provide(BROWSER_DASHBOARD_KEY, _dashboard);

  const _state = ref<SidebarWidgetInteractionState>({
    activeLabelFilter: null,
    selectedLabels: [],
    collections: {},
  });

  const interactionState = computed(() => _state.value);

  function dispatchIntent(intent: SidebarWidgetIntent): void {
    _state.value = {
      ..._state.value,
      activeLabelFilter: reduceLabelFilterIntent(
        _state.value.activeLabelFilter,
        intent,
      ),
      collections: reduceCollectionIntent(
        _state.value.collections,
        intent,
      ),
    };
    options.onIntent?.(intent, _state.value);
  }

  const interactionContext = computed<SidebarWidgetInteractionContext>(
    () => ({
      state: interactionState.value,
      dispatch: dispatchIntent,
    }),
  );

  provide(SIDEBAR_WIDGET_INTERACTION_KEY, interactionContext);

  if (options.classifyDashboard) {
    provide("classifyDashboard", options.classifyDashboard);
  }

  return {
    interactionContext,
    interactionState,
    dispatchIntent,
    dashboard: _dashboard,
  };
}
