<template>
  <div class="classify-view" :style="themeStyleVars">
    <div class="classify-header">
      <n-button text @click="router.push(`/datasets/${datasetId}`)">
        <template #icon>
          <span>&#8592;</span>
        </template>
        Back
      </n-button>
      <n-divider vertical />
      <n-text tag="h2" style="margin: 0; font-size: 18px; font-weight: 600">
        {{ datasetQuery.data.value?.name ?? datasetId }}
      </n-text>
      <n-tag v-if="isReviewMode" type="warning" size="small">Prediction Review Mode</n-tag>
      <div style="margin-left: auto; display: flex; align-items: center; gap: 12px">
        <n-text depth="3" style="white-space: nowrap">View</n-text>
        <n-radio-group v-model:value="prefs.layout" size="small">
          <n-radio-button value="grid">Grid</n-radio-button>
          <n-radio-button value="list">List</n-radio-button>
        </n-radio-group>
        <n-text depth="3" style="white-space: nowrap">Image size</n-text>
        <n-slider v-model:value="prefs.thumbSize" :min="64" :max="256" :step="8" style="width: 160px" />
        <n-text depth="3" style="white-space: nowrap">{{ prefs.thumbSize }}px</n-text>
      </div>
    </div>

    <n-grid :cols="2" :x-gap="12" class="workflow-grid">
      <n-gi>
        <n-card title="Training" size="small">
          <n-space vertical>
            <n-select
              v-model:value="selectedPresetId"
              :options="presetOptions"
              placeholder="Select training preset"
              filterable
            />
            <n-space>
              <n-button
                type="primary"
                :disabled="!selectedPresetId"
                :loading="startTrainingMutation.isPending.value"
                @click="startTraining"
              >
                Start Training
              </n-button>
              <n-button @click="router.push('/tasks')">Open Task Explorer</n-button>
            </n-space>
            <n-text v-if="activeTrainingJob" depth="3">
              Active training: {{ activeTrainingJob.id }} ({{ activeTrainingJob.status }})
            </n-text>
          </n-space>
        </n-card>
      </n-gi>
      <n-gi>
        <n-card title="Prediction Review" size="small">
          <n-space vertical>
            <n-select
              v-model:value="selectedModelId"
              :options="modelOptions"
              placeholder="Select model"
              filterable
            />
            <n-input v-model:value="modelVersionTag" placeholder="Optional model version" />
            <n-space>
              <n-button
                type="primary"
                :disabled="!selectedModelId"
                :loading="runPredictionsMutation.isPending.value"
                @click="runPredictions"
              >
                Run Predictions
              </n-button>
              <n-button
                v-if="activePredictionJob && ['queued', 'running'].includes(activePredictionJob.status.toLowerCase())"
                type="warning"
                :loading="cancelPredictionMutation.isPending.value"
                @click="cancelPrediction"
              >
                Cancel
              </n-button>
            </n-space>
            <n-text v-if="activePredictionJob" depth="3">
              Active prediction: {{ activePredictionJob.id }} ({{ activePredictionJob.status }})
              <template v-if="formatPredictionJobProgress(activePredictionJob)">
                &middot; {{ formatPredictionJobProgress(activePredictionJob) }} processed
              </template>
            </n-text>
          </n-space>
        </n-card>
      </n-gi>
    </n-grid>

    <n-card v-if="predictionJobs.length > 0" title="Recent Prediction Jobs" size="small" class="jobs-card">
      <n-data-table :columns="predictionJobColumns" :data="predictionJobs" :bordered="true" :max-height="220" />
    </n-card>

    <div class="classify-body">
      <div ref="browserShellRef" class="classify-browser-shell" tabindex="-1" @keydown="onKeyDown">
        <SampleBrowser
          ref="gridRef"
          :items="filteredBrowserItems"
          :total-count="activeTotalCount"
          :thumb-size="prefs.thumbSize"
          :layout="prefs.layout"
          :is-loading="activeGridLoading"
          :selection-enabled="true"
          :show-checkboxes="true"
          :show-label-rail="true"
          :show-bottom-bar="true"
          activation-mode="select"
          @select="onBrowserSelect"
          @load-more="onGridLoadMore"
        >
          <template #label-rail>
            <div class="classify-label-panel">
              <input
                v-model="labelSearch"
                class="classify-label-search"
                placeholder="Search labels..."
                @keydown.stop
              />
              <div class="classify-label-list">
                <div
                  v-for="(label, idx) in filteredLabels"
                  :key="label"
                  class="classify-label-item"
                  @click="applyLabelToSelection(label)"
                  :title="label"
                >
                  <span class="classify-label-dot" :style="{ background: labelColor(label) }" />
                  <span class="classify-label-name">{{ label }}</span>
                  <span v-if="idx < 9" class="classify-label-shortcut">{{ idx + 1 }}</span>
                </div>
              </div>
              <button v-if="!isReviewMode" class="classify-label-add" @click="showAddLabelModal = true">
                + Add label
              </button>
            </div>
          </template>
          <template #bar-left>
            <template v-if="isReviewMode">
              <n-button size="tiny" :loading="syncCollectionMutation.isPending.value" @click="syncCollectionToLs">
                Sync to LS
              </n-button>
              <n-button size="tiny" @click="resetReviewEdits">Reset Edits</n-button>
              <n-button size="tiny" @click="clearPredictionReview">Back to Annotation</n-button>
            </template>
            <template v-else>
              <n-select
                v-model:value="labelFilter"
                :options="filterOptions"
                placeholder="Filter by label"
                size="tiny"
                clearable
                style="width: 160px"
              />
              <n-select v-model:value="orderBy" :options="orderOptions" size="tiny" style="width: 130px" />
            </template>
          </template>
          <template #bar-right>
            <button class="classify-submit-btn" :disabled="isSubmitting || browserSubmitCount === 0" @click="submitFromGrid">
              {{ isSubmitting ? "Submitting..." : `Submit ${browserSubmitCount}` }}
            </button>
          </template>
        </SampleBrowser>
      </div>

      <ClassifySidebar
        :panels="mergedPanels"
        :context="dashboardContext"
        :interaction="sidebarInteraction"
        :collapsed="prefs.sidebarCollapsed"
        @update:collapsed="prefs.setSidebarCollapsed"
      />
    </div>

    <n-modal v-model:show="showAddLabelModal" preset="dialog" title="Add New Label">
      <n-input v-model:value="newLabelName" placeholder="Enter label name" @keyup.enter="addNewLabel" />
      <template #action>
        <n-button @click="showAddLabelModal = false">Cancel</n-button>
        <n-button
          type="primary"
          :loading="addLabelMutation.isPending.value"
          :disabled="!newLabelName.trim()"
          @click="addNewLabel"
        >
          Add
        </n-button>
      </template>
    </n-modal>

    <TaskInsightModal
      :show="showTaskModal"
      :task="activeTaskSummary"
      :handoff-enabled="taskHandoffEnabled"
      @update:show="showTaskModal = $event"
      @toggle-handoff="taskHandoffEnabled = $event"
    />
  </div>
