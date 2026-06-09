import type { Decorator } from "@storybook/vue3";
import { provide, shallowRef, onUnmounted } from "vue";
import {
  BROWSER_DASHBOARD_KEY,
} from "@/shared/widgets/sdk";
import { DATA_PIPELINE_KEY, createDataPipeline } from "../composables/useDataPipeline";
import { fn } from "@storybook/test";
import type {
  ImporterProps,
  ExporterProps,
  PreviewLauncherRequiredProps,
} from "@/shared/widgets/sdk";

export interface FetchMockEntry {
  urlPattern: string | RegExp;
  method?: string;
  response: {
    status?: number;
    body: unknown;
    headers?: Record<string, string>;
  };
}

export function provideFetchMock(entries: FetchMockEntry[]): Decorator {
  return (story) => ({
    components: { story },
    setup() {
      const originalFetch = window.fetch.bind(window);

      window.fetch = (async (input: RequestInfo | URL, init?: RequestInit) => {
        const url = typeof input === "string" ? input : input instanceof URL ? input.href : input.url;
        const method = (init?.method ?? "GET").toUpperCase();

        for (const entry of entries) {
          const patternMatch =
            typeof entry.urlPattern === "string"
              ? url.includes(entry.urlPattern)
              : entry.urlPattern.test(url);
          const methodMatch = !entry.method || entry.method.toUpperCase() === method;

          if (patternMatch && methodMatch) {
            return new Response(JSON.stringify(entry.response.body), {
              status: entry.response.status ?? 200,
              headers: {
                "Content-Type": "application/json",
                ...(entry.response.headers ?? {}),
              },
            });
          }
        }

        return originalFetch(input, init);
      }) as typeof window.fetch;

      onUnmounted(() => {
        window.fetch = originalFetch;
      });

      return {};
    },
    template: "<story />",
  });
}

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
