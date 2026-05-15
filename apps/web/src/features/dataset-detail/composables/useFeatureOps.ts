import { computed, h, ref, type ComputedRef } from "vue";
import { useQuery } from "@tanstack/vue-query";
import { useMessage, type DataTableColumns } from "naive-ui";
import { listSamples } from "@platform/web-ui/api/samples"
import { getSimilarity, type SimilarityResponse } from "@platform/web-ui/api/datasets";
import { updateEmbedConfig, extractFeatures, getSelectionMetrics, getUncoveredHints } from "@platform/web-ui/api";
import type { ExtractFeaturesResponse, SelectionMetricsResponse, UncoveredHintsResponse } from "@platform/web-ui/api";

interface UseFeatureOpsOptions {
  datasetId: ComputedRef<string>;
}

interface SelectionMetricsRow {
  sample_id: string;
  uniqueness: number;
  representativeness: number;
}

export function useFeatureOps({ datasetId }: UseFeatureOpsOptions) {
  const message = useMessage();

  const featureSamplesQuery = useQuery({
    queryKey: computed(() => ["feature-samples", datasetId.value]),
    queryFn: () => listSamples(datasetId.value, 0, 100),
    enabled: computed(() => !!datasetId.value),
  });

  const embedConfigModel = ref("openai/clip-vit-base-patch32");
  const embedConfigDimension = ref(512);
  const embedConfigLoading = ref(false);
  const embedConfigSaved = ref(false);

  async function doApplyEmbedConfig() {
    embedConfigLoading.value = true;
    embedConfigSaved.value = false;
    try {
      await updateEmbedConfig(datasetId.value, { model: embedConfigModel.value, dimension: embedConfigDimension.value });
      await extractFeatures(datasetId.value, true);
      embedConfigSaved.value = true;
    } finally {
      embedConfigLoading.value = false;
    }
  }

  const extractFeaturesLoading = ref(false);
  const extractFeaturesResult = ref<ExtractFeaturesResponse | null>(null);

  async function doExtractFeatures() {
    extractFeaturesLoading.value = true;
    try {
      extractFeaturesResult.value = await extractFeatures(datasetId.value);
    } catch (error) {
      message.error(`Extract features failed: ${(error as Error).message}`);
    } finally {
      extractFeaturesLoading.value = false;
    }
  }

  const similarityLoading = ref(false);
  const similaritySampleId = ref<string | null>(null);
  const similarityResult = ref<SimilarityResponse | null>(null);

  const sampleSelectOptions = computed(() =>
    (featureSamplesQuery.data.value?.items ?? []).map((sample) => ({
      label: `${sample.id.slice(0, 8)}… — ${sample.image_uris.length} image(s)`,
      value: sample.id,
    })),
  );

  const neighborColumns: DataTableColumns<{ sample_id: string; score: number }> = [
    {
      title: "Sample ID",
      key: "sample_id",
      render: (row) => h("span", { style: "font-family: monospace; font-size: 11px" }, row.sample_id),
    },
    {
      title: "Score",
      key: "score",
      width: 100,
      render: (row) => h("span", {}, String(row.score)),
    },
  ];

  async function doSimilaritySearch() {
    if (!similaritySampleId.value) return;
    similarityLoading.value = true;
    try {
      similarityResult.value = await getSimilarity(datasetId.value, similaritySampleId.value);
    } catch (error) {
      message.error(`Similarity search failed: ${(error as Error).message}`);
    } finally {
      similarityLoading.value = false;
    }
  }

  const selectionMetricsLoading = ref(false);
  const selectionMetricsResult = ref<SelectionMetricsResponse | null>(null);

  const selectionMetricsRows = computed<SelectionMetricsRow[]>(() => {
    if (!selectionMetricsResult.value) return [];
    const { uniqueness, representativeness } = selectionMetricsResult.value;
    return Object.keys(uniqueness).map((sampleId) => ({
      sample_id: sampleId,
      uniqueness: uniqueness[sampleId],
      representativeness: representativeness[sampleId] ?? 0,
    }));
  });

  const selectionMetricsColumns: DataTableColumns<SelectionMetricsRow> = [
    {
      title: "Sample ID",
      key: "sample_id",
      render: (row) => h("span", { style: "font-family: monospace; font-size: 11px" }, row.sample_id),
    },
    {
      title: "Uniqueness",
      key: "uniqueness",
      width: 120,
      render: (row) => h("span", {}, String(row.uniqueness)),
    },
    {
      title: "Representativeness",
      key: "representativeness",
      width: 160,
      render: (row) => h("span", {}, String(row.representativeness)),
    },
  ];

  async function doSelectionMetrics() {
    selectionMetricsLoading.value = true;
    try {
      selectionMetricsResult.value = await getSelectionMetrics(datasetId.value);
    } catch (error) {
      message.error(`Selection metrics failed: ${(error as Error).message}`);
    } finally {
      selectionMetricsLoading.value = false;
    }
  }

  const uncoveredClustersLoading = ref(false);
  const uncoveredClustersResult = ref<UncoveredHintsResponse | null>(null);

  const clusterColumns: DataTableColumns<{ cluster_id: string; size: number; hint: string }> = [
    {
      title: "Cluster ID",
      key: "cluster_id",
      width: 120,
      render: (row) => h("span", { style: "font-family: monospace; font-size: 11px" }, row.cluster_id),
    },
    {
      title: "Size",
      key: "size",
      width: 80,
      render: (row) => h("span", {}, String(row.size)),
    },
    {
      title: "Hint",
      key: "hint",
      render: (row) => h("span", {}, row.hint),
    },
  ];

  async function doUncoveredClusters() {
    uncoveredClustersLoading.value = true;
    try {
      uncoveredClustersResult.value = await getUncoveredHints(datasetId.value);
    } catch (error) {
      message.error(`Uncovered clusters failed: ${(error as Error).message}`);
    } finally {
      uncoveredClustersLoading.value = false;
    }
  }

  return {
    featureSamplesQuery,
    embedConfigModel,
    embedConfigDimension,
    embedConfigLoading,
    embedConfigSaved,
    doApplyEmbedConfig,
    extractFeaturesLoading,
    extractFeaturesResult,
    doExtractFeatures,
    similarityLoading,
    similaritySampleId,
    similarityResult,
    sampleSelectOptions,
    neighborColumns,
    doSimilaritySearch,
    selectionMetricsLoading,
    selectionMetricsResult,
    selectionMetricsRows,
    selectionMetricsColumns,
    doSelectionMetrics,
    uncoveredClustersLoading,
    uncoveredClustersResult,
    clusterColumns,
    doUncoveredClusters,
  };
}