</template>

<script setup lang="ts">
import { ref, computed, inject, onMounted, watch, provide, h, type Ref } from "vue";
import { useRoute, useRouter } from "vue-router";
import { useQuery, useMutation, useQueryClient } from "@tanstack/vue-query";
import type { DataTableColumns, SelectOption } from "naive-ui";
import {
  NButton,
  NSpace,
  NTag,
  NText,
  NSlider,
  NDivider,
  NSelect,
  NModal,
  NInput,
  NRadioGroup,
  NRadioButton,
  useMessage,
  useDialog,
  useThemeVars,
} from "naive-ui";
import { bulkCreateAnnotations, syncAnnotationsToLs } from "../api";
import { getDataset, updateLabelSpace } from "@platform/web-data/datasets";
import { getSample, listSamplesWithLabels } from "@platform/web-data/samples";
import { listModels, listJobs, listPresets, createJob } from "@platform/web-data/models";
import {
  listPredictionJobs,
  listPredictionJobPredictions,
  runPredictions as runPredictionsApi,
  getPredictionJob,
  cancelPredictionJob,
  createPredictionCollection,
  syncPredictionCollection,
  createReviewAction as createReviewActionApi,
  saveReviewAnnotations,
} from "@platform/web-data/predictions";
import { queryWaferPoints } from "@platform/web-data/agent";
import type {
  AnnotationGridItem,
  BrowserItem,
  BulkAnnotationRequest,
  BulkAnnotationResponse,
  Dataset,
  JobStatus,
  Model,
  PredictionCollection,
  PredictionJob,
  PredictionResult,
  Sample,
  SampleWithLabels,
  SaveReviewAnnotationItem,
  SyncResult,
  TaskTrackerSummary,
  TrainingJob,
  WaferPoint,
} from "../types";
import { resolveImageUris } from "../utils/imageAdapters";
import { useSampleLoader } from "../composables/useSampleLoader";
import { useBrowserFilter } from "../composables/useBrowserFilter";
import { SampleBrowser } from "@platform/web-ui";
import ClassifySidebar from "../components/classify/ClassifySidebar.vue";
import TaskInsightModal from "../components/TaskInsightModal.vue";
import { defaultPanels, mergePanels, type SidebarPanelDescriptor } from "../components/classify/sidebarConfig";
import {
  reduceCollectionIntent,
  reduceLabelFilterIntent,
  type SidebarWidgetIntent,
  type SidebarWidgetInteractionContext,
  type SidebarWidgetInteractionState,
} from "../components/classify/widgetContract";
import { useClassifyDashboard } from "../composables/useClassifyDashboard";
import { GLOBAL_AGENT_PANELS_KEY } from "../composables/useGlobalAgent";
import { useOrgStore } from "../stores/org";
import { useSampleBrowserPrefs } from "../stores/sampleBrowser";

interface ReviewRow {
  key: string;
  prediction_id: string | null;
  sample_id: string;
  predicted_label: string;
  final_label: string;
  confidence: number | null;
}

type HydratedSample = Sample & {
  latest_annotation?: { label?: string | null } | null;
};

const route = useRoute();
const router = useRouter();
const datasetId = computed(() => route.params.id as string);
const message = useMessage();
const dialog = useDialog();
const themeVars = useThemeVars();
const queryClient = useQueryClient();
const orgStore = useOrgStore();
const prefs = useSampleBrowserPrefs();
const PREVIEW_HYDRATION_CAP = 50;

const themeStyleVars = computed(() => ({
  "--cv-bg": themeVars.value.bodyColor,
  "--cv-card-bg": themeVars.value.cardColor,
  "--cv-text": themeVars.value.textColor1,
  "--cv-text-secondary": themeVars.value.textColor3,
  "--cv-text-disabled": themeVars.value.textColorDisabled,
  "--cv-border": themeVars.value.borderColor,
  "--cv-divider": themeVars.value.dividerColor,
  "--cv-hover": themeVars.value.hoverColor,
  "--cv-primary": themeVars.value.primaryColor,
  "--cv-primary-hover": themeVars.value.primaryColorHover,
}));

