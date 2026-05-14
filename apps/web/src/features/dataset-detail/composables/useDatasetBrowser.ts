import { computed, onMounted, provide, ref, watch, type ComputedRef } from "vue";
import { useQuery } from "@tanstack/vue-query";
import { queryWaferPoints } from "@platform/web-data/agent";
import { BROWSER_DASHBOARD_KEY } from "@platform/widget-sdk";
import {
  buildBlinkTableData,
  DATA_PIPELINE_KEY,
  injectWaferPanelData,
  normalizeWaferPoint,
  resolveImageUris,
  useSampleLoader,
  useDataPipeline,
} from "@platform/web-ui";
import type { BlinkSampleInput } from "@platform/web-ui";
import type { BrowserItem, WaferPoint } from "../../../types";
import { datasetPanels } from "../../classify/config";

interface UseDatasetBrowserOptions {
  datasetId: ComputedRef<string>;
  labelSpace: ComputedRef<string[]>;
}

export function useDatasetBrowser({ datasetId, labelSpace }: UseDatasetBrowserOptions) {
  const pageDashboardData = ref<Record<string, unknown>>({});
  const browserSidebarDashboard: Record<string, unknown> = {
    get stats() {
      return browserSidebarStats.value;
    },
    get isLoading() {
      return sampleLoader.isLoading.value && sampleLoader.samples.value.length === 0;
    },
    get isError() {
      return false;
    },
    get errorMessage() {
      return null;
    },
    get draftCount() {
      return 0;
    },
    get selectedCount() {
      return 0;
    },
    get labelSpace() {
      return labelSpace.value;
    },
    refetch: () => sampleLoader.reset(),
  };

  provide("classifyDashboard", browserSidebarDashboard);
  provide(BROWSER_DASHBOARD_KEY, pageDashboardData.value);

  const sampleLoader = useSampleLoader({ datasetId });

  const browserSamples = computed<BrowserItem[]>(() =>
    sampleLoader.samples.value.map((sample) => ({
      id: sample.id,
      imageSrcs: resolveImageUris(sample.image_uris),
      metadata: sample.metadata ?? {},
      sourceKind: "dataset",
      currentLabel: sample.latest_annotation?.label ?? null,
      draftLabel: null,
      predictionLabel: null,
      predictionConfidence: null,
      predictionId: null,
      activationLabel: null,
    })),
  );

  const pipeline = useDataPipeline<BrowserItem>(browserSamples);
  provide(DATA_PIPELINE_KEY, pipeline);

  const filteredSamples = computed<BrowserItem[]>(() => {
    const labelFilter = pipeline.getNode("label-distribution")?.annotation.value;
    if (!labelFilter || labelFilter.kind !== "labelFilter" || labelFilter.ids.size === 0) return browserSamples.value;
    return browserSamples.value.filter((sample) => sample.currentLabel !== null && labelFilter.ids.has(sample.currentLabel));
  });

  const browserSidebarStats = computed(() => {
    const labelCounts: Record<string, number> = {};
    let annotatedSamples = 0;

    for (const sample of sampleLoader.samples.value) {
      const label = sample.latest_annotation?.label ?? null;
      if (!label) continue;
      annotatedSamples += 1;
      labelCounts[label] = (labelCounts[label] ?? 0) + 1;
    }

    return {
      total_samples: sampleLoader.totalCount.value,
      annotated_samples: annotatedSamples,
      unlabeled_samples: Math.max(sampleLoader.totalCount.value - annotatedSamples, 0),
      label_counts: labelCounts,
    };
  });

  watch(
    [() => sampleLoader.samples.value.length, filteredSamples, browserSidebarStats],
    () => {
      pageDashboardData.value = {
        totalLoaded: sampleLoader.samples.value.length,
        filteredCount: filteredSamples.value.length,
        stats: browserSidebarStats.value,
        isLoading: sampleLoader.isLoading.value && sampleLoader.samples.value.length === 0,
        isError: false,
        errorMessage: null,
        draftCount: 0,
        selectedCount: 0,
        labelSpace: labelSpace.value,
        refetch: () => sampleLoader.reset(),
      };
    },
    { immediate: true },
  );

  const waferPointsQuery = useQuery({
    queryKey: computed(() => ["dataset", datasetId.value, "wafer-points"]),
    queryFn: () => queryWaferPoints(datasetId.value),
    retry: false,
  });

  const waferPoints = computed<WaferPoint[]>(() => {
    const points = waferPointsQuery.data.value?.points ?? [];
    return points
      .map((point) => normalizeWaferPoint(point))
      .filter((point): point is WaferPoint => point !== null);
  });

  const blinkTableData = computed(() => {
    const multiSamples: BlinkSampleInput[] = browserSamples.value
      .filter((sample) => sample.imageSrcs.length > 1)
      .map((sample) => ({
        id: sample.id,
        imageSrcs: sample.imageSrcs,
        metadata: sample.metadata,
        label: sample.currentLabel ?? undefined,
      }));
    return buildBlinkTableData(multiSamples);
  });

  const datasetSidebarPanels = computed(() => {
    const waferInjected = injectWaferPanelData(datasetPanels, waferPoints.value, "browser-items");
    return waferInjected.map((panel) => {
      if (panel.id !== "blink-table") return panel;
      return {
        ...panel,
        props: {
          ...panel.props,
          data: {
            inline: {
              rows: blinkTableData.value.rows,
              columns: blinkTableData.value.columns,
            },
          },
        },
      };
    });
  });

  onMounted(() => {
    void sampleLoader.loadMore();
  });

  return {
    pageDashboardData,
    pageDashboard: pageDashboardData.value,
    sampleLoader,
    browserSamples,
    filteredSamples,
    browserSidebarStats,
    waferPointsQuery,
    waferPoints,
    blinkTableData,
    datasetSidebarPanels,
  };
}
