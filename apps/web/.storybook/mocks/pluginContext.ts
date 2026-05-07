import type { Decorator } from "@storybook/vue3";
import { provide, computed, type ComputedRef } from "vue";
import {
  BROWSER_DASHBOARD_KEY,
  SIDEBAR_WIDGET_INTERACTION_KEY,
  type SidebarWidgetInteractionContext,
  type SidebarWidgetInteractionState,
} from "@platform/plugin-sdk";

export interface MockClassifyDashboardContext {
  stats: Record<string, unknown> | null;
  isLoading: boolean;
  isError: boolean;
  errorMessage: string | null;
  draftCount: number;
  selectedCount: number;
  refetch: () => void;
}

export interface MockPluginContextOverrides {
  classifyDashboard?: Partial<MockClassifyDashboardContext> | null;
  browserDashboard?: Record<string, unknown> | null;
  interactionState?: Partial<SidebarWidgetInteractionState> | null;
  onDispatch?: (intent: unknown) => void;
}

const defaultClassifyDashboard: MockClassifyDashboardContext = {
  stats: {
    total_samples: 100,
    annotated_samples: 60,
    unlabeled_samples: 40,
    label_counts: {
      cat: 25,
      dog: 20,
      bird: 15,
    },
  },
  isLoading: false,
  isError: false,
  errorMessage: null,
  draftCount: 5,
  selectedCount: 3,
  refetch: () => {},
};

const defaultInteractionState: SidebarWidgetInteractionState = {
  activeLabelFilter: null,
  selectedLabels: [],
  collections: {},
};

export function providePluginContext(
  overrides: MockPluginContextOverrides = {},
): Decorator {
  return (story) => ({
    components: { story },
    setup() {
      const classifyDashboard =
        overrides.classifyDashboard === null
          ? null
          : {
              ...defaultClassifyDashboard,
              ...(overrides.classifyDashboard ?? {}),
            };

      if (classifyDashboard) {
        provide("classifyDashboard", classifyDashboard);
      }

      const browserDashboard =
        overrides.browserDashboard === null
          ? null
          : {
              totalLoaded: 100,
              filteredCount: 85,
              ...(overrides.browserDashboard ?? {}),
            };

      if (browserDashboard) {
        provide(BROWSER_DASHBOARD_KEY, browserDashboard);
      }

      const interactionState: SidebarWidgetInteractionState = {
        ...defaultInteractionState,
        ...(overrides.interactionState ?? {}),
      };

      const dispatch = overrides.onDispatch ?? (() => {});

      const interactionCtx: ComputedRef<SidebarWidgetInteractionContext> =
        computed(() => ({
          state: interactionState,
          dispatch: dispatch as (intent: unknown) => void,
        }));

      provide(SIDEBAR_WIDGET_INTERACTION_KEY, interactionCtx);

      provide(
        "pr-grid-items",
        computed(() => []),
      );

      provide("classify-grid-items", computed(() => []));

      return {};
    },
    template: "<story />",
  });
}

export { defaultClassifyDashboard, defaultInteractionState };