const datasetQuery = useQuery({
  queryKey: computed(() => ["dataset", datasetId.value]),
  queryFn: () => getDataset(datasetId.value),
  retry: false,
});

const selectedDataset = computed<Dataset | undefined>(() => datasetQuery.data.value);

const labelSpace = computed<string[]>(() => selectedDataset.value?.task_spec?.label_space ?? []);

const labelFilter = ref<string | null>(null);
const orderBy = ref<string>("id");

const filterOptions = computed(() =>
  [
    { label: "All", value: null as string | null },
    { label: "Unlabeled", value: "__unlabeled__" as string | null },
    ...labelSpace.value.map((l) => ({ label: l, value: l as string | null })),
  ] as SelectOption[],
);

const orderOptions = [
  { label: "Default (id)", value: "id" },
  { label: "By Label", value: "label" },
  { label: "Newest First", value: "created_at" },
] as SelectOption[];

const { samples, totalCount, isLoading, loadMore, reset: resetLoader } = useSampleLoader({
  datasetId: datasetId.value,
  pageSize: 100,
  labelFilter,
  orderBy,
});

onMounted(() => {
  resetLoader();

  if (route.query.previewPersistSession) {
    message.success('Dataset imported from preview session.');
    router.replace({ query: { ...route.query, previewPersistSession: undefined } });
  }

  browserShellRef.value?.focus();
});

const annotationDraft = ref<Record<string, string>>({});
const reviewDraftLabels = ref<Record<string, string>>({});
const gridRef = ref<InstanceType<typeof SampleBrowser> | null>(null);
const browserShellRef = ref<HTMLElement | null>(null);
const selectedIds = ref<Set<string>>(new Set());
const labelSearch = ref("");

const LABEL_COLORS = [
  "#4CAF50",
  "#2196F3",
  "#FF9800",
  "#E91E63",
  "#9C27B0",
  "#00BCD4",
  "#FF5722",
  "#795548",
  "#607D8B",
  "#CDDC39",
];

function labelColor(label: string): string {
  const idx = labelSpace.value.indexOf(label);
  if (idx === -1) return "#9E9E9E";
  return LABEL_COLORS[idx % LABEL_COLORS.length];
}

const filteredLabels = computed(() => {
  if (!labelSearch.value) return labelSpace.value;
  const query = labelSearch.value.toLowerCase();
  return labelSpace.value.filter((label) => label.toLowerCase().includes(query));
});

const annotationGridItems = computed<AnnotationGridItem[]>(() =>
  samples.value.map((s) => ({
    id: s.id,
    imageSrcs: resolveImageUris(s.image_uris ?? []),
    currentLabel: s.latest_annotation?.label ?? null,
    draftLabel: annotationDraft.value[s.id] ?? null,
    predictionLabel: null,
    predictionConfidence: null,
    predictionId: null,
    metadata: s.metadata ?? {},
  })),
);

const selectedModelId = ref<string | null>(null);
const modelVersionTag = ref("");
const predictions = ref<ReviewRow[]>([]);
const activePredictionJob = ref<PredictionJob | null>(null);
const pollingPredictionJob = ref(false);
const reviewSamples = ref<SampleWithLabels[]>([]);
const syncedCollection = ref<PredictionCollection | null>(null);
const syncedCollectionTag = ref<string | null>(null);

const isReviewMode = computed(() => predictions.value.length > 0);

const reviewGridItems = computed<AnnotationGridItem[]>(() => {
  if (!isReviewMode.value) return [];
  const sampleMap = new Map(reviewSamples.value.map((s) => [s.id, s]));
  return predictions.value.map((row) => {
    const sample = sampleMap.get(row.sample_id);
    return {
      id: row.sample_id,
      imageSrcs: resolveImageUris(sample?.image_uris ?? []),
      currentLabel: sample?.latest_annotation?.label ?? null,
      draftLabel: reviewDraftLabels.value[row.sample_id] ?? row.final_label,
      predictionLabel: row.predicted_label,
      predictionConfidence: row.confidence,
      predictionId: row.prediction_id,
      metadata: sample?.metadata ?? {},
    };
  });
});

const activeGridItems = computed<AnnotationGridItem[]>(() =>
  isReviewMode.value ? reviewGridItems.value : annotationGridItems.value,
);

function toAnnotationGridItem(sample: HydratedSample): AnnotationGridItem {
  return {
    id: sample.id,
    imageSrcs: resolveImageUris(sample.image_uris ?? []),
    currentLabel: sample.latest_annotation?.label ?? null,
    draftLabel: null,
    predictionLabel: null,
    predictionConfidence: null,
    predictionId: null,
    metadata: sample.metadata ?? {},
  };
}

const interactionState = ref<SidebarWidgetInteractionState>({
  activeLabelFilter: labelFilter.value,
  selectedLabels: labelFilter.value ? [labelFilter.value] : [],
  collections: {},
});

watch(labelFilter, (nextLabel) => {
  interactionState.value = {
    ...interactionState.value,
    activeLabelFilter: nextLabel,
    selectedLabels: nextLabel ? [nextLabel] : [],
  };
});

const selectedSidebarSampleIds = computed(() => {
  const filterIds = interactionState.value.collections?.["classify-samples"]?.filter.ids ?? [];
  if (filterIds.length > 0) {
    return filterIds;
  }
  return interactionState.value.collections?.["classify-samples"]?.selection.ids ?? [];
});

const selectedSidebarSampleHydrationIds = computed(() => {
  const selectedIds = selectedSidebarSampleIds.value;
  if (selectedIds.length === 0 || selectedIds.length > PREVIEW_HYDRATION_CAP) {
    return [] as string[];
  }
  const activeIds = new Set(activeGridItems.value.map((item) => item.id));
  return selectedIds.filter((id) => !activeIds.has(id));
});

