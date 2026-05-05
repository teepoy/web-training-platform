<template>
  <div>
    <!-- Loading state -->
    <n-spin v-if="datasetQuery.isLoading.value" style="display: flex; justify-content: center; padding: 48px" />

    <!-- 404 / error state -->
    <n-result
      v-else-if="datasetQuery.isError.value || !datasetQuery.data.value"
      status="404"
      title="Dataset Not Found"
      description="The dataset you are looking for does not exist or could not be loaded."
    >
      <template #footer>
        <n-button @click="router.push('/datasets')">Back to Datasets</n-button>
      </template>
    </n-result>

    <!-- Main content -->
    <template v-else>
      <!-- Header -->
      <div style="display: flex; align-items: center; gap: 12px; margin-bottom: 20px">
        <n-button text @click="router.push('/datasets')">
          <template #icon>
            <span>&#8592;</span>
          </template>
          Back
        </n-button>
        <n-divider vertical />
        <div>
          <n-h2 style="margin: 0">{{ dataset.name }}</n-h2>
          <n-text depth="3" style="font-size: 12px">
            Task: {{ dataset.task_spec.task_type }} &nbsp;|&nbsp; ID: {{ dataset.id }}
          </n-text>
          <div v-if="dataset.ls_project_id" style="margin-top: 4px">
            <n-tag type="success" size="small">
              <a
                v-if="dataset.ls_project_url"
                :href="dataset.ls_project_url"
                target="_blank"
                rel="noreferrer"
                style="color: inherit; text-decoration: none"
              >
                Label Studio Project #{{ dataset.ls_project_id }} ↗
              </a>
              <span v-else>
                Label Studio Project #{{ dataset.ls_project_id }}
              </span>
            </n-tag>
          </div>
        </div>
        <n-button
          v-if="dataset?.task_spec?.label_space?.length > 0"
          type="primary"
          size="small"
          @click="router.push(`/datasets/${dataset.id}/classify`)"
        >
          Open Workflow
        </n-button>
      </div>

      <!-- Tabs -->
      <n-tabs v-model:value="activeTab" type="line" animated>
        <!-- ============================================================ -->
        <!-- TAB 1: Samples -->
        <!-- ============================================================ -->
        <n-tab-pane name="samples" tab="Samples">
          <div style="margin-bottom: 12px; display: flex; justify-content: space-between; align-items: center">
            <n-radio-group v-model:value="prefs.layout" size="small">
              <n-radio-button value="grid">Grid</n-radio-button>
              <n-radio-button value="list">List</n-radio-button>
            </n-radio-group>
            <n-button type="primary" @click="showAddSampleModal = true">Add Sample</n-button>
          </div>

          <div class="ds-samples-layout">
            <SampleBrowser
              :items="filteredSamples"
              :total-count="sampleLoader.totalCount.value"
              :thumb-size="prefs.thumbSize"
              :layout="prefs.layout"
              :is-loading="sampleLoader.isLoading.value"
              :selection-enabled="false"
              :show-checkboxes="false"
              :show-label-rail="false"
              :show-bottom-bar="false"
              activation-mode="open"
              @open-item="openSampleDetail"
              @load-more="sampleLoader.loadMore()"
            />
            <BrowserSidebar
              :panels="datasetPanels"
              :context="browserSidebarContext as unknown as Record<string, unknown>"
              :interaction="datasetInteraction"
              :collapsed="prefs.sidebarCollapsed"
              @update:collapsed="prefs.setSidebarCollapsed"
            />
          </div>

          <!-- Add Sample Modal -->
          <n-modal v-model:show="showAddSampleModal" preset="dialog" title="Add Sample" style="width: 480px">
            <n-form ref="sampleFormRef" :model="sampleForm" :rules="sampleRules" label-placement="top">
              <n-form-item label="Image URIs (comma-separated, optional)" path="image_uris">
                <n-input v-model:value="sampleForm.image_uris" placeholder="e.g. s3://bucket/img1.jpg, s3://bucket/img2.jpg" />
              </n-form-item>
              <n-form-item label="Upload Image (optional)">
                <div>
                  <input type="file" accept="image/*" style="display: none" ref="fileInputRef" @change="onFileChange" />
                  <n-button @click="(fileInputRef as HTMLInputElement)?.click()">Choose Image</n-button>
                  <n-image v-if="uploadPreviewUrl" :src="uploadPreviewUrl" width="80" height="80" object-fit="cover" style="margin-top: 8px; border-radius: 4px" />
                </div>
              </n-form-item>
              <n-form-item label="Metadata (JSON)" path="metadata_raw">
                <n-input
                  v-model:value="sampleForm.metadata_raw"
                  type="textarea"
                  placeholder='{"key": "value"}'
                  :autosize="{ minRows: 3, maxRows: 6 }"
                />
              </n-form-item>
            </n-form>
            <template #action>
              <n-button @click="showAddSampleModal = false">Cancel</n-button>
              <n-button type="primary" :loading="uploadingImage" @click="submitSample">
                Create
              </n-button>
            </template>
          </n-modal>
        </n-tab-pane>

        <!-- ============================================================ -->
        <!-- TAB 2: Export -->
        <!-- ============================================================ -->
        <n-tab-pane name="export" tab="Export">
          <div style="display: flex; gap: 12px; margin-bottom: 16px">
            <n-button type="default" :loading="exportLoading" @click="previewExport">
              Preview Export
            </n-button>
            <n-button type="primary" :loading="persistLoading" @click="doPersistExport">
              Persist Export
            </n-button>
          </div>

          <template v-if="exportData">
            <n-card title="Export Preview" size="small">
              <n-scrollbar style="max-height: 400px">
                <pre style="margin: 0; font-size: 12px; white-space: pre-wrap; word-break: break-all">{{ exportJson }}</pre>
              </n-scrollbar>
            </n-card>
          </template>

          <n-empty v-else description="Click 'Preview Export' to load export data." style="margin-top: 32px" />
        </n-tab-pane>

        <!-- ============================================================ -->
        <!-- TAB 3: Feature Ops -->
        <!-- ============================================================ -->
        <n-tab-pane name="feature-ops" tab="Feature Ops">
          <n-space vertical size="large">

            <!-- ---- Panel 0: Embedding Config ---- -->
            <n-card title="Embedding Config" size="small">
              <n-space vertical size="medium">
                <n-form-item label="Embedding Model">
                  <n-select
                    v-model:value="embedConfigModel"
                    :options="[{ label: 'CLIP ViT-B/32 (512-dim)', value: 'openai/clip-vit-base-patch32' }]"
                    style="width: 320px"
                  />
                </n-form-item>
                <n-button
                  type="primary"
                  :loading="embedConfigLoading"
                  @click="doApplyEmbedConfig"
                >
                  Apply &amp; Re-embed
                </n-button>
                <n-alert v-if="embedConfigSaved" type="success" :show-icon="false" style="margin-top: 8px">
                  Config saved. Re-embedding started in background.
                </n-alert>
              </n-space>
            </n-card>

            <!-- ---- Panel 1: Extract Features ---- -->
            <n-card title="Extract Features" size="small">
              <n-button type="primary" :loading="extractFeaturesLoading" @click="doExtractFeatures">
                Extract Features
              </n-button>
              <template v-if="extractFeaturesResult">
                <n-space style="margin-top: 16px">
                  <n-statistic label="Job" :value="extractFeaturesResult.id" />
                  <n-statistic label="Status" :value="extractFeaturesResult.status" />
                  <n-statistic label="Processed" :value="Number(extractFeaturesResult.summary.processed || 0)" />
                </n-space>
                <n-text depth="3" style="display: block; margin-top: 8px">
                  Embedding model: {{ String(extractFeaturesResult.summary.embedding_model || embedConfigModel) }}
                </n-text>
              </template>
            </n-card>

            <!-- ---- Panel 2: Similarity Search ---- -->
            <n-card title="Similarity Search" size="small">
              <template #header-extra>
                <n-tag type="warning">Mock Data</n-tag>
              </template>
              <n-space align="center">
                <n-select
                  v-model:value="similaritySampleId"
                  :options="sampleSelectOptions"
                  placeholder="Select a sample"
                  style="width: 280px"
                  clearable
                />
                <n-button
                  type="primary"
                  :loading="similarityLoading"
                  :disabled="!similaritySampleId"
                  @click="doSimilaritySearch"
                >
                  Search
                </n-button>
              </n-space>
              <template v-if="similarityResult">
                <n-data-table
                  :columns="neighborColumns"
                  :data="similarityResult.neighbors"
                  :bordered="true"
                  :single-line="false"
                  style="margin-top: 16px"
                />
              </template>
            </n-card>

            <!-- ---- Panel 3: Selection Metrics ---- -->
            <n-card title="Selection Metrics" size="small">
              <template #header-extra>
                <n-tag type="warning">Mock Data</n-tag>
              </template>
              <n-button type="primary" :loading="selectionMetricsLoading" @click="doSelectionMetrics">
                Load Selection Metrics
              </n-button>
              <template v-if="selectionMetricsRows.length > 0">
                <n-data-table
                  :columns="selectionMetricsColumns"
                  :data="selectionMetricsRows"
                  :bordered="true"
                  :single-line="false"
                  style="margin-top: 16px"
                />
              </template>
            </n-card>

            <!-- ---- Panel 4: Uncovered Clusters ---- -->
            <n-card title="Uncovered Clusters" size="small">
              <template #header-extra>
                <n-tag type="warning">Mock Data</n-tag>
              </template>
              <n-button type="primary" :loading="uncoveredClustersLoading" @click="doUncoveredClusters">
                Load Uncovered Clusters
              </n-button>
              <template v-if="uncoveredClustersResult">
                <n-data-table
                  :columns="clusterColumns"
                  :data="uncoveredClustersResult.clusters"
                  :bordered="true"
                  :single-line="false"
                  style="margin-top: 16px"
                />
              </template>
            </n-card>

          </n-space>
        </n-tab-pane>

        <!-- ============================================================ -->
        <!-- TAB 4: Annotate -->
        <!-- ============================================================ -->
        <n-tab-pane name="annotate" tab="Annotate">
          <template v-if="dataset?.ls_project_url">
            <iframe
              :src="dataset.ls_project_url"
              style="width: 100%; height: calc(100vh - 200px); border: 1px solid #eee; border-radius: 8px;"
              allow="clipboard-read; clipboard-write"
            />
            <div style="margin-top: 8px; display: flex; align-items: center; gap: 8px">
              <n-text depth="3" style="font-size: 12px">
                Label Studio Project #{{ dataset.ls_project_id }}
              </n-text>
              <n-button text size="small" tag="a" :href="dataset.ls_project_url" target="_blank">
                Open in new tab ↗
              </n-button>
            </div>
          </template>
          <template v-else>
            <n-result
              status="info"
              title="Label Studio URL Not Configured"
              description="The server does not have a Label Studio URL configured. Contact your administrator."
            />
          </template>
        </n-tab-pane>
      </n-tabs>

      <SampleDetailDrawer
        :sampleId="selectedSampleId"
        :datasetId="id"
        :labelSpace="labelSpace"
        :show="selectedSampleId !== null"
        @close="selectedSampleId = null"
        @select-sample="(sid: string) => { selectedSampleId = sid }"
      />
    </template>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, h, watch, onMounted, provide } from "vue";
