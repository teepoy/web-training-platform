<template>
  <n-space vertical size="large">
    <template v-if="!orgStore.currentOrgId">
      <div style="padding: 48px; text-align: center;">
        <n-empty description="You are not a member of any organization. Contact an admin." />
      </div>
    </template>
    <template v-else>
      <n-page-header title="Prediction Review">
        <template #subtitle>
          Run predictions, review and edit labels, save as annotation versions, and export.
        </template>
        <template #extra>
          <n-button @click="router.push('/tasks')">Open Task Explorer</n-button>
        </template>
      </n-page-header>

      <!-- Step 1: Setup -->
      <n-card title="1. Setup" size="small">
        <n-space vertical>
          <n-space align="center">
            <n-text style="width: 100px; display: inline-block">Dataset</n-text>
            <n-select
              v-model:value="selectedDatasetId"
              :options="datasetOptions"
              placeholder="Select dataset"
              filterable
              style="width: 300px"
              @update:value="onDatasetChange"
            />
          </n-space>
          <n-space align="center">
            <n-text style="width: 100px; display: inline-block">Model</n-text>
            <n-select
              v-model:value="selectedModelId"
              :options="modelOptions"
              placeholder="Select model"
              filterable
              style="width: 300px"
              :disabled="!selectedDatasetId"
            />
          </n-space>
          <n-space align="center">
            <n-text style="width: 100px; display: inline-block">Version Tag</n-text>
            <n-input
              v-model:value="modelVersionTag"
              placeholder="Optional version tag"
              style="width: 300px"
            />
          </n-space>
          <n-space>
            <n-button
              type="primary"
              :disabled="!selectedDatasetId || !selectedModelId"
              :loading="runPredictionsMutation.isPending.value"
              @click="onRunPredictions"
            >
              Run Predictions
            </n-button>
            <n-button
              v-if="activePredictionJob && ['queued', 'running'].includes(activePredictionJob.status.toLowerCase())"
              type="warning"
              :loading="cancelPredictionMutation.isPending.value"
              @click="onCancelPredictionJob"
            >
              Cancel Active Job
            </n-button>
          </n-space>
          <n-text v-if="activePredictionJob" depth="3">
            Active job: {{ activePredictionJob.id }} ({{ activePredictionJob.status }})
            <template v-if="formatPredictionJobProgress(activePredictionJob)">
              &middot; {{ formatPredictionJobProgress(activePredictionJob) }} processed
            </template>
          </n-text>
        </n-space>
      </n-card>

      <n-card v-if="predictionJobs.length > 0" title="Active & Recent Prediction Jobs" size="small">
        <n-data-table :columns="predictionJobColumns" :data="predictionJobs" :bordered="true" :max-height="260" />
      </n-card>

      <!-- Step 2: Review Predictions (grid gallery for classification datasets) -->
      <n-card
        v-if="reviewGridItems.length > 0 && isClassificationDataset"
        title="2. Review Predictions"
        size="small"
      >
        <template #header-extra>
          <n-space>
            <n-text depth="3">{{ reviewGridItems.length }} predictions</n-text>
            <n-text depth="3">{{ editedCount }} edited</n-text>
          </n-space>
        </template>

        <div class="pr-review-body" :style="themeStyleVars">
          <AnnotationGrid
            ref="gridRef"
            :items="reviewGridItems"
            :total-count="reviewGridItems.length"
            :label-space="labelSpace"
            :thumb-size="160"
            :is-loading="false"
            :submitting="saveAnnotationsMutation.isPending.value"
            :show-add-label="false"
            @select="onGridSelect"
            @apply-label="onGridApplyLabel"
            @submit="onSaveAnnotations"
            @load-more="() => {}"
          >
            <template #bar-left>
              <n-button
                size="tiny"
                :loading="syncCollectionMutation.isPending.value"
                @click="onSyncCollectionToLs"
              >
                Sync to LS
              </n-button>
              <n-button size="tiny" @click="resetEdits">Reset Edits</n-button>
            </template>
          </AnnotationGrid>

          <!-- Sidebar -->
          <ClassifySidebar
            :panels="reviewSidebarPanels"
            :context="dashboardContext"
            v-model:collapsed="sidebarCollapsed"
          />
        </div>

        <n-text v-if="syncedCollectionTag" depth="3" style="margin-top: 8px; display: block;">
          Current LS sync tag: {{ syncedCollectionTag }}
        </n-text>
      </n-card>

      <!-- Step 2 fallback: table for non-classification (VQA, etc.) -->
      <n-card
        v-else-if="predictions.length > 0 && !isClassificationDataset"
        title="2. Review Predictions"
        size="small"
      >
        <template #header-extra>
          <n-space>
            <n-text depth="3">{{ predictions.length }} predictions</n-text>
            <n-text depth="3">{{ editedCount }} edited</n-text>
          </n-space>
        </template>
        <n-space vertical>
          <n-data-table
            :columns="reviewColumns"
            :data="predictions"
            :bordered="true"
            :max-height="480"
            :scroll-x="800"
            virtual-scroll
          />
          <n-space justify="end">
            <n-button @click="resetEdits">Reset All Edits</n-button>
            <n-button
              :disabled="predictions.length === 0"
              :loading="syncCollectionMutation.isPending.value"
              @click="onSyncCollectionToLs"
            >
              Sync Selection to Label Studio
            </n-button>
            <n-button
              type="primary"
              :disabled="predictions.length === 0"
              :loading="saveAnnotationsMutation.isPending.value"
              @click="onSaveAnnotations"
            >
              Save as Annotation Version ({{ predictions.length }} items)
            </n-button>
          </n-space>
          <n-text v-if="syncedCollectionTag" depth="3">
            Current LS sync tag: {{ syncedCollectionTag }}
          </n-text>
        </n-space>
      </n-card>

      <!-- Step 3: History & Export -->
      <n-card title="3. Review History & Export" size="small">
        <n-space vertical>
          <n-space align="center">
            <n-text style="width: 100px; display: inline-block">Dataset</n-text>
            <n-select
              v-model:value="exportDatasetId"
              :options="datasetOptions"
              placeholder="Select dataset to view history"
              filterable
              style="width: 300px"
              @update:value="onExportDatasetChange"
            />
          </n-space>

          <n-spin :show="reviewActionsLoading">
            <n-data-table
              v-if="reviewActions.length > 0"
              :columns="historyColumns"
              :data="reviewActions"
              :bordered="true"
              :max-height="300"
            />
            <n-empty
              v-else-if="exportDatasetId && !reviewActionsLoading"
              description="No review actions found for this dataset"
            />
          </n-spin>
        </n-space>
      </n-card>

      <!-- Export modal -->
      <n-modal v-model:show="showExportModal" preset="card" title="Export Annotation Version" style="width: 640px">
        <n-space vertical>
          <n-space align="center">
            <n-text style="width: 100px; display: inline-block">Format</n-text>
            <n-select
              v-model:value="selectedExportFormat"
              :options="exportFormatOptions"
              style="width: 400px"
            />
          </n-space>
          <n-space>
            <n-button
              :loading="previewExportLoading"
              @click="onPreviewExport"
            >
              Preview JSON
            </n-button>
            <n-button
              type="primary"
              :loading="persistExportMutation.isPending.value"
              @click="onPersistExport"
            >
              Persist to Storage
            </n-button>
          </n-space>
          <n-code
            v-if="exportPreview"
            :code="exportPreview"
            language="json"
            style="max-height: 400px; overflow: auto"
          />
          <n-alert v-if="exportUri" type="success" title="Export persisted">
            URI: {{ exportUri }}
          </n-alert>
        </n-space>
      </n-modal>

      <!-- Delete confirmation -->
      <n-modal
        v-model:show="showDeleteModal"
        preset="dialog"
        title="Delete Review Action"
        type="warning"
        positive-text="Delete"
        negative-text="Cancel"
        :loading="deleteActionMutation.isPending.value"
        @positive-click="confirmDeleteAction"
        @negative-click="showDeleteModal = false"
      >
        <p>Are you sure you want to delete this review action and all its annotation versions?</p>
      </n-modal>

      <!-- Task Insight Modal (auto-opened for active prediction jobs) -->
      <TaskInsightModal
        :show="showTaskModal"
        :task="activeTaskSummary"
        :handoff-enabled="taskHandoffEnabled"
        @update:show="showTaskModal = $event"
        @toggle-handoff="taskHandoffEnabled = $event"
      />
    </template>
  </n-space>