const selectedSidebarHydrationQuery = useQuery({
  queryKey: computed(() => [
    "dataset",
    datasetId.value,
    "selected-sample-hydration",
    selectedSidebarSampleHydrationIds.value.join(","),
  ]),
  queryFn: async () => {
    const samples = await Promise.all(
      selectedSidebarSampleHydrationIds.value.map((sampleId) => getSample(sampleId)),
    );
    return samples;
  },
  enabled: computed(() => selectedSidebarSampleHydrationIds.value.length > 0),
  retry: false,
});

const hydratedGridItems = computed<AnnotationGridItem[]>(() => {
  if (selectedSidebarSampleHydrationIds.value.length === 0) {
    return [];
  }
  return (selectedSidebarHydrationQuery.data.value ?? []).map((sample) => toAnnotationGridItem(sample));
});

const providedGridItems = computed<AnnotationGridItem[]>(() => {
  if (hydratedGridItems.value.length === 0) {
    return activeGridItems.value;
  }
  const merged = new Map(activeGridItems.value.map((item) => [item.id, item] as const));
  hydratedGridItems.value.forEach((item) => {
    if (!merged.has(item.id)) {
      merged.set(item.id, item);
    }
  });
  return Array.from(merged.values());
});

const browserItems = computed<BrowserItem[]>(() =>
  activeGridItems.value.map((item) => ({
    id: item.id,
    imageSrcs: item.imageSrcs,
    metadata: item.metadata as Record<string, unknown>,
    sourceKind: "classify-review" as const,
    currentLabel: item.currentLabel ?? null,
    draftLabel: item.draftLabel ?? null,
    predictionLabel: item.predictionLabel ?? null,
    predictionConfidence: item.predictionConfidence ?? null,
    predictionId: item.predictionId ?? null,
    activationLabel: null,
  })),
);

const { filteredItems: filteredBrowserItems } = useBrowserFilter(
  browserItems,
  interactionState,
  "classify-samples"
);

provide<Ref<AnnotationGridItem[]>>("classify-grid-items", providedGridItems);

const activeTotalCount = computed(() =>
  isReviewMode.value ? reviewGridItems.value.length : totalCount.value,
);

const activeGridLoading = computed(() =>
  isReviewMode.value ? pollingPredictionJob.value : isLoading.value,
);

const { data: models } = useQuery({
  queryKey: computed(() => ["models", orgStore.currentOrgId]),
  queryFn: () => listModels(),
  enabled: computed(() => !!orgStore.currentOrgId),
});

const modelOptions = computed<SelectOption[]>(() => {
  const allModels = models.value ?? [];
  const dataset = selectedDataset.value;
  const filtered = dataset
    ? allModels.filter((m) => {
        const metadata = m.metadata ?? {};
        const datasetTypes = Array.isArray(metadata.dataset_types) ? (metadata.dataset_types as string[]) : [];
        const taskTypes = Array.isArray(metadata.task_types) ? (metadata.task_types as string[]) : [];
        return datasetTypes.includes(dataset.dataset_type) && taskTypes.includes(dataset.task_spec.task_type);
      })
    : allModels;
  const source = filtered.length > 0 ? filtered : allModels;
  return source.map((m) => ({
    label: `${m.name || `${m.id.slice(0, 12)}...`} (${m.dataset_name})`,
    value: m.id,
  }));
});

const selectedModel = computed<Model | undefined>(() =>
  (models.value ?? []).find((m) => m.id === selectedModelId.value),
);

const predictionTarget = computed(() => {
  const targets = selectedModel.value?.metadata?.prediction_targets;
  if (Array.isArray(targets) && typeof targets[0] === "string") {
    return targets[0];
  }
  return "image_classification";
});

const { data: predictionJobsData } = useQuery({
  queryKey: computed(() => ["prediction-jobs", orgStore.currentOrgId]),
  queryFn: listPredictionJobs,
  enabled: computed(() => !!orgStore.currentOrgId),
  refetchInterval: 3000,
});

const predictionJobs = computed(() =>
  (predictionJobsData.value ?? [])
    .filter((job) => job.dataset_id === datasetId.value)
    .slice(0, 10),
);

function predictionResultToReviewRow(item: PredictionResult): ReviewRow {
  return {
    key: item.id ?? item.sample_id,
    prediction_id: item.id,
    sample_id: item.sample_id,
    predicted_label: item.predicted_label,
    final_label: item.predicted_label,
    confidence: item.confidence,
  };
}

async function loadReviewRowsFromJob(job: PredictionJob): Promise<ReviewRow[]> {
  const summaryPredictions = ((job.summary.predictions as PredictionResult[] | undefined) ?? [])
    .filter((item) => !item.error)
    .map(predictionResultToReviewRow);
  if (summaryPredictions.length > 0) {
    return summaryPredictions;
  }
  const fetched = await listPredictionJobPredictions(job.id);
  return fetched.filter((item) => !item.error).map(predictionResultToReviewRow);
}

function asNumber(value: unknown): number | null {
  if (typeof value === "number" && Number.isFinite(value)) return value;
  if (typeof value === "string" && value.trim() !== "") {
    const parsed = Number(value);
    if (Number.isFinite(parsed)) return parsed;
  }
  return null;
}

