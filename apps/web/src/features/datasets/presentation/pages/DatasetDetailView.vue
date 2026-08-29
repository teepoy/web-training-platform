<script setup lang="ts">
import { computed, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import { useQueryClient } from "@tanstack/vue-query";
import { FlowModal, SampleDetailDrawer, type FlowCard } from "@/shared";
import {
  getGetDatasetApiV1DatasetsDatasetIdGetQueryKey,
  getGetSparseSummaryApiV1DatasetsDatasetIdSparseSummaryGetQueryKey,
  useGetDatasetApiV1DatasetsDatasetIdGet,
  useGetSparseSummaryApiV1DatasetsDatasetIdSparseSummaryGet,
} from "@/generated/orval/endpoints/api";
import type { Dataset, SparseSummaryResponse } from "@/generated/orval/models";
import { useOrgStore } from "@/features/auth/application/org";
import { orgScopedQueryKey } from "@/shared/api";
import ManualImporter from "@/features/datasets/presentation/components/ManualImporter.vue";
import ManualDatasetImporter from "@/features/datasets/presentation/components/ManualDatasetImporter.vue";
import ParquetImporter from "@/features/datasets/presentation/components/ParquetImporter.vue";
import DatasetTrainTab from "@/features/datasets/presentation/components/DatasetTrainTab.vue";
import DatasetPredictTab from "@/features/datasets/presentation/components/DatasetPredictTab.vue";
import DatasetPredictionExportTab from "@/features/datasets/presentation/components/DatasetPredictionExportTab.vue";
import DatasetViewPage from "@/features/datasets/presentation/pages/DatasetViewPage.vue";
import GlobalFilterControl from "@/features/sc/presentation/components/GlobalFilterControl.vue";
import { supportsScPredictionExport } from "@/features/sc/domain/predictionExportCapability";

const route = useRoute();
const router = useRouter();
const qc = useQueryClient();
const orgStore = useOrgStore();

const id = computed(() => String(route.params.id));
function tabFromHash(hash: string): string {
  return hash.startsWith("#") && hash.length > 1 ? hash.slice(1) : "overview";
}

const activeTab = ref(tabFromHash(route.hash));
const selectedSampleId = ref<string | null>(null);
const showImportFlow = ref(false);

const datasetQuery = useGetDatasetApiV1DatasetsDatasetIdGet(id, {
  query: {
    queryKey: computed(() =>
      orgScopedQueryKey(
        orgStore.currentOrgId,
        getGetDatasetApiV1DatasetsDatasetIdGetQueryKey(id.value),
      ),
    ),
    enabled: computed(() => !!orgStore.currentOrgId && !!id.value),
    retry: false,
  },
});

const dataset = computed(
  () => datasetQuery.data.value as Dataset & { ls_project_url?: string | null },
);

const isSparse = computed(() => dataset.value?.storage_mode === "file_shard_sparse");
const isScDataset = computed(
  () => dataset.value?.dataset_type === "image_sc" && dataset.value?.task_spec?.task_type === "sc",
);
const supportsPredictionExport = computed(() => supportsScPredictionExport(dataset.value ?? null));
const labelSpace = computed(() => dataset.value?.task_spec?.label_space ?? []);
const hasSampleBrowser = computed(() =>
  (dataset.value?.view_types ?? []).includes("image_input_v1"),
);
const hasDetailSampleBrowser = computed(() => hasSampleBrowser.value && !isScDataset.value);
const sparseSummaryQuery = useGetSparseSummaryApiV1DatasetsDatasetIdSparseSummaryGet(id, {
  query: {
    queryKey: computed(() =>
      orgScopedQueryKey(
        orgStore.currentOrgId,
        getGetSparseSummaryApiV1DatasetsDatasetIdSparseSummaryGetQueryKey(id.value),
      ),
    ),
    enabled: computed(() => !!orgStore.currentOrgId && !!id.value && isSparse.value),
    retry: false,
  },
});
const sparseSummary = computed(
  () => (sparseSummaryQuery.data.value as SparseSummaryResponse | undefined) ?? null,
);
const sampleCount = computed<number | null>(() => {
  const sparseTotal = sparseSummary.value?.manifest.total_rows;
  if (typeof sparseTotal === "number") return sparseTotal;
  const metadataTotal = dataset.value?.dataset_meta?.total_samples;
  return typeof metadataTotal === "number" ? metadataTotal : null;
});
const datasetKindLabel = computed(() => {
  if (isScDataset.value) return "Patch inspection";
  if (dataset.value?.dataset_type === "image_classification") return "Image classification";
  const value = dataset.value?.dataset_type?.replace(/_/g, " ").trim();
  return value ? value.replace(/^./, (character) => character.toUpperCase()) : "Dataset";
});

const availableTabs = computed(() => {
  const value = dataset.value;
  if (!value) return [];
  return [
    "overview",
    ...(hasDetailSampleBrowser.value ? ["samples"] : []),
    "train",
    "predict",
    ...(supportsPredictionExport.value ? ["export"] : []),
    ...(value.storage_mode !== "file_shard_sparse" ? ["annotate"] : []),
  ];
});

watch(
  [dataset, () => route.hash],
  ([value, hash]) => {
    if (!value) return;
    const requestedTab = tabFromHash(hash);
    if (isScDataset.value && (requestedTab === "classify" || requestedTab === "samples")) {
      openScClassify();
      return;
    }
    const nextTab = availableTabs.value.includes(requestedTab) ? requestedTab : "overview";
    if (activeTab.value !== nextTab) activeTab.value = nextTab;
    const canonicalHash = `#${nextTab}`;
    if (route.hash && route.hash !== canonicalHash) void router.replace({ hash: canonicalHash });
  },
  { immediate: true },
);

watch(activeTab, (tab) => {
  if (!availableTabs.value.includes(tab)) return;
  const hash = `#${tab}`;
  if (route.hash !== hash) void router.replace({ hash });
});

const importerFlows: FlowCard[] = [
  {
    id: "import-manual",
    label: "Manual Sample Entry",
    description: "Create one sample at a time with URI, metadata, or uploaded image.",
    icon: "✏️",
    component: ManualImporter,
  },
  {
    id: "import-dataset-manual",
    label: "Import from JSON",
    description: "Create a dataset by uploading a JSON file of sample items.",
    icon: "📁",
    component: ManualDatasetImporter,
  },
  {
    id: "import-parquet",
    label: "Import from Parquet",
    description:
      "Import samples from a HuggingFace-compatible Parquet file (image struct with bytes/path columns).",
    icon: "📦",
    component: ParquetImporter,
  },
];

function handleImporterComplete() {
  showImportFlow.value = false;
  activeTab.value = hasDetailSampleBrowser.value ? "samples" : "overview";
  qc.invalidateQueries({
    queryKey: orgScopedQueryKey(orgStore.currentOrgId, ["view-samples", id.value]),
  });
  qc.invalidateQueries({
    queryKey: orgScopedQueryKey(orgStore.currentOrgId, ["feature-samples", id.value]),
  });
}

function openScClassify() {
  void router.push({ name: "sc-reclassify", params: { id: id.value } });
}

function handleTabBeforeLeave(name: string | number): boolean {
  if (name !== "classify") return true;
  openScClassify();
  return false;
}
</script>

<template>
  <div class="dataset-detail-page">
    <n-spin
      v-if="datasetQuery.isLoading.value"
      style="display: flex; justify-content: center; padding: 48px"
    />
    <n-result
      v-else-if="datasetQuery.isError.value || !datasetQuery.data.value"
      status="404"
      title="Dataset Not Found"
      description="The dataset you are looking for does not exist or could not be loaded."
    >
      <template #footer
        ><n-button @click="router.push('/datasets')">Back to Datasets</n-button></template
      >
    </n-result>

    <template v-else>
      <header class="dataset-detail-header">
        <div class="dataset-heading">
          <n-button text class="back-button" @click="router.push('/datasets')">
            <template #icon><span aria-hidden="true">&#8592;</span></template>
            Datasets
          </n-button>
          <div class="dataset-title-block">
            <div class="dataset-title-line">
              <h1>{{ dataset.name }}</h1>
              <n-tag size="small" :bordered="false">{{ datasetKindLabel }}</n-tag>
            </div>
          </div>
        </div>
        <n-space class="dataset-header-actions" :wrap="true">
          <n-button
            v-if="!isSparse"
            :type="dataset.task_spec?.task_type === 'sc' ? 'default' : 'primary'"
            @click="showImportFlow = true"
          >
            Add samples
          </n-button>
        </n-space>
      </header>

      <GlobalFilterControl v-if="isScDataset" :dataset-id="id" />

      <n-tabs
        v-model:value="activeTab"
        type="line"
        animated
        class="dataset-tabs"
        :on-before-leave="handleTabBeforeLeave"
      >
        <n-tab-pane name="overview" tab="Overview">
          <n-card size="small" title="About this dataset" class="dataset-overview-card">
            <div class="dataset-overview-grid">
              <div class="overview-field">
                <n-text depth="3">Purpose</n-text>
                <strong>{{ datasetKindLabel }}</strong>
              </div>
              <div class="overview-field">
                <n-text depth="3">Samples</n-text>
                <strong>{{ sampleCount === null ? "—" : sampleCount.toLocaleString() }}</strong>
              </div>
              <div class="overview-field">
                <n-text depth="3">Created by</n-text>
                <strong>{{ dataset.creator_name || dataset.created_by || "System" }}</strong>
              </div>
              <div class="overview-field">
                <n-text depth="3">Created</n-text>
                <strong>{{
                  dataset.created_at ? new Date(dataset.created_at).toLocaleString() : "—"
                }}</strong>
              </div>
              <div class="overview-field overview-field-wide">
                <n-text depth="3">Labels</n-text>
                <n-space v-if="labelSpace.length" size="small">
                  <n-tag v-for="label in labelSpace" :key="label" size="small">
                    {{ label }}
                  </n-tag>
                </n-space>
                <n-text v-else depth="3">No labels configured</n-text>
              </div>
            </div>
          </n-card>
        </n-tab-pane>
        <n-tab-pane v-if="isScDataset" name="classify">
          <template #tab>
            <span>Classify <span aria-hidden="true">&#8599;</span></span>
          </template>
        </n-tab-pane>
        <n-tab-pane v-else-if="hasSampleBrowser" name="samples" tab="Samples">
          <DatasetViewPage
            :dataset-id="id"
            view-type="image_input_v1"
            @select-sample="selectedSampleId = $event"
          />
        </n-tab-pane>
        <n-tab-pane name="train" tab="Train">
          <DatasetTrainTab :dataset-id="id" :dataset="dataset" />
        </n-tab-pane>
        <n-tab-pane name="predict" tab="Predict">
          <DatasetPredictTab :dataset-id="id" :compatible-view-types="dataset.view_types ?? []" />
        </n-tab-pane>
        <n-tab-pane v-if="supportsPredictionExport" name="export" tab="Export">
          <DatasetPredictionExportTab :dataset-id="id" />
        </n-tab-pane>
        <n-tab-pane v-if="!isSparse" name="annotate" tab="Annotate">
          <template v-if="dataset?.ls_project_url"
            ><iframe
              :src="dataset.ls_project_url"
              class="annotation-frame"
              allow="clipboard-read; clipboard-write"
            />
            <div style="margin-top: 8px; display: flex; align-items: center; gap: 8px">
              <n-text depth="3" style="font-size: 12px"
                >Label Studio Project #{{ dataset.ls_project_id }}</n-text
              ><n-button text size="small" tag="a" :href="dataset.ls_project_url" target="_blank"
                >Open in new tab ↗</n-button
              >
            </div></template
          >
          <n-result
            v-else
            status="info"
            title="Label Studio URL Not Configured"
            description="The server does not have a Label Studio URL configured. Contact your administrator."
          />
        </n-tab-pane>
      </n-tabs>

      <SampleDetailDrawer
        :sampleId="selectedSampleId"
        :datasetId="id"
        :labelSpace="labelSpace"
        :sparse="isSparse"
        :show="selectedSampleId !== null"
        @close="selectedSampleId = null"
        @select-sample="
          (sid: string) => {
            selectedSampleId = sid;
          }
        "
      />
      <FlowModal
        v-model:show="showImportFlow"
        :flows="importerFlows"
        kind="import"
        title="Import Samples"
        :dataset-id="id"
        @complete="handleImporterComplete"
      />
    </template>
  </div>
</template>

<style scoped>
.dataset-detail-page {
  min-width: 0;
}

.dataset-detail-header {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: 20px;
  margin-bottom: 20px;
}

.dataset-heading {
  min-width: 0;
}

.back-button {
  margin-bottom: 8px;
}

.dataset-title-block {
  min-width: 0;
}

.dataset-title-line {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 10px;
}

.dataset-title-line h1 {
  min-width: 0;
  margin: 0;
  overflow-wrap: anywhere;
  font-size: 26px;
  line-height: 1.25;
}

.dataset-header-actions {
  flex: 0 0 auto;
}

.dataset-tabs {
  margin-top: 16px;
}

.dataset-overview-card {
  margin-top: 4px;
}

.dataset-overview-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 20px 28px;
}

.overview-field {
  display: flex;
  min-width: 0;
  flex-direction: column;
  gap: 5px;
}

.overview-field strong {
  overflow-wrap: anywhere;
  font-weight: 600;
}

.overview-field-wide {
  grid-column: 1 / -1;
}

.annotation-frame {
  width: 100%;
  height: calc(100vh - 240px);
  min-height: 520px;
  border: 1px solid var(--n-border-color, #e5e7eb);
  border-radius: 8px;
}

@media (max-width: 720px) {
  .dataset-detail-header {
    align-items: stretch;
    flex-direction: column;
    gap: 14px;
  }

  .dataset-header-actions :deep(.n-button) {
    flex: 1 1 auto;
  }

  .dataset-overview-grid {
    grid-template-columns: 1fr;
  }

  .overview-field-wide {
    grid-column: auto;
  }

  .annotation-frame {
    height: calc(100vh - 280px);
    min-height: 420px;
  }
}
</style>