</template>

<script setup lang="ts">
import { ref, computed, h, watch, provide, type Ref } from "vue";
import { useRouter } from "vue-router";
import { useMutation, useQuery, useQueryClient } from "@tanstack/vue-query";
import type { DataTableColumns, SelectOption } from "naive-ui";
import { useMessage, useThemeVars, NButton, NSpace, NTag, NSelect } from "naive-ui";
import { api, listSamplesWithLabels } from "../api";
import type {
  Model,
  Dataset,
  AnnotationGridItem,
  PredictionCollection,
  PredictionResult,
  PredictionJob,
  ReviewAction,
  SampleWithLabels,
  SaveReviewAnnotationItem,
  ExportFormat,
  TaskTrackerSummary,
} from "../types";
import { resolveImageUris } from "../utils/imageAdapters";
import { useOrgStore } from "../stores/org";
import { useAuthStore } from "../stores/auth";
import AnnotationGrid from "../components/annotation/AnnotationGrid.vue";
import ClassifySidebar from "../components/classify/ClassifySidebar.vue";
import { mergePanels, type SidebarPanelDescriptor } from "../components/classify/sidebarConfig";
import { useClassifyDashboard } from "../composables/useClassifyDashboard";
import TaskInsightModal from "../components/TaskInsightModal.vue";