function getPredictionJobProgress(job: PredictionJob): { processed: number; total: number } | null {
  const status = job.status.toLowerCase();
  const total =
    asNumber(job.summary.total_samples) ?? asNumber(job.summary.total) ?? asNumber(job.sample_ids?.length) ?? null;
  const processed =
    asNumber(job.summary.processed) ??
    asNumber(job.summary.successful) ??
    asNumber(job.summary.completed) ??
    (status === "completed" ? total : 0);
  if (total === null || processed === null || total <= 0) return null;
  return { processed, total };
}

function formatPredictionJobProgress(job: PredictionJob): string {
  const progress = getPredictionJobProgress(job);
  return progress ? `${progress.processed}/${progress.total}` : "-";
}

watch(predictions, async (rows) => {
  if (rows.length === 0) {
    reviewSamples.value = [];
    return;
  }
  try {
    const all: SampleWithLabels[] = [];
    const pageSize = 200;
    let offset = 0;
    let total = Infinity;
    while (offset < total) {
      const result = await listSamplesWithLabels(datasetId.value, offset, pageSize);
      all.push(...result.items);
      total = result.total;
      offset += pageSize;
      if (result.items.length === 0) break;
    }
    reviewSamples.value = all;
  } catch {
    reviewSamples.value = [];
  }
});

const runPredictionsMutation = useMutation({
  mutationFn: () => {
    if (!selectedModelId.value) {
      throw new Error("Model is required");
    }
    return runPredictionsApi({
      model_id: selectedModelId.value,
      dataset_id: datasetId.value,
      model_version: modelVersionTag.value || null,
      target: predictionTarget.value,
    });
  },
  onSuccess: (job) => {
    activePredictionJob.value = job;
    predictions.value = [];
    reviewDraftLabels.value = {};
    taskModalSource.value = "prediction";
    showTaskModal.value = true;
    message.success(`Prediction job submitted: ${job.id}`);
    void pollPredictionJob(job.id);
  },
  onError: (err: Error) => {
    message.error(err.message ?? "Failed to run predictions");
  },
});

const cancelPredictionMutation = useMutation({
  mutationFn: () => {
    if (!activePredictionJob.value) {
      throw new Error("No active prediction job");
    }
    return cancelPredictionJob(activePredictionJob.value.id);
  },
  onSuccess: () => {
    message.warning("Prediction cancellation requested");
  },
  onError: (err: Error) => {
    message.error(err.message ?? "Failed to cancel prediction job");
  },
});

async function pollPredictionJob(jobId: string) {
  pollingPredictionJob.value = true;
  try {
    for (let attempt = 0; attempt < 120; attempt += 1) {
      const job = await getPredictionJob(jobId);
      activePredictionJob.value = job;
      const status = job.status.toLowerCase();
      if (status === "completed") {
        const rows = await loadReviewRowsFromJob(job);
        predictions.value = rows;
        reviewDraftLabels.value = {};
        message.success(`${rows.length} predictions ready for review`);
        return;
      }
      if (status === "failed" || status === "cancelled") {
        message.error(`Prediction job ${status}`);
        return;
      }
      await new Promise((resolve) => window.setTimeout(resolve, 1500));
    }
    message.warning("Prediction job is still running. Refresh later to load results.");
  } finally {
    pollingPredictionJob.value = false;
  }
}

const syncCollectionMutation = useMutation({
  mutationFn: async () => {
    if (!selectedModelId.value || predictions.value.length === 0) {
      throw new Error("Predictions are required before syncing to Label Studio");
    }
    const collection = await createPredictionCollection({
      name: `review-${new Date().toISOString()}`,
      dataset_id: datasetId.value,
      model_id: selectedModelId.value,
      prediction_ids: predictions.value.map((row) => row.prediction_id).filter((id): id is string => !!id),
      model_version: modelVersionTag.value || null,
      target: predictionTarget.value,
      source_job_id: activePredictionJob.value?.id ?? null,
    });
    const syncResult = await syncPredictionCollection(collection.id);
    syncedCollection.value = collection;
    syncedCollectionTag.value = syncResult.sync_tag;
    return syncResult;
  },
  onSuccess: (data) => {
    message.success(`Synced ${data.synced_count} predictions to Label Studio`);
    if (data.failed_count > 0) {
      message.warning(`${data.failed_count} predictions were skipped during sync`);
    }
  },
  onError: (err: Error) => {
    message.error(err.message ?? "Failed to sync predictions to Label Studio");
  },
});

const saveAnnotationsMutation = useMutation({
  mutationFn: async () => {
    if (!selectedModelId.value) {
      throw new Error("Model is required");
    }
    const action = await createReviewActionApi({
      dataset_id: datasetId.value,
      model_id: selectedModelId.value,
      model_version: modelVersionTag.value || null,
      collection_id: syncedCollection.value?.id ?? null,
      sync_tag: syncedCollectionTag.value,
    });
    const items: SaveReviewAnnotationItem[] = predictions.value.map((row) => ({
      sample_id: row.sample_id,
      predicted_label: row.predicted_label,
      final_label: reviewDraftLabels.value[row.sample_id] ?? row.final_label,
      confidence: row.confidence,
      prediction_id: row.prediction_id,
    }));
    return saveReviewAnnotations(action.id, items);
  },
  onSuccess: (data) => {
    message.success(`Saved ${data.created_count} reviewed annotations`);
    clearPredictionReview();
  },
  onError: (err: Error) => {
    message.error(err.message ?? "Failed to save reviewed annotations");
  },
});

function runPredictions() {
  runPredictionsMutation.mutate();
}

function cancelPrediction() {
  cancelPredictionMutation.mutate();
}

function syncCollectionToLs() {
  syncCollectionMutation.mutate();
}

