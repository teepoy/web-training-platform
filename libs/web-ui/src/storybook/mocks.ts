import type { Decorator } from "@storybook/vue3";
import { computed, provide, type ComputedRef } from "vue";
import {
  BROWSER_DASHBOARD_KEY,
  SIDEBAR_WIDGET_INTERACTION_KEY,
  type SidebarWidgetInteractionContext,
  type SidebarWidgetInteractionState,
} from "@platform/plugin-sdk";

const defaultInteractionState: SidebarWidgetInteractionState = {
  activeLabelFilter: null,
  selectedLabels: [],
  collections: {
    samples: {
      entity: "sample",
      selection: { ids: [], sourcePanelId: null, revision: 0 },
      filter: { mode: "all", ids: [], sourcePanelId: null, revision: 0 },
    },
    predictions: {
      entity: "prediction",
      selection: { ids: [], sourcePanelId: null, revision: 0 },
      filter: { mode: "all", ids: [], sourcePanelId: null, revision: 0 },
    },
  },
};

export interface MockContextOverrides {
  classifyDashboard?: Record<string, unknown> | null;
  browserDashboard?: Record<string, unknown> | null;
  interactionState?: Partial<SidebarWidgetInteractionState>;
  predictionGridItems?: Array<Record<string, unknown>>;
  classifyGridItems?: Array<Record<string, unknown>>;
  onDispatch?: (intent: unknown) => void;
}

export function provideWebUiContext(
  overrides: MockContextOverrides = {},
): Decorator {
  return (story) => ({
    components: { story },
    setup() {
      const classifyDashboard =
        overrides.classifyDashboard === null
          ? null
          : {
              stats: {
                total_samples: 100,
                annotated_samples: 60,
                unlabeled_samples: 40,
                label_counts: { cat: 25, dog: 20, bird: 15 },
              },
              isLoading: false,
              isError: false,
              draftCount: 5,
              selectedCount: 3,
              refetch: () => {},
              ...(overrides.classifyDashboard ?? {}),
            };

      if (classifyDashboard) {
        provide("classifyDashboard", classifyDashboard);
      }

      provide(
        BROWSER_DASHBOARD_KEY,
        overrides.browserDashboard ?? { totalLoaded: 120, filteredCount: 90 },
      );

      const interactionState: SidebarWidgetInteractionState = {
        ...defaultInteractionState,
        ...(overrides.interactionState ?? {}),
      };

      const interactionCtx: ComputedRef<SidebarWidgetInteractionContext> =
        computed(() => ({
          state: interactionState,
          dispatch: (overrides.onDispatch ?? (() => {})) as (
            intent: unknown,
          ) => void,
        }));

      provide(SIDEBAR_WIDGET_INTERACTION_KEY, interactionCtx);
      provide(
        "pr-grid-items",
        computed(() => overrides.predictionGridItems ?? []),
      );
      provide(
        "classify-grid-items",
        computed(() => overrides.classifyGridItems ?? []),
      );

      return {};
    },
    template: "<story />",
  });
}