const message = useMessage();
const qc = useQueryClient();
const orgStore = useOrgStore();
const authStore = useAuthStore();
const router = useRouter();
const themeVars = useThemeVars();

const themeStyleVars = computed(() => ({
  '--cv-bg': themeVars.value.bodyColor,
  '--cv-card-bg': themeVars.value.cardColor,
  '--cv-text': themeVars.value.textColor1,
  '--cv-text-secondary': themeVars.value.textColor3,
  '--cv-text-disabled': themeVars.value.textColorDisabled,
  '--cv-border': themeVars.value.borderColor,
  '--cv-divider': themeVars.value.dividerColor,
  '--cv-hover': themeVars.value.hoverColor,
  '--cv-primary': themeVars.value.primaryColor,
  '--cv-primary-hover': themeVars.value.primaryColorHover,
}))

// ---------------------------------------------------------------------------
// Setup state
// ---------------------------------------------------------------------------

const selectedDatasetId = ref<string | null>(null);
const selectedModelId = ref<string | null>(null);
const modelVersionTag = ref("");

// ---------------------------------------------------------------------------
// Queries
// ---------------------------------------------------------------------------

const { data: datasets } = useQuery({
  queryKey: computed(() => ["datasets", orgStore.currentOrgId]),
  queryFn: api.listDatasets,
  enabled: computed(() => !!orgStore.currentOrgId),
});

const { data: models } = useQuery({
  queryKey: computed(() => ["models", orgStore.currentOrgId]),
  queryFn: () => api.listModels(),
  enabled: computed(() => !!orgStore.currentOrgId),
});

const datasetOptions = computed<SelectOption[]>(() =>
  (datasets.value ?? []).map((d) => ({ label: d.name, value: d.id }))
);

const modelOptions = computed<SelectOption[]>(() => {
  const allModels = models.value ?? [];
  const dataset = selectedDataset.value;
  const filtered = dataset
    ? allModels.filter((m) => {
        const metadata = m.metadata ?? {};
        const datasetTypes = Array.isArray(metadata.dataset_types) ? metadata.dataset_types as string[] : [];
        const taskTypes = Array.isArray(metadata.task_types) ? metadata.task_types as string[] : [];
        return datasetTypes.includes(dataset.dataset_type)
          && taskTypes.includes(dataset.task_spec.task_type);
      })
    : allModels;
  const source = filtered.length > 0 ? filtered : allModels;
  return source.map((m) => ({
    label: `${m.name || m.id.slice(0, 12) + "..."} (${m.dataset_name})`,
    value: m.id,
  }));
});

const selectedModel = computed<Model | undefined>(
  () => (models.value ?? []).find((m) => m.id === selectedModelId.value)
);