function resetReviewEdits() {
  reviewDraftLabels.value = {};
  predictions.value = predictions.value.map((row) => ({
    ...row,
    final_label: row.predicted_label,
  }));
}

function clearPredictionReview() {
  predictions.value = [];
  reviewDraftLabels.value = {};
  syncedCollection.value = null;
  syncedCollectionTag.value = null;
}

const { data: trainingJobs } = useQuery({
  queryKey: computed(() => ["jobs", orgStore.currentOrgId]),
  queryFn: listJobs,
  refetchInterval: 5000,
  enabled: computed(() => !!orgStore.currentOrgId),
});

const { data: presets } = useQuery({
  queryKey: computed(() => ["presets", orgStore.currentOrgId]),
  queryFn: listPresets,
  enabled: computed(() => !!orgStore.currentOrgId),
});

const presetOptions = computed<SelectOption[]>(() =>
  (presets.value ?? [])
    .filter((p) => {
      if (p.trainable === false) return false;
      const dataset = selectedDataset.value;
      if (!dataset) return true;
      const compatibility = p.compatibility;
      if (!compatibility) return true;
      return compatibility.dataset_types.includes(dataset.dataset_type) && compatibility.task_types.includes(dataset.task_spec.task_type);
    })
    .map((p) => ({ label: p.name, value: p.id })),
);

const selectedPresetId = ref<string | null>(null);
const activeTrainingJobId = ref<string | null>(null);
const activeTrainingJob = computed<TrainingJob | null>(() => {
  if (!activeTrainingJobId.value) return null;
  return (trainingJobs.value ?? []).find((job) => job.id === activeTrainingJobId.value) ?? null;
});

const startTrainingMutation = useMutation({
  mutationFn: () => {
    if (!selectedPresetId.value) {
      throw new Error("Preset is required");
    }
    return createJob(datasetId.value, selectedPresetId.value);
  },
  onSuccess: (job) => {
    activeTrainingJobId.value = job.id;
    taskModalSource.value = "training";
    showTaskModal.value = true;
    message.success(`Training job started: ${job.id}`);
    void queryClient.invalidateQueries({ queryKey: ["jobs", orgStore.currentOrgId] });
  },
  onError: (err: Error) => {
    message.error(err.message ?? "Failed to start training job");
  },
});

function startTraining() {
  startTrainingMutation.mutate();
}

type TaskSource = "training" | "prediction" | null;

const taskModalSource = ref<TaskSource>(null);
const showTaskModal = ref(false);
const taskHandoffEnabled = ref(true);

function toTrainingTaskSummary(job: TrainingJob): TaskTrackerSummary {
  return {
    id: job.id,
    task_kind: "training",
    execution_kind: "prefect",
    display_name: `Training: ${job.preset_id}`,
    display_status: job.status,
    stage: job.status,
    dataset_id: job.dataset_id,
    model_id: null,
    preset_id: job.preset_id,
    created_by: job.created_by,
    created_at: job.created_at,
    updated_at: job.updated_at,
    prefect_state: null,
    work_pool_name: null,
    work_queue_name: null,
    queue_priority: null,
    queue_priority_label: "none",
    queue_depth_ahead: null,
    capacity_status: "unknown",
    pool_concurrency_limit: null,
    pool_slots_used: null,
  };
}

function toPredictionTaskSummary(job: PredictionJob): TaskTrackerSummary {
  const status = job.status.toLowerCase();
  return {
    id: job.id,
    task_kind: "prediction",
    execution_kind: "prefect",
    display_name: `Prediction: ${job.dataset_id.slice(0, 8)}...`,
    display_status: status,
    stage: status,
    dataset_id: job.dataset_id,
    model_id: job.model_id,
    preset_id: null,
    created_by: job.created_by,
    created_at: job.created_at,
    updated_at: job.updated_at,
    prefect_state: null,
    work_pool_name: null,
    work_queue_name: null,
    queue_priority: null,
    queue_priority_label: "none",
    queue_depth_ahead: null,
    capacity_status: "unknown",
    pool_concurrency_limit: null,
    pool_slots_used: null,
  };
}

const activeTaskSummary = computed<TaskTrackerSummary | null>(() => {
  if (taskModalSource.value === "training" && activeTrainingJob.value) {
    if (["queued", "running"].includes(activeTrainingJob.value.status)) {
      return toTrainingTaskSummary(activeTrainingJob.value);
    }
    return null;
  }
  if (taskModalSource.value === "prediction" && activePredictionJob.value) {
    const status = activePredictionJob.value.status.toLowerCase();
    if (["queued", "running"].includes(status)) {
      return toPredictionTaskSummary(activePredictionJob.value);
    }
    return null;
  }
  return null;
});

watch(activeTaskSummary, (task) => {
  if (!task) {
    showTaskModal.value = false;
  }
});

const selectedCount = ref(0);

const browserSubmitCount = computed(() => activeGridItems.value.filter((item) => item.draftLabel != null).length);

const isSubmitting = computed(() =>
  isReviewMode.value ? saveAnnotationsMutation.isPending.value : bulkAnnotateMutation.isPending.value,
);

function onBrowserSelect(ids: Set<string>) {
  selectedIds.value = ids;
  selectedCount.value = ids.size;
}

function applyLabelToSelection(label: string) {
  if (selectedIds.value.size === 0) return;
  const payload = { ids: [...selectedIds.value], label };
  if (isReviewMode.value) {
    const next = { ...reviewDraftLabels.value };
    payload.ids.forEach((id) => {
      next[id] = payload.label;
      const row = predictions.value.find((item) => item.sample_id === id);
      if (row) {
        row.final_label = payload.label;
      }
    });
    reviewDraftLabels.value = next;
    return;
  }
  const next = { ...annotationDraft.value };
  payload.ids.forEach((id) => {
    next[id] = payload.label;
  });
  annotationDraft.value = next;
}

