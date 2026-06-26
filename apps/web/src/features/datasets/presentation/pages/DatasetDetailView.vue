<script setup lang="ts">
import { computed, h, ref } from "vue";
import { useRoute, useRouter } from "vue-router";
import { useQuery, useQueryClient } from "@tanstack/vue-query";
import { useMessage, NButton } from "naive-ui";
import { FlowModal, FlowTypeSelector, SampleDetailDrawer, type FlowCard } from "@/shared";
import { getDataset, buildExportDownloadUrl } from "@/shared/api/datasets";
import type { Dataset } from "@/generated/orval/models";
import ManualImporter from "@/features/datasets/presentation/components/ManualImporter.vue";
import ManualDatasetImporter from "@/features/datasets/presentation/components/ManualDatasetImporter.vue";
import ParquetImporter from "@/features/datasets/presentation/components/ParquetImporter.vue";
import PersistExportPlugin from "@/features/datasets/presentation/components/PersistExportPlugin.vue";
import ParquetExportPlugin from "@/features/datasets/presentation/components/ParquetExportPlugin.vue";
import PreviewExportPlugin from "@/features/datasets/presentation/components/PreviewExportPlugin.vue";
import DatasetTrainTab from "@/features/datasets/presentation/components/DatasetTrainTab.vue";
import DatasetPredictTab from "@/features/datasets/presentation/components/DatasetPredictTab.vue";

const route = useRoute();
const router = useRouter();
const message = useMessage();
const qc = useQueryClient();

const id = computed(() => String(route.params.id));
const activeTab = ref("train");
const selectedSampleId = ref<string | null>(null);
const showImportFlow = ref(false);
const exportStep = ref<"select" | "execute">("select");
const selectedExporter = ref<FlowCard | null>(null);

const datasetQuery = useQuery({
  queryKey: computed(() => ["dataset", id.value]),
  queryFn: () => getDataset(id.value),
  retry: false,
});

const dataset = computed(
  () => datasetQuery.data.value as Dataset & { ls_project_url?: string | null },
);

const isSparse = computed(() => dataset.value?.storage_mode === "file_shard_sparse");
const labelSpace = computed(() => dataset.value?.task_spec?.label_space ?? []);

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
  qc.invalidateQueries({ queryKey: ["view-samples", id.value] });
  qc.invalidateQueries({ queryKey: ["feature-samples", id.value] });
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
  <div>
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
      <div style="display: flex; align-items: center; gap: 12px; margin-bottom: 20px">
        <n-button text @click="router.push('/datasets')"
          ><template #icon><span>&#8592;</span></template
          >Back</n-button
        >
        <n-divider vertical />
        <div>
          <n-h2 style="margin: 0">{{ dataset.name }}</n-h2>
          <n-text depth="3" style="font-size: 12px">ID: {{ dataset.id }}</n-text>
        </div>
        <n-button
          v-if="dataset.task_spec?.task_type === 'sc'"
          type="primary"
          size="small"
          @click="openScClassify"
          >Classify</n-button
        >
      </div>

      <div style="margin-bottom: 16px; display: flex; align-items: center; gap: 8px">
        <n-button
          v-if="!isSparse"
          size="small"
          type="primary"
          style="margin-left: auto"
          @click="showImportFlow = true"
          >Add Sample</n-button
        >
      </div>
      <n-tabs v-model:value="activeTab" type="line" animated>
        <n-tab-pane name="train" tab="Train"><DatasetTrainTab :dataset-id="id" /></n-tab-pane>
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
              style="
                width: 100%;
                height: calc(100vh - 200px);
                border: 1px solid #eee;
                border-radius: 8px;
              "
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