const predictionTarget = computed(() => {
  const targets = selectedModel.value?.metadata?.prediction_targets;
  if (Array.isArray(targets) && typeof targets[0] === "string") {
    return targets[0];
  }
  return "image_classification";
});

// ---------------------------------------------------------------------------
// Predictions state
// ---------------------------------------------------------------------------

interface ReviewRow {
  key: string;
  prediction_id: string | null;
  sample_id: string;
  predicted_label: string;
  final_label: string;
  confidence: number | null;
}

const predictions = ref<ReviewRow[]>([]);
const activePredictionJob = ref<PredictionJob | null>(null);
const pollingPredictionJob = ref(false);
const syncedCollection = ref<PredictionCollection | null>(null);
const syncedCollectionTag = ref<string | null>(null);

const { data: predictionJobsData } = useQuery({
  queryKey: computed(() => ["prediction-jobs", orgStore.currentOrgId]),
  queryFn: api.listPredictionJobs,
  enabled: computed(() => !!orgStore.currentOrgId),
  refetchInterval: 3000,
});

const predictionJobs = computed(() =>
  (predictionJobsData.value ?? []).filter((job) => job.target === predictionTarget.value).slice(0, 10)
);

function predictionResultToReviewRow(p: PredictionResult): ReviewRow {
  return {
    key: p.id ?? p.sample_id,
    prediction_id: p.id,
    sample_id: p.sample_id,
    predicted_label: p.predicted_label,
    final_label: p.predicted_label,
    confidence: p.confidence,
  };
}

async function loadReviewRowsFromJob(job: PredictionJob): Promise<ReviewRow[]> {
  const summaryPredictions = ((job.summary.predictions as PredictionResult[] | undefined) ?? [])
    .filter((p) => !p.error)
    .map(predictionResultToReviewRow);

  if (summaryPredictions.length > 0) {
    return summaryPredictions;
  }
  const predictionsForJob = await api.listPredictionJobPredictions(job.id);
  return predictionsForJob.filter((item) => !item.error).map(predictionResultToReviewRow);
}

function asNumber(value: unknown): number | null {
  if (typeof value === "number" && Number.isFinite(value)) {
    return value;
  }
  if (typeof value === "string" && value.trim() !== "") {
    const parsed = Number(value);
    if (Number.isFinite(parsed)) {
      return parsed;
    }
  }
  return null;
}

function getPredictionJobProgress(job: PredictionJob): { processed: number; total: number } | null {
  const status = job.status.toLowerCase();
  const total = asNumber(job.summary.total_samples)
    ?? asNumber(job.summary.total)
    ?? asNumber(job.sample_ids?.length)
    ?? null;
  const processed = asNumber(job.summary.processed)
    ?? asNumber(job.summary.successful)
    ?? asNumber(job.summary.completed)
    ?? (status === "completed" ? total : 0);

  if (total === null || processed === null || total <= 0) {
    return null;
  }

  return {
    processed,
    total,
  };
}

function formatPredictionJobProgress(job: PredictionJob): string {
  const progress = getPredictionJobProgress(job);
  return progress ? `${progress.processed}/${progress.total}` : "-";
}

const editedCount = computed(
  () => predictions.value.filter((r) => r.final_label !== r.predicted_label).length
);

// Get label space for the selected dataset
const selectedDataset = computed<Dataset | undefined>(
  () => (datasets.value ?? []).find((d) => d.id === selectedDatasetId.value)
);

const labelSpace = computed<string[]>(
  () => selectedDataset.value?.task_spec?.label_space ?? []
);

const labelOptions = computed<SelectOption[]>(() =>
  labelSpace.value.map((l) => ({ label: l, value: l }))
);

const isClassificationDataset = computed(() =>
  selectedDataset.value?.task_spec?.task_type === "classification"
);

// ---------------------------------------------------------------------------
// Step 2 grid mode — AnnotationGrid items
// ---------------------------------------------------------------------------

// Samples fetched for building grid items alongside prediction rows
const reviewSamples = ref<SampleWithLabels[]>([]);

// Draft labels (user corrections in grid mode)
const reviewDraftLabels = ref<Record<string, string>>({});

