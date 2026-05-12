import type { Decorator } from "@storybook/vue3";
import { provide, shallowRef } from "vue";
import {
  BROWSER_DASHBOARD_KEY,
} from "@platform/widget-sdk";
import { DATA_PIPELINE_KEY, createDataPipeline } from "../composables/useDataPipeline";

export interface MockContextOverrides {
  classifyDashboard?: Record<string, unknown> | null;
  browserDashboard?: Record<string, unknown> | null;
  predictionGridItems?: Array<Record<string, unknown>>;
  classifyGridItems?: Array<Record<string, unknown>>;
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

      provide(DATA_PIPELINE_KEY, createDataPipeline(shallowRef([])));
      provide(
        "pr-grid-items",
        () => overrides.predictionGridItems ?? [],
      );
      provide(
        "classify-grid-items",
        () => overrides.classifyGridItems ?? [],
      );

      return {};
    },
    template: "<story />",
  });
}