import { useRoute, useRouter } from "vue-router";
import { useQuery, useQueryClient } from "@tanstack/vue-query";
import { useMessage, type FormInst, type FormRules, type DataTableColumns } from "naive-ui";
import { api } from "../api";
import { resolveImageUris } from "../utils/imageAdapters";
import type { BrowserItem, Dataset } from "../types";
import SampleDetailDrawer from "../components/SampleDetailDrawer.vue";
import SampleBrowser from "../components/sample-browser/SampleBrowser.vue";
import BrowserSidebar from "../components/sample-browser/BrowserSidebar.vue";
import { datasetPanels } from "../components/classify/sidebarConfig";
import { useSampleBrowserPrefs } from "../stores/sampleBrowser";
import { useSampleLoader } from "../composables/useSampleLoader";
import { useBrowserFilter } from "../composables/useBrowserFilter";
import {
  reduceCollectionIntent,
  reduceLabelFilterIntent,
  type SidebarWidgetInteractionContext,
  type SidebarWidgetInteractionState,
} from "../components/classify/widgetContract";
import type { DatasetExport, ExtractFeaturesResponse, SimilarityResponse, SelectionMetricsResponse, UncoveredHintsResponse } from "../api";

// ---------------------------------------------------------------------------
// Route / Router
// ---------------------------------------------------------------------------
const route = useRoute();
const router = useRouter();
const message = useMessage();
const qc = useQueryClient();
const prefs = useSampleBrowserPrefs();