const reviewGridItems = computed<AnnotationGridItem[]>(() => {
  if (!isClassificationDataset.value || predictions.value.length === 0) return [];
  const sampleMap = new Map(reviewSamples.value.map((s) => [s.id, s]));
  return predictions.value.map((row) => {
    const sample = sampleMap.get(row.sample_id);
    return {
      id: row.sample_id,
      imageSrcs: resolveImageUris(sample?.image_uris ?? []),
      currentLabel: sample?.latest_annotation?.label ?? null,
      draftLabel: reviewDraftLabels.value[row.sample_id] ?? null,
      predictionLabel: row.predicted_label,
      predictionConfidence: row.confidence,
      predictionId: row.prediction_id,
      metadata: sample?.metadata ?? {},
    };
  });
});

// Provide grid items for PredictionSummaryWidget
provide<Ref<AnnotationGridItem[]>>('pr-grid-items', reviewGridItems);

function onGridSelect(ids: Set<string>) {
  // Selection tracking (for potential future use)
  void ids;
}

function onGridApplyLabel(payload: { ids: string[]; label: string }) {
  const draft = { ...reviewDraftLabels.value };
  payload.ids.forEach((id) => { draft[id] = payload.label; });
  reviewDraftLabels.value = draft;
  // Sync back to review rows
  payload.ids.forEach((id) => {
    const row = predictions.value.find((r) => r.sample_id === id);
    if (row) row.final_label = payload.label;
  });
}

const gridRef = ref<InstanceType<typeof AnnotationGrid> | null>(null);

// Sidebar for review mode
const sidebarCollapsed = ref(false);

const reviewDraftCount = computed(() =>
  Object.keys(reviewDraftLabels.value).length
);

const reviewSelectedCount = ref(0);

const dashboardContext = useClassifyDashboard(
  computed(() => selectedDatasetId.value ?? ''),
  reviewDraftCount,
  reviewSelectedCount as Ref<number>,
  labelSpace,
);

// Sidebar panels for review mode (includes prediction summary widget)
const reviewStaticPanels: SidebarPanelDescriptor[] = [
  {
    id: 'prediction-summary',
    component: 'prediction-summary',
    title: 'Prediction Summary',
    props: {},
    order: 5,
  },
  {
    id: 'annotation-progress',
    component: 'annotation-progress',
    title: 'Annotation Progress',
    props: {
      chartType: 'donut',
      showCounts: true,
      showPercent: true,
      includeDrafts: true,
      showLabelBreakdown: true,
    },
    order: 10,
  },
];

const reviewSidebarPanels = computed(() =>
  mergePanels(reviewStaticPanels, [])
);

// Load samples when predictions are loaded (for grid images)
watch(predictions, async (rows) => {
  if (rows.length === 0 || !selectedDatasetId.value) {
    reviewSamples.value = [];
    return;
  }
  try {
    // Fetch all samples in batches to get images
    const allSamples: SampleWithLabels[] = [];
    const pageSize = 200;
    let offset = 0;
    let total = Infinity;
    while (offset < total) {
      const result = await listSamplesWithLabels(selectedDatasetId.value!, offset, pageSize);
      allSamples.push(...result.items);
      total = result.total;
      offset += pageSize;
      if (result.items.length === 0) break;
    }
    reviewSamples.value = allSamples;
  } catch {
    reviewSamples.value = [];
  }
});

// ---------------------------------------------------------------------------
// Task Insight Modal (auto-open for active prediction jobs) — T4
// ---------------------------------------------------------------------------

const showTaskModal = ref(false);
const taskHandoffEnabled = ref(true);

const activeTaskSummary = computed<TaskTrackerSummary | null>(() => {
  const job = activePredictionJob.value;
  if (!job) return null;
  const status = job.status.toLowerCase();
  if (!['queued', 'running'].includes(status)) return null;
  // Build a TaskTrackerSummary from the prediction job (the backend
  // uses the same ID for both, so the modal can fetch full detail by ID)
  return {
    id: job.id,
    task_kind: 'prediction',
    execution_kind: 'prefect',
    display_name: `Prediction: ${job.dataset_id.slice(0, 8)}...`,
    display_status: status,
    stage: status === 'queued' ? 'queued' : 'running',
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
    queue_priority_label: 'none',
    queue_depth_ahead: null,
    capacity_status: 'unknown',
    pool_concurrency_limit: null,
    pool_slots_used: null,
  };
});

