<script setup lang="ts">
import { computed, h, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import { useQueryClient } from "@tanstack/vue-query";
import { useMessage, NButton } from "naive-ui";
import { FlowModal, FlowTypeSelector, SampleDetailDrawer, type FlowCard } from "@/shared";
import { buildExportDownloadUrl } from "@/shared/api/datasets";
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
import PersistExportPlugin from "@/features/datasets/presentation/components/PersistExportPlugin.vue";
import ParquetExportPlugin from "@/features/datasets/presentation/components/ParquetExportPlugin.vue";
import PreviewExportPlugin from "@/features/datasets/presentation/components/PreviewExportPlugin.vue";
import DatasetTrainTab from "@/features/datasets/presentation/components/DatasetTrainTab.vue";
import DatasetPredictTab from "@/features/datasets/presentation/components/DatasetPredictTab.vue";
import DatasetSparseSummary from "@/features/datasets/presentation/components/DatasetSparseSummary.vue";
import DatasetViewPage from "@/features/datasets/presentation/pages/DatasetViewPage.vue";
import ScDatasetGlobalFilterControl from "@/features/sc/presentation/components/ScDatasetGlobalFilterControl.vue";

const route = useRoute();
const router = useRouter();
const message = useMessage();
const qc = useQueryClient();
const orgStore = useOrgStore();

const id = computed(() => String(route.params.id));
const activeTab = ref("overview");
const selectedSampleId = ref<string | null>(null);
const showImportFlow = ref(false);
const exportStep = ref<"select" | "execute">("select");
const selectedExporter = ref<FlowCard | null>(null);

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
const labelSpace = computed(() => dataset.value?.task_spec?.label_space ?? []);
const hasSampleBrowser = computed(() =>
  (dataset.value?.view_types ?? []).includes("image_input_v1"),
);
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

watch(
  dataset,
  (value) => {
    if (!value) return;
    const availableTabs = [
      "overview",
      ...(hasSampleBrowser.value ? ["samples"] : []),
      "train",
      "predict",
      ...(value.storage_mode !== "file_shard_sparse" ? ["annotate"] : []),
    ];
    if (!availableTabs.includes(activeTab.value)) {
      activeTab.value = availableTabs[0] ?? "train";
    }
  },
  { immediate: true },
);

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

const exporterFlows: FlowCard[] = [
  {
    id: "export-persist",
    label: "Persist Export",
    description: "Persist dataset export artifact and return a URI.",
    icon: "💾",
    component: PersistExportPlugin,
  },
  {
    id: "export-parquet",
    label: "Export as Parquet",
    description: "Export dataset samples and annotations as a HuggingFace-compatible Parquet file.",
    icon: "📦",
    component: ParquetExportPlugin,
  },
  {
    id: "export-preview",
    label: "Preview Export",
    description: "Generate and inspect dataset export payload without persisting.",
    icon: "👁️",
    component: PreviewExportPlugin,
  },
];

function handleImporterComplete() {
  showImportFlow.value = false;
  activeTab.value = "samples";
  qc.invalidateQueries({
    queryKey: orgScopedQueryKey(orgStore.currentOrgId, ["view-samples", id.value]),
  });
  qc.invalidateQueries({
    queryKey: orgScopedQueryKey(orgStore.currentOrgId, ["feature-samples", id.value]),
  });
}

function handleExportSelect(flow: FlowCard) {
  selectedExporter.value = flow;
  exportStep.value = "execute";
}

function handleExportBack() {
  exportStep.value = "select";
  selectedExporter.value = null;
}

function handleExportComplete(result: unknown) {
  exportStep.value = "select";
  selectedExporter.value = null;
  const payload = result as { url?: string; message?: string } | undefined;
  const url = payload?.url;
  if (url) {
    message.success(
      () =>
        h("span", {}, [
          payload.message ?? "Export complete",
          " — ",
          h(
            NButton,
            {
              tag: "a",
              href: buildExportDownloadUrl(url),
              download: true,
              type: "primary",
              size: "tiny",
              style: "margin-left: 8px",
            },
            { default: () => "Download" },
          ),
        ]),
      { duration: 10000 },
    );
  } else if (payload?.message) {
    message.success(payload.message);
  }
}

function openScClassify() {
  router.push({ name: "sc-reclassify", params: { id: id.value } });
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
              <n-tag size="small" :bordered="false">{{ dataset.storage_mode }}</n-tag>
            </div>
            <n-text depth="3" class="dataset-id">ID: {{ dataset.id }}</n-text>
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
          <n-button
            v-if="dataset.task_spec?.task_type === 'sc'"
            type="primary"
            @click="openScClassify"
          >
            Open classify workspace
          </n-button>
        </n-space>
      </header>

      <ScDatasetGlobalFilterControl v-if="dataset.task_spec?.task_type === 'sc'" :dataset-id="id" />

      <n-tabs v-model:value="activeTab" type="line" animated class="dataset-tabs">
        <n-tab-pane name="overview" tab="Overview">
          <n-card size="small" title="Dataset contract" class="dataset-contract-card">
            <div class="dataset-contract-grid">
              <div class="contract-field">
                <n-text depth="3">Dataset type</n-text>
                <strong>{{ dataset.dataset_type }}</strong>
              </div>
              <div class="contract-field">
                <n-text depth="3">Storage mode</n-text>
                <strong>{{ dataset.storage_mode }}</strong>
              </div>
              <div class="contract-field">
                <n-text depth="3">Task type</n-text>
                <strong>{{ dataset.task_spec?.task_type ?? "—" }}</strong>
              </div>
              <div class="contract-field">
                <n-text depth="3">Creator</n-text>
                <strong>{{ dataset.creator_name || dataset.created_by }}</strong>
              </div>
              <div class="contract-field contract-field-wide">
                <n-text depth="3">Labels</n-text>
                <n-space v-if="labelSpace.length" size="small">
                  <n-tag v-for="label in labelSpace" :key="label" size="small">
                    {{ label }}
                  </n-tag>
                </n-space>
                <n-text v-else depth="3">No labels configured</n-text>
              </div>
              <div class="contract-field contract-field-wide">
                <n-text depth="3">Available views</n-text>
                <n-space v-if="(dataset.view_types ?? []).length" size="small">
                  <n-tag v-for="viewType in dataset.view_types ?? []" :key="viewType" size="small">
                    {{ viewType }}
                  </n-tag>
                </n-space>
                <n-text v-else depth="3">No registered views</n-text>
              </div>
            </div>
          </n-card>
          <DatasetSparseSummary
            v-if="isSparse"
            :dataset-id="id"
            :sparse-summary="sparseSummary"
            :is-loading="sparseSummaryQuery.isLoading.value"
            @select-sample="selectedSampleId = $event"
          />
        </n-tab-pane>
        <n-tab-pane v-if="hasSampleBrowser" name="samples" tab="Samples">
          <DatasetViewPage
            :dataset-id="id"
            view-type="image_input_v1"
            @select-sample="selectedSampleId = $event"
          />
        </n-tab-pane>
        <n-tab-pane name="train" tab="Train">
          <DatasetTrainTab :dataset-id="id" :dataset="dataset" />
        </n-tab-pane>
        <n-tab-pane name="predict" tab="Predict"><DatasetPredictTab :dataset-id="id" /></n-tab-pane>
        <n-tab-pane v-if="false" name="export" tab="Export">
          <n-empty
            v-if="exporterFlows.length === 0"
            description="No export plugins available."
            style="margin-top: 24px"
          />
          <template v-else-if="exportStep === 'select'">
            <FlowTypeSelector :flows="exporterFlows" @select="handleExportSelect" />
          </template>
          <template v-else-if="exportStep === 'execute' && selectedExporter">
            <div style="margin-bottom: 12px">
              <n-button text @click="handleExportBack">&larr; Back to export options</n-button>
            </div>
            <component
              :is="selectedExporter?.component"
              :dataset-id="id"
              :on-complete="handleExportComplete"
              :on-cancel="handleExportBack"
            />
          </template>
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

.dataset-id {
  display: block;
  margin-top: 4px;
  overflow-wrap: anywhere;
  font-size: 12px;
}

.dataset-header-actions {
  flex: 0 0 auto;
}

.dataset-tabs {
  margin-top: 16px;
}

.dataset-contract-card {
  margin-top: 4px;
}

.dataset-contract-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 20px 28px;
}

.contract-field {
  display: flex;
  min-width: 0;
  flex-direction: column;
  gap: 5px;
}

.contract-field strong {
  overflow-wrap: anywhere;
  font-weight: 600;
}

.contract-field-wide {
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

  .dataset-contract-grid {
    grid-template-columns: 1fr;
  }

  .contract-field-wide {
    grid-column: auto;
  }

  .annotation-frame {
    height: calc(100vh - 280px);
    min-height: 420px;
  }
}
</style>
