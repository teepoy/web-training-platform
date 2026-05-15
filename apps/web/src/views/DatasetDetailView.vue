<script setup lang="ts">
import { computed, ref } from "vue";
import { useRoute, useRouter } from "vue-router";
import { useQuery, useQueryClient } from "@tanstack/vue-query";
import { useMessage } from "naive-ui";
import { BrowserSidebar, FlowModal, SampleBrowser, SampleDetailDrawer, type FlowCard } from "@platform/web-ui";
import { getDataset } from "@platform/web-ui/api/datasets";
import { getSparseSummary } from "@platform/web-ui/api/datasets";
import { COLLAPSED_SIDEBAR_WIDTH, MAX_SIDEBAR_WIDTH, MIN_SIDEBAR_WIDTH, useSampleBrowserPrefs } from "@platform/web-ui";
import type { Dataset, SparseSummaryResponse } from "../types";
import ManualImporter from "../features/dataset-detail/components/ManualImporter.vue";
import ManualDatasetImporter from "../features/dataset-detail/components/ManualDatasetImporter.vue";
import ParquetImporter from "../features/dataset-detail/components/ParquetImporter.vue";
import PersistExportPlugin from "../features/dataset-detail/components/PersistExportPlugin.vue";
import ParquetExportPlugin from "../features/dataset-detail/components/ParquetExportPlugin.vue";
import PreviewExportPlugin from "../features/dataset-detail/components/PreviewExportPlugin.vue";
import { widgetComponentMap } from "../components/classify/widgetMap";
import { useDatasetBrowser } from "../features/dataset-detail/composables/useDatasetBrowser";
import DatasetSparseSummary from "../features/dataset-detail/components/DatasetSparseSummary.vue";
import DatasetFeatureOpsTab from "../features/dataset-detail/components/DatasetFeatureOpsTab.vue";

const route = useRoute();
const router = useRouter();
const message = useMessage();
const qc = useQueryClient();
const prefs = useSampleBrowserPrefs();

const id = computed(() => String(route.params.id));
const activeTab = ref("samples");
const selectedSampleId = ref<string | null>(null);
const showImportFlow = ref(false);
const showExportFlow = ref(false);

const datasetQuery = useQuery({
  queryKey: computed(() => ["dataset", id.value]),
  queryFn: () => getDataset(id.value),
  retry: false,
});

const dataset = computed(() => datasetQuery.data.value as Dataset & { ls_project_url?: string | null });
const isSparse = computed(() => dataset.value?.storage_mode === "file_shard_sparse");
const labelSpace = computed(() => dataset.value?.task_spec?.label_space ?? []);

const sparseSummaryQuery = useQuery({
  queryKey: computed(() => ["sparse-summary", id.value]),
  queryFn: () => getSparseSummary(id.value),
  enabled: computed(() => isSparse.value),
  retry: false,
});

const sparseSummary = computed(() => (sparseSummaryQuery.data.value as SparseSummaryResponse | undefined) ?? null);

const browser = useDatasetBrowser({ datasetId: id, labelSpace });

const importerFlows: FlowCard[] = [
  { id: "import-manual", label: "Manual Sample Entry", description: "Create one sample at a time with URI, metadata, or uploaded image.", icon: "✏️", component: ManualImporter },
  { id: "import-dataset-manual", label: "Import from JSON", description: "Create a dataset by uploading a JSON file of sample items.", icon: "📁", component: ManualDatasetImporter },
  { id: "import-parquet", label: "Import from Parquet", description: "Import samples from a HuggingFace-compatible Parquet file (image struct with bytes/path columns).", icon: "📦", component: ParquetImporter },
];

const exporterFlows: FlowCard[] = [
  { id: "export-persist", label: "Persist Export", description: "Persist dataset export artifact and return a URI.", icon: "💾", component: PersistExportPlugin },
  { id: "export-parquet", label: "Export as Parquet", description: "Export dataset samples and annotations as a HuggingFace-compatible Parquet file.", icon: "📦", component: ParquetExportPlugin },
  { id: "export-preview", label: "Preview Export", description: "Generate and inspect dataset export payload without persisting.", icon: "👁️", component: PreviewExportPlugin },
];

function handleImporterComplete() {
  showImportFlow.value = false;
  browser.sampleLoader.reset();
  qc.invalidateQueries({ queryKey: ["feature-samples", id.value] });
}

function openSampleDetail(sampleId: string) {
  selectedSampleId.value = sampleId;
}

function handleExporterComplete(result: unknown) {
  showExportFlow.value = false;
  const payload = result as { url?: string; message?: string } | undefined;
  if (payload?.message) message.success(payload.message);
}
</script>