// Auto-open modal when a prediction job becomes active; auto-close when done
watch(activeTaskSummary, (task) => {
  if (task) {
    showTaskModal.value = true;
  } else {
    showTaskModal.value = false;
  }
});

// ---------------------------------------------------------------------------
// Run predictions
// ---------------------------------------------------------------------------

const runPredictionsMutation = useMutation({
  mutationFn: () => {
    if (!selectedModelId.value || !selectedDatasetId.value) {
      throw new Error("Model and dataset are required");
    }
    return api.runPredictions({
      model_id: selectedModelId.value,
      dataset_id: selectedDatasetId.value,
      model_version: modelVersionTag.value || null,
      target: predictionTarget.value,
    });
  },
  onSuccess: (data) => {
    activePredictionJob.value = data;
    predictions.value = [];
    reviewDraftLabels.value = {};
    message.success(`Prediction job submitted: ${data.id}`);
    void pollPredictionJob(data.id);
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
    return api.cancelPredictionJob(activePredictionJob.value.id);
  },
  onSuccess: () => {
    message.warning("Prediction cancellation requested");
  },
  onError: (err: Error) => {
    message.error(err.message ?? "Failed to cancel prediction job");
  },
});

function onRunPredictions() {
  runPredictionsMutation.mutate();
}

function onCancelPredictionJob() {
  cancelPredictionMutation.mutate();
}

function onDatasetChange() {
  selectedModelId.value = null;
  predictions.value = [];
  reviewDraftLabels.value = {};
  activePredictionJob.value = null;
  syncedCollection.value = null;
  syncedCollectionTag.value = null;
}