function onGridLoadMore() {
  if (isReviewMode.value) return;
  loadMore();
}

watch(labelFilter, () => {
  selectedCount.value = 0;
  selectedIds.value = new Set();
  gridRef.value?.clearSelection();
});

const annotationDraftCount = computed(() =>
  Object.keys(annotationDraft.value).filter((key) => annotationDraft.value[key]).length,
);

const reviewEditedCount = computed(() =>
  predictions.value.filter((row) => (reviewDraftLabels.value[row.sample_id] ?? row.final_label) !== row.predicted_label).length,
);

const dashboardDraftCount = computed(() =>
  isReviewMode.value ? reviewEditedCount.value : annotationDraftCount.value,
);

provide<Ref<AnnotationGridItem[]>>(
  "pr-grid-items",
  computed(() => (isReviewMode.value ? reviewGridItems.value : [])),
);

const dashboardContext = useClassifyDashboard(
  datasetId,
  dashboardDraftCount,
  selectedCount,
  labelSpace,
);

const waferPointsQuery = useQuery({
  queryKey: computed(() => ["dataset", datasetId.value, "wafer-points"]),
  queryFn: () => queryWaferPoints(datasetId.value),
  retry: false,
});

const globalAgentPanels = inject(GLOBAL_AGENT_PANELS_KEY, ref([]));

const reviewPanel: SidebarPanelDescriptor = {
  id: "prediction-summary",
  component: "prediction-summary",
  title: "Prediction Summary",
  props: {},
  order: 5,
};