const id = computed(() => String(route.params.id));

// ---------------------------------------------------------------------------
// Dataset fetch
// ---------------------------------------------------------------------------
const datasetQuery = useQuery({
  queryKey: computed(() => ["dataset", id.value]),
  queryFn: () => api.getDataset(id.value),
  retry: false,
});

const dataset = computed(() => datasetQuery.data.value as Dataset & { ls_project_url?: string | null });

// ---------------------------------------------------------------------------
// Drawer state
// ---------------------------------------------------------------------------
const selectedSampleId = ref<string | null>(null);
const labelSpace = computed(() => dataset.value?.task_spec?.label_space ?? []);

// ---------------------------------------------------------------------------
// Samples tab
// ---------------------------------------------------------------------------
const sampleLoader = useSampleLoader({ datasetId: id });

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
  }))
);

const datasetInteractionState = ref<SidebarWidgetInteractionState>({
  activeLabelFilter: null,
  selectedLabels: [],
  collections: {},
});

const datasetInteraction = computed<SidebarWidgetInteractionContext>(() => ({
  state: datasetInteractionState.value,
  dispatch: (intent) => {
    datasetInteractionState.value = {
      ...datasetInteractionState.value,
      activeLabelFilter: reduceLabelFilterIntent(datasetInteractionState.value.activeLabelFilter, intent),
      collections: reduceCollectionIntent(datasetInteractionState.value.collections, intent),
    };
  },
}));