async function pollPredictionJob(jobId: string) {
  pollingPredictionJob.value = true;
  try {
    for (let attempt = 0; attempt < 120; attempt += 1) {
      const job = await api.getPredictionJob(jobId);
      activePredictionJob.value = job;

      // Ensure dataset/model context matches the loaded job so the
      // correct Step 2 renderer (grid vs. fallback table) is used.
      if (job.dataset_id && selectedDatasetId.value !== job.dataset_id) {
        selectedDatasetId.value = job.dataset_id;
      }
      if (job.model_id && selectedModelId.value !== job.model_id) {
        selectedModelId.value = job.model_id;
      }

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

function resetEdits() {
  reviewDraftLabels.value = {};
  predictions.value = predictions.value.map((r) => ({
    ...r,
    final_label: r.predicted_label,
  }));
}

// ---------------------------------------------------------------------------
// Review table columns (for VQA / non-classification fallback)
// ---------------------------------------------------------------------------

const reviewColumns = computed<DataTableColumns<ReviewRow>>(() => [
  {
    title: "Sample ID",
    key: "sample_id",
    width: 180,
    ellipsis: { tooltip: true },
    render: (row) => row.sample_id.slice(0, 16) + "...",
  },
  {
    title: "Predicted",
    key: "predicted_label",
    width: 140,
    render: (row) => h(NTag, { size: "small", type: "info" }, { default: () => row.predicted_label }),
  },
  {
    title: "Confidence",
    key: "confidence",
    width: 100,
    render: (row) =>
      row.confidence !== null ? (row.confidence * 100).toFixed(1) + "%" : "-",
  },
  {
    title: "Final Label",
    key: "final_label",
    width: 200,
    render: (row) => {
      if (labelSpace.value.length > 0) {
        return h(NSelect, {
          value: row.final_label,
          options: labelOptions.value,
          size: "small",
          style: "width: 160px",
          onUpdateValue: (val: string) => {
            row.final_label = val;
          },
        });
      }
      // Fallback: free-text display
      return h(NTag, {
        size: "small",
        type: row.final_label !== row.predicted_label ? "warning" : "success",
      }, { default: () => row.final_label });
    },
  },
  {
    title: "Status",
    key: "status",
    width: 100,
    render: (row) =>
      row.final_label !== row.predicted_label
        ? h(NTag, { size: "small", type: "warning" }, { default: () => "Edited" })
        : h(NTag, { size: "small", type: "default" }, { default: () => "Accepted" }),
  },
]);

const predictionJobColumns = computed<DataTableColumns<PredictionJob>>(() => [
  { title: "Job", key: "id", width: 180, render: (row) => row.id.slice(0, 16) + "..." },
  { title: "Status", key: "status", width: 120 },
  {
    title: "Progress",
    key: "progress",
    width: 140,
    render: (row) => formatPredictionJobProgress(row),
  },
  {
    title: "Actions",
    key: "actions",
    width: 120,
    render: (row) =>
      h(NButton, {
        size: "small",
        disabled: row.status.toLowerCase() !== "completed",
        onClick: () => void pollPredictionJob(row.id),
      }, { default: () => "Load" }),
  },
]);

// ---------------------------------------------------------------------------
// Save annotations
// ---------------------------------------------------------------------------

const currentReviewActionId = ref<string | null>(null);

const syncCollectionMutation = useMutation({
  mutationFn: async () => {
    if (!selectedDatasetId.value || !selectedModelId.value || predictions.value.length === 0) {
      throw new Error("Predictions are required before syncing to Label Studio");
    }
    const collection = await api.createPredictionCollection({
      name: `review-${new Date().toISOString()}`,
      dataset_id: selectedDatasetId.value,
      model_id: selectedModelId.value,
      prediction_ids: predictions.value.map((row) => row.prediction_id).filter((id): id is string => !!id),
      model_version: modelVersionTag.value || null,
      target: predictionTarget.value,
      source_job_id: activePredictionJob.value?.id ?? null,
    });
    const syncResult = await api.syncPredictionCollection(collection.id);
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
    if (!selectedDatasetId.value || !selectedModelId.value) {
      throw new Error("Dataset and model are required");
    }
    // Create review action first
    const action = await api.createReviewAction(
      selectedDatasetId.value,
      selectedModelId.value,
      modelVersionTag.value || null,
      syncedCollection.value?.id ?? null,
      syncedCollectionTag.value,
    );
    currentReviewActionId.value = action.id;

    // Save annotations — use draft labels from grid if in classification mode
    const items: SaveReviewAnnotationItem[] = predictions.value.map((r) => ({
      sample_id: r.sample_id,
      predicted_label: r.predicted_label,
      final_label: reviewDraftLabels.value[r.sample_id] ?? r.final_label,
      confidence: r.confidence,
      prediction_id: r.prediction_id,
    }));
    return api.saveReviewAnnotations(action.id, items);
  },
  onSuccess: (data) => {
    message.success(`Saved ${data.created_count} annotations to version`);
    predictions.value = [];
    reviewDraftLabels.value = {};
    // Refresh review actions if viewing the same dataset
    if (exportDatasetId.value === selectedDatasetId.value) {
      qc.invalidateQueries({ queryKey: ["reviewActions", exportDatasetId.value] });
    }
  },
  onError: (err: Error) => {
    message.error(err.message ?? "Failed to save annotations");
  },
});

function onSaveAnnotations() {
  saveAnnotationsMutation.mutate();
}

function onSyncCollectionToLs() {
  syncCollectionMutation.mutate();
}

// ---------------------------------------------------------------------------
// History & Export
// ---------------------------------------------------------------------------

const exportDatasetId = ref<string | null>(null);
const reviewActions = ref<ReviewAction[]>([]);
const reviewActionsLoading = ref(false);

async function fetchReviewActions(datasetId: string) {
  reviewActionsLoading.value = true;
  try {
    reviewActions.value = await api.listReviewActions(datasetId);
  } catch (err: unknown) {
    message.error((err as Error).message ?? "Failed to fetch review actions");
    reviewActions.value = [];
  } finally {
    reviewActionsLoading.value = false;
  }
}

function onExportDatasetChange() {
  reviewActions.value = [];
  if (exportDatasetId.value) {
    fetchReviewActions(exportDatasetId.value);
  }
}

// Refresh review actions when query is invalidated
watch(
  () => exportDatasetId.value,
  (dsId) => {
    if (dsId) fetchReviewActions(dsId);
  },
);

// History table columns
const historyColumns = computed<DataTableColumns<ReviewAction>>(() => [
  {
    title: "ID",
    key: "id",
    width: 180,
    ellipsis: { tooltip: true },
    render: (row) => row.id.slice(0, 16) + "...",
  },
  {
    title: "Model",
    key: "model_id",
    width: 180,
    ellipsis: { tooltip: true },
    render: (row) => {
      const model = (models.value ?? []).find((m) => m.id === row.model_id);
      return model?.name || row.model_id.slice(0, 12) + "...";
    },
  },
  {
    title: "Version",
    key: "model_version",
    width: 100,
    render: (row) => row.model_version || "-",
  },
  {
    title: "Created",
    key: "created_at",
    width: 160,
    render: (row) => new Date(row.created_at).toLocaleString(),
  },
  {
    title: "Actions",
    key: "actions",
    width: 200,
    render: (row) =>
      h(NSpace, { size: "small" }, () => [
        h(
          NButton,
          {
            size: "small",
            type: "primary",
            onClick: () => openExportModal(row.id),
          },
          { default: () => "Export" },
        ),
        h(
          NButton,
          {
            size: "small",
            type: "error",
            onClick: () => {
              actionToDelete.value = row.id;
              showDeleteModal.value = true;
            },
          },
          { default: () => "Delete" },
        ),
      ]),
  },
]);

// ---------------------------------------------------------------------------
// Export modal
// ---------------------------------------------------------------------------

const showExportModal = ref(false);
const exportActionId = ref<string | null>(null);
const selectedExportFormat = ref("annotation-version-full-context-v1");
const exportPreview = ref<string | null>(null);
const exportUri = ref<string | null>(null);
const previewExportLoading = ref(false);

const { data: exportFormats } = useQuery({
  queryKey: ["exportFormats"],
  queryFn: api.listExportFormats,
});

const exportFormatOptions = computed<SelectOption[]>(() =>
  (exportFormats.value ?? []).map((f) => ({ label: f.format_id, value: f.format_id }))
);

function openExportModal(actionId: string) {
  exportActionId.value = actionId;
  exportPreview.value = null;
  exportUri.value = null;
  selectedExportFormat.value = "annotation-version-full-context-v1";
  showExportModal.value = true;
}

async function onPreviewExport() {
  if (!exportActionId.value) return;
  previewExportLoading.value = true;
  try {
    const data = await api.previewReviewExport(
      exportActionId.value,
      selectedExportFormat.value,
    );
    exportPreview.value = JSON.stringify(data, null, 2);
  } catch (err: unknown) {
    message.error((err as Error).message ?? "Failed to preview export");
  } finally {
    previewExportLoading.value = false;
  }
}

const persistExportMutation = useMutation({
  mutationFn: () => {
    if (!exportActionId.value) throw new Error("No action selected");
    return api.persistReviewExport(exportActionId.value, selectedExportFormat.value);
  },
  onSuccess: (data) => {
    exportUri.value = data.uri;
    message.success("Export persisted successfully");
  },
  onError: (err: Error) => {
    message.error(err.message ?? "Failed to persist export");
  },
});

function onPersistExport() {
  persistExportMutation.mutate();
}

// ---------------------------------------------------------------------------
// Delete action
// ---------------------------------------------------------------------------

const showDeleteModal = ref(false);
const actionToDelete = ref<string | null>(null);

const deleteActionMutation = useMutation({
  mutationFn: (actionId: string) => api.deleteReviewAction(actionId),
  onSuccess: () => {
    message.success("Review action deleted");
    showDeleteModal.value = false;
    actionToDelete.value = null;
    if (exportDatasetId.value) {
      fetchReviewActions(exportDatasetId.value);
    }
  },
  onError: (err: Error) => {
    message.error(err.message ?? "Failed to delete review action");
  },
});

function confirmDeleteAction() {
  if (actionToDelete.value) {
    deleteActionMutation.mutate(actionToDelete.value);
  }
  return false;
}
</script>

<style scoped>
.pr-review-body {
  display: flex;
  min-height: 400px;
  max-height: 70vh;
  gap: 0;
}
</style>