function metadataNumber(metadata: Record<string, unknown>, key: string): number | null {
  const value = metadata[key];
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

function metadataString(metadata: Record<string, unknown>, key: string): string | null {
  const value = metadata[key];
  return typeof value === "string" && value.trim().length > 0 ? value : null;
}

function normalizeWaferPoint(point: WaferPoint): WaferPoint | null {
  if (typeof point.id !== "string" || point.id.trim().length === 0) {
    return null;
  }

  const x = Number(point.x);
  const y = Number(point.y);
  if (!Number.isFinite(x) || !Number.isFinite(y)) {
    return null;
  }

  const value = Number(point.value);

  return {
    id: point.id,
    x,
    y,
    ...(Number.isFinite(value) ? { value } : {}),
  };
}

const waferPoints = computed<WaferPoint[]>(() => {
  const points = waferPointsQuery.data.value?.points ?? [];
  return points
    .map((point) => normalizeWaferPoint(point))
    .filter((point): point is WaferPoint => point !== null);
});



const staticPanels = computed(() => {
  const basePanels = isReviewMode.value ? [reviewPanel, ...defaultPanels] : defaultPanels;
  return basePanels.map((panel) => {
    if (panel.id === "wafer-map") {
      return {
        ...panel,
        props: {
          ...panel.props,
          data: {
            inline: {
              points: waferPoints.value,
            },
          },
        },
      };
    }

    return panel;
  });
});

const mergedPanels = computed(() =>
  mergePanels(staticPanels.value, globalAgentPanels.value),
);

function handleSidebarIntent(intent: SidebarWidgetIntent): void {
  interactionState.value = {
    ...interactionState.value,
    activeLabelFilter: reduceLabelFilterIntent(interactionState.value.activeLabelFilter, intent),
    collections: reduceCollectionIntent(interactionState.value.collections, intent),
  };
  if (!isReviewMode.value) {
    labelFilter.value = interactionState.value.activeLabelFilter;
  }
}



const sidebarInteraction = computed<SidebarWidgetInteractionContext>(() => ({
  state: interactionState.value,
  dispatch: handleSidebarIntent,
}));

const syncToLsMutation = useMutation({
  mutationFn: () => syncAnnotationsToLs(datasetId.value),
  onSuccess: (data: SyncResult) => {
    message.success(`Synced ${data.synced_count} annotations to Label Studio`);
  },
  onError: (err: Error) => {
    message.error(err.message ?? "Failed to sync to Label Studio");
  },
});

const bulkAnnotateMutation = useMutation({
  mutationFn: (body: BulkAnnotationRequest) => bulkCreateAnnotations(datasetId.value, body),
  onSuccess: (data: BulkAnnotationResponse) => {
    message.success(`Created ${data.created} annotations`);
    if (datasetQuery.data.value?.ls_project_id) {
      syncToLsMutation.mutate();
    }
    annotationDraft.value = {};
    selectedIds.value = new Set();
    gridRef.value?.clearSelection();
    resetLoader();
    void queryClient.invalidateQueries({ queryKey: ["annotation-stats", datasetId.value] });
  },
  onError: (err: Error) => {
    message.error(err.message ?? "Failed to create annotations");
  },
});

function submitFromGrid() {
  if (isReviewMode.value) {
    saveAnnotationsMutation.mutate();
    return;
  }
  const entries = Object.entries(annotationDraft.value).filter(([, label]) => label);
  if (entries.length === 0) {
    message.warning("No annotations to submit");
    return;
  }
  dialog.warning({
    title: "Submit annotations?",
    content: `This will create ${entries.length} annotation(s). Continue?`,
    positiveText: "Submit",
    negativeText: "Cancel",
    onPositiveClick: () => {
      bulkAnnotateMutation.mutate({
        annotations: entries.map(([sample_id, label]) => ({
          sample_id,
          label,
          annotator: "platform-user",
        })),
      });
    },
  });
}

const predictionJobColumns = computed<DataTableColumns<PredictionJob>>(() => [
  { title: "Job", key: "id", width: 180, render: (row) => `${row.id.slice(0, 16)}...` },
  { title: "Status", key: "status", width: 120 },
  {
    title: "Progress",
    key: "progress",
    width: 120,
    render: (row) => formatPredictionJobProgress(row),
  },
  {
    title: "Actions",
    key: "actions",
    width: 100,
    render: (row) =>
      h(
        NButton,
        {
          size: "small",
          disabled: row.status.toLowerCase() !== "completed",
          onClick: () => void pollPredictionJob(row.id),
        },
        { default: () => "Load" },
      ),
  },
]);

const showAddLabelModal = ref(false);
const newLabelName = ref("");

const addLabelMutation = useMutation({
  mutationFn: (newLabel: string) => {
    const currentLabels = labelSpace.value;
    if (currentLabels.includes(newLabel)) {
      throw new Error(`Label "${newLabel}" already exists`);
    }
    return updateLabelSpace(datasetId.value, [...currentLabels, newLabel]);
  },
  onSuccess: () => {
    message.success(`Added label "${newLabelName.value}"`);
    showAddLabelModal.value = false;
    newLabelName.value = "";
    void datasetQuery.refetch();
  },
  onError: (err: Error) => {
    message.error(err.message ?? "Failed to add label");
  },
});

function addNewLabel() {
  const trimmed = newLabelName.value.trim();
  if (!trimmed) return;
  addLabelMutation.mutate(trimmed);
}

function onKeyDown(e: KeyboardEvent) {
  const el = document.activeElement;
  if (
    el instanceof HTMLInputElement ||
    el instanceof HTMLSelectElement ||
    el instanceof HTMLTextAreaElement ||
    (el instanceof HTMLElement && el.isContentEditable)
  ) {
    return;
  }

  const num = Number.parseInt(e.key, 10);
  if (Number.isNaN(num) || num < 1 || num > 9) return;
  const label = labelSpace.value[num - 1];
  if (!label) return;
  if (selectedIds.value.size === 0) return;
  e.preventDefault();
  applyLabelToSelection(label);
}

watch(datasetId, () => {
  annotationDraft.value = {};
  clearPredictionReview();
  selectedModelId.value = null;
  modelVersionTag.value = "";
  selectedPresetId.value = null;
  activePredictionJob.value = null;
  activeTrainingJobId.value = null;
  labelSearch.value = "";
  labelFilter.value = null;
  orderBy.value = "id";
  selectedIds.value = new Set();
  selectedCount.value = 0;
  gridRef.value?.clearSelection();
  resetLoader();
});

watch(isReviewMode, () => {
  selectedIds.value = new Set();
  selectedCount.value = 0;
  gridRef.value?.clearSelection();
  browserShellRef.value?.focus();
});
</script>

<style scoped>
.classify-view {
  display: flex;
  flex-direction: column;
  height: 100vh;
  padding: 12px;
  box-sizing: border-box;
  color: var(--cv-text);
  gap: 10px;
}

.classify-header {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-shrink: 0;
}

.workflow-grid {
  flex-shrink: 0;
}

.jobs-card {
  flex-shrink: 0;
}

.classify-body {
  display: flex;
  flex: 1;
  min-height: 0;
  gap: 0;
}

.classify-browser-shell {
  flex: 1;
  min-width: 0;
  min-height: 0;
  outline: none;
}

.classify-label-panel {
  display: flex;
  flex-direction: column;
  width: 100%;
  height: 100%;
}

.classify-label-search {
  margin: 8px;
  padding: 6px 8px;
  border: 1px solid var(--cv-border, rgba(255,255,255,0.12));
  border-radius: 4px;
  background: transparent;
  color: var(--cv-text, #fff);
  font-size: 12px;
  outline: none;
}

.classify-label-search::placeholder {
  color: var(--cv-text-disabled, rgba(255,255,255,0.3));
}

.classify-label-list {
  flex: 1;
  overflow-y: auto;
  padding: 0 4px;
}

.classify-label-item {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 6px 8px;
  border-radius: 4px;
  cursor: pointer;
  user-select: none;
  font-size: 12px;
  color: var(--cv-text, #fff);
}

.classify-label-item:hover {
  background: var(--cv-hover, rgba(255,255,255,0.08));
}

.classify-label-dot {
  width: 10px;
  height: 10px;
  border-radius: 50%;
  flex-shrink: 0;
}

.classify-label-name {
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.classify-label-shortcut {
  font-size: 10px;
  color: var(--cv-text-disabled, rgba(255,255,255,0.3));
  flex-shrink: 0;
}

.classify-label-add {
  margin: 4px 8px 8px;
  padding: 6px;
  border: 1px dashed var(--cv-border, rgba(255,255,255,0.12));
  border-radius: 4px;
  background: transparent;
  color: var(--cv-text-secondary, rgba(255,255,255,0.5));
  cursor: pointer;
  font-size: 12px;
}

.classify-label-add:hover {
  border-color: var(--cv-primary, #4098fc);
  color: var(--cv-primary, #4098fc);
}

.classify-submit-btn {
  padding: 6px 16px;
  border: none;
  border-radius: 4px;
  background: var(--cv-primary, #4098fc);
  color: white;
  font-size: 12px;
  font-weight: 600;
  cursor: pointer;
}

.classify-submit-btn:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}

.classify-submit-btn:not(:disabled):hover {
  background: var(--cv-primary-hover, #3080e0);
}

@media (max-width: 1100px) {
  .workflow-grid {
    display: block;
  }
}
</style>