<template>
  <div>
    <n-spin v-if="datasetQuery.isLoading.value" style="display: flex; justify-content: center; padding: 48px" />
    <n-result v-else-if="datasetQuery.isError.value || !datasetQuery.data.value" status="404" title="Dataset Not Found" description="The dataset you are looking for does not exist or could not be loaded.">
      <template #footer><n-button @click="router.push('/datasets')">Back to Datasets</n-button></template>
    </n-result>

    <template v-else>
      <div style="display: flex; align-items: center; gap: 12px; margin-bottom: 20px">
        <n-button text @click="router.push('/datasets')"><template #icon><span>&#8592;</span></template>Back</n-button>
        <n-divider vertical />
        <div>
          <n-h2 style="margin: 0">{{ dataset.name }}</n-h2>
          <n-text depth="3" style="font-size: 12px">Task: {{ dataset.task_spec.task_type }} &nbsp;|&nbsp; ID: {{ dataset.id }}<template v-if="isSparse"> &nbsp;|&nbsp; <n-tag type="info" size="small">Sparse Storage</n-tag></template></n-text>
          <div v-if="dataset.ls_project_id" style="margin-top: 4px"><n-tag type="success" size="small"><a v-if="dataset.ls_project_url" :href="dataset.ls_project_url" target="_blank" rel="noreferrer" style="color: inherit; text-decoration: none">Label Studio Project #{{ dataset.ls_project_id }} ↗</a><span v-else>Label Studio Project #{{ dataset.ls_project_id }}</span></n-tag></div>
        </div>
        <n-button v-if="dataset?.task_spec?.label_space?.length > 0" type="primary" size="small" @click="router.push(`/datasets/${dataset.id}/classify`)">Open Workflow</n-button>
      </div>

      <n-tabs v-model:value="activeTab" type="line" animated>
        <n-tab-pane name="samples" tab="Samples">
          <DatasetSparseSummary v-if="isSparse" :dataset-id="id" :sparse-summary="sparseSummary" :is-loading="sparseSummaryQuery.isLoading.value" />
          <template v-else>
            <div style="margin-bottom: 12px; display: flex; justify-content: space-between; align-items: center">
              <n-radio-group v-model:value="prefs.layout" size="small"><n-radio-button value="grid">Grid</n-radio-button><n-radio-button value="list">List</n-radio-button></n-radio-group>
              <n-button type="primary" @click="showImportFlow = true">Add Sample</n-button>
            </div>
            <div class="ds-samples-layout">
              <SampleBrowser :items="browser.filteredSamples.value" :total-count="browser.sampleLoader.totalCount.value" :thumb-size="prefs.thumbSize" :layout="prefs.layout" :is-loading="browser.sampleLoader.isLoading.value" :selection-enabled="false" :show-checkboxes="false" :show-label-rail="false" :show-bottom-bar="false" activation-mode="open" @open-item="openSampleDetail" @load-more="browser.sampleLoader.loadMore()" />
              <BrowserSidebar :panels="browser.datasetSidebarPanels.value" :context="browser.pageDashboard" :collapsed="prefs.sidebarCollapsed" :sidebar-width="prefs.sidebarWidth" :min-sidebar-width="MIN_SIDEBAR_WIDTH" :max-sidebar-width="MAX_SIDEBAR_WIDTH" :collapsed-sidebar-width="COLLAPSED_SIDEBAR_WIDTH" :component-resolver="(key: string) => widgetComponentMap[key] ?? null" @update:collapsed="prefs.setSidebarCollapsed" @update:sidebar-width="prefs.setSidebarWidth" />
            </div>
          </template>
        </n-tab-pane>

        <n-tab-pane name="export" tab="Export"><n-empty v-if="exporterFlows.length === 0" description="No export plugins available." style="margin-top: 24px" /><div v-else style="display: flex; justify-content: center; padding: 24px 0"><n-button type="primary" @click="showExportFlow = true">Export Dataset</n-button></div></n-tab-pane>
        <n-tab-pane name="feature-ops" tab="Feature Ops"><DatasetFeatureOpsTab :dataset-id="id" :is-sparse="isSparse" /></n-tab-pane>
        <n-tab-pane v-if="!isSparse" name="annotate" tab="Annotate">
          <template v-if="dataset?.ls_project_url"><iframe :src="dataset.ls_project_url" style="width: 100%; height: calc(100vh - 200px); border: 1px solid #eee; border-radius: 8px;" allow="clipboard-read; clipboard-write" /><div style="margin-top: 8px; display: flex; align-items: center; gap: 8px"><n-text depth="3" style="font-size: 12px">Label Studio Project #{{ dataset.ls_project_id }}</n-text><n-button text size="small" tag="a" :href="dataset.ls_project_url" target="_blank">Open in new tab ↗</n-button></div></template>
          <n-result v-else status="info" title="Label Studio URL Not Configured" description="The server does not have a Label Studio URL configured. Contact your administrator." />
        </n-tab-pane>
      </n-tabs>

      <SampleDetailDrawer :sampleId="selectedSampleId" :datasetId="id" :labelSpace="labelSpace" :sparse="isSparse" :show="selectedSampleId !== null" @close="selectedSampleId = null" @select-sample="(sid: string) => { selectedSampleId = sid }" />
      <FlowModal v-model:show="showImportFlow" :flows="importerFlows" kind="import" title="Import Samples" :dataset-id="id" @complete="handleImporterComplete" />
      <FlowModal v-model:show="showExportFlow" :flows="exporterFlows" kind="export" title="Export Dataset" :dataset-id="id" @complete="handleExporterComplete" />
    </template>
  </div>
</template>

<style scoped>
.ds-samples-layout {
  display: flex;
  height: 600px;
  min-height: 0;
  overflow: hidden;
}
</style>