const { filteredItems: filteredSamples } = useBrowserFilter(browserSamples, datasetInteractionState);

const browserSidebarStats = computed(() => {
  const labelCounts: Record<string, number> = {};
  let annotatedSamples = 0;

  for (const sample of sampleLoader.samples.value) {
    const label = sample.latest_annotation?.label ?? null;
    if (!label) {
      continue;
    }
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

const browserSidebarDashboard = {
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

const browserSidebarContext = computed(() => ({
  totalLoaded: sampleLoader.samples.value.length,
  filteredCount: filteredSamples.value.length,
}));

const featureSamplesQuery = useQuery({
  queryKey: computed(() => ["feature-samples", id.value]),
  queryFn: () => api.listSamples(id.value, 0, 100),
  enabled: computed(() => !!id.value),
});

// Add Sample form
const showAddSampleModal = ref(false);
const sampleFormRef = ref<FormInst | null>(null);
const sampleForm = ref({ image_uris: "", metadata_raw: "" });

const sampleRules: FormRules = {
  image_uris: [],
};

const uploadFile = ref<File | null>(null);
const uploadPreviewUrl = ref<string | null>(null);
const uploadingImage = ref(false);
const fileInputRef = ref<HTMLInputElement | null>(null);

function onFileChange(e: Event) {
  const target = e.target as HTMLInputElement;
  const file = target.files?.[0] ?? null;
  uploadFile.value = file;
  if (uploadPreviewUrl.value) {
    URL.revokeObjectURL(uploadPreviewUrl.value);
    uploadPreviewUrl.value = null;
  }
  if (file) {
    uploadPreviewUrl.value = URL.createObjectURL(file);
  }
}

function submitSample() {
  sampleFormRef.value?.validate(async (errors) => {
    if (errors) return;
    let metadata: Record<string, unknown> = {};
    if (sampleForm.value.metadata_raw.trim()) {
      try {
        metadata = JSON.parse(sampleForm.value.metadata_raw) as Record<string, unknown>;
      } catch {
        message.error("Metadata must be valid JSON");
        return;
      }
    }
    const textUris = sampleForm.value.image_uris.split(",").map((s: string) => s.trim()).filter(Boolean);

    try {
      const newSample = await api.createSample(id.value, { image_uris: textUris, metadata });

      if (uploadFile.value) {
        uploadingImage.value = true;
        try {
          await api.uploadSampleImage(newSample.id, uploadFile.value);
        } finally {
          uploadingImage.value = false;
        }
      }

      sampleLoader.reset();
      qc.invalidateQueries({ queryKey: ["feature-samples", id.value] });
      message.success("Sample created");
      showAddSampleModal.value = false;
      sampleForm.value = { image_uris: "", metadata_raw: "" };
      uploadFile.value = null;
      if (uploadPreviewUrl.value) {
        URL.revokeObjectURL(uploadPreviewUrl.value);
      }
      uploadPreviewUrl.value = null;
    } catch (e) {
      message.error(`Failed to create sample: ${(e as Error).message}`);
    }
  });
}

function openSampleDetail(sampleId: string) {
  selectedSampleId.value = sampleId;
}

// ---------------------------------------------------------------------------
// Export tab
// ---------------------------------------------------------------------------
const exportData = ref<DatasetExport | null>(null);
const exportLoading = ref(false);
const persistLoading = ref(false);

const exportJson = computed(() =>
  exportData.value ? JSON.stringify(exportData.value, null, 2) : ""
);

async function previewExport() {
  exportLoading.value = true;
  try {
    exportData.value = await api.getExport(id.value);
  } catch (e) {
    message.error(`Export preview failed: ${(e as Error).message}`);
  } finally {
    exportLoading.value = false;
  }
}

async function doPersistExport() {
  persistLoading.value = true;
  try {
    const res = await api.persistExport(id.value);
    message.success(`Export persisted: ${res.uri}`);
  } catch (e) {
    message.error(`Persist failed: ${(e as Error).message}`);
  } finally {
    persistLoading.value = false;
  }
}

// ---------------------------------------------------------------------------
// Active tab
// ---------------------------------------------------------------------------
const activeTab = ref("samples");

onMounted(() => {
  void sampleLoader.loadMore();
});

// Reset export state on dataset change
watch(id, () => {
  exportData.value = null;
});

// Revoke object URL when Add Sample modal is closed
watch(showAddSampleModal, (open) => {
  if (!open && uploadPreviewUrl.value) {
    URL.revokeObjectURL(uploadPreviewUrl.value);
    uploadPreviewUrl.value = null;
    uploadFile.value = null;
  }
});

// ---------------------------------------------------------------------------
// Feature Ops tab
// ---------------------------------------------------------------------------

// --- Embedding Config ---
const embedConfigModel = ref("openai/clip-vit-base-patch32");
const embedConfigDimension = ref(512);
const embedConfigLoading = ref(false);
const embedConfigSaved = ref(false);

async function doApplyEmbedConfig() {
  embedConfigLoading.value = true;
  embedConfigSaved.value = false;
  try {
    await api.updateEmbedConfig(id.value, { model: embedConfigModel.value, dimension: embedConfigDimension.value });
    await api.extractFeatures(id.value, true);
    embedConfigSaved.value = true;
  } finally {
    embedConfigLoading.value = false;
  }
}

// --- Extract Features ---
const extractFeaturesLoading = ref(false);
const extractFeaturesResult = ref<ExtractFeaturesResponse | null>(null);

async function doExtractFeatures() {
  extractFeaturesLoading.value = true;
  try {
    extractFeaturesResult.value = await api.extractFeatures(id.value);
  } catch (e) {
    message.error(`Extract features failed: ${(e as Error).message}`);
  } finally {
    extractFeaturesLoading.value = false;
  }
}

// --- Similarity Search ---
const similarityLoading = ref(false);
const similaritySampleId = ref<string | null>(null);
const similarityResult = ref<SimilarityResponse | null>(null);

const sampleSelectOptions = computed(() =>
  (featureSamplesQuery.data.value?.items ?? []).map((s) => ({
    label: `${s.id.slice(0, 8)}… — ${s.image_uris.length} image(s)`,
    value: s.id,
  }))
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
    similarityResult.value = await api.getSimilarity(id.value, similaritySampleId.value);
  } catch (e) {
    message.error(`Similarity search failed: ${(e as Error).message}`);
  } finally {
    similarityLoading.value = false;
  }
}

// --- Selection Metrics ---
const selectionMetricsLoading = ref(false);
const selectionMetricsResult = ref<SelectionMetricsResponse | null>(null);

interface SelectionMetricsRow {
  sample_id: string;
  uniqueness: number;
  representativeness: number;
}

const selectionMetricsRows = computed<SelectionMetricsRow[]>(() => {
  if (!selectionMetricsResult.value) return [];
  const { uniqueness, representativeness } = selectionMetricsResult.value;
  return Object.keys(uniqueness).map((sid) => ({
    sample_id: sid,
    uniqueness: uniqueness[sid],
    representativeness: representativeness[sid] ?? 0,
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
    selectionMetricsResult.value = await api.getSelectionMetrics(id.value);
  } catch (e) {
    message.error(`Selection metrics failed: ${(e as Error).message}`);
  } finally {
    selectionMetricsLoading.value = false;
  }
}

// --- Uncovered Clusters ---
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
    uncoveredClustersResult.value = await api.getUncoveredHints(id.value);
  } catch (e) {
    message.error(`Uncovered clusters failed: ${(e as Error).message}`);
  } finally {
    uncoveredClustersLoading.value = false;
  }
}

</script>

<style scoped>
.ds-samples-layout {
  display: flex;
  height: 600px;
  min-height: 0;
  overflow: hidden;
}
</style>
