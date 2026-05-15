import type { Decorator } from "@storybook/vue3";
import { provide, shallowRef } from "vue";
import {
  BROWSER_DASHBOARD_KEY,
} from "@platform/widget-sdk";
import { DATA_PIPELINE_KEY, createDataPipeline } from "../composables/useDataPipeline";
import { fn } from "@storybook/test";
import type {
  ImporterProps,
  ExporterProps,
  PreviewLauncherRequiredProps,
} from "@platform/widget-sdk";

export function mockImportProps(
  overrides: Partial<ImporterProps> = {},
): ImporterProps {
  return {
    datasetId: "dataset-storybook-001",
    onComplete: fn(),
    onCancel: fn(),
    ...overrides,
  };
}

export function mockExportProps(
  overrides: Partial<ExporterProps> = {},
): ExporterProps {
  return {
    datasetId: "dataset-storybook-001",
    onComplete: fn(),
    onCancel: fn(),
    ...overrides,
  };
}

export function mockPreviewProps(
  overrides: Partial<PreviewLauncherRequiredProps> = {},
): PreviewLauncherRequiredProps {
  return {
    onComplete: fn(),
    onCancel: fn(),
    ...overrides,
  };
}

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
