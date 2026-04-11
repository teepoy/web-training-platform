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
            <template v-if="activePredictionJob.summary.total_samples">
              · {{ Number(activePredictionJob.summary.processed || 0) }}/{{ Number(activePredictionJob.summary.total_samples || 0) }} processed
            </template>
          </n-text>
        </n-space>
      </n-card>

      <n-card v-if="predictionJobs.length > 0" title="Active & Recent Prediction Jobs" size="small">
        <n-data-table :columns="predictionJobColumns" :data="predictionJobs" :bordered="true" :max-height="260" />
      </n-card>

      <!-- Step 2: Review predictions -->
      <n-card
        v-if="predictions.length > 0"
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
              type="primary"
              :disabled="predictions.length === 0"
              :loading="saveAnnotationsMutation.isPending.value"
              @click="onSaveAnnotations"
            >
              Save as Annotation Version ({{ predictions.length }} items)
            </n-button>
          </n-space>
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
    </template>
  </n-space>
</template>

<script setup lang="ts">
import { ref, computed, h, watch } from "vue";
import { useMutation, useQuery, useQueryClient } from "@tanstack/vue-query";
import type { DataTableColumns, SelectOption } from "naive-ui";
import { useMessage, NButton, NSpace, NTag, NSelect } from "naive-ui";
import { api } from "../api";
import type {
  Model,
  Dataset,
  PredictionResult,
  PredictionJob,
  ReviewAction,
  SaveReviewAnnotationItem,
  ExportFormat,
} from "../types";
import { useOrgStore } from "../stores/org";

const message = useMessage();
const qc = useQueryClient();
const orgStore = useOrgStore();

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
  sample_id: string;
  ls_task_id: number | null;
  predicted_label: string;
  final_label: string;
  confidence: number | null;
  ls_prediction_id: number | null;
}

const predictions = ref<ReviewRow[]>([]);
const activePredictionJob = ref<PredictionJob | null>(null);
const pollingPredictionJob = ref(false);

const { data: predictionJobsData } = useQuery({
  queryKey: computed(() => ["prediction-jobs", orgStore.currentOrgId]),
  queryFn: api.listPredictionJobs,
  enabled: computed(() => !!orgStore.currentOrgId),
  refetchInterval: 3000,
});

const predictionJobs = computed(() =>
  (predictionJobsData.value ?? []).filter((job) => job.target === predictionTarget.value).slice(0, 10)
);

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
  activePredictionJob.value = null;
}

async function pollPredictionJob(jobId: string) {
  pollingPredictionJob.value = true;
  try {
    for (let attempt = 0; attempt < 120; attempt += 1) {
      const job = await api.getPredictionJob(jobId);
      activePredictionJob.value = job;
      const status = job.status.toLowerCase();
      if (status === "completed") {
        const rows = ((job.summary.predictions as PredictionResult[] | undefined) ?? [])
          .filter((p) => !p.error)
          .map((p) => ({
            key: p.sample_id,
            sample_id: p.sample_id,
            ls_task_id: p.ls_task_id,
            predicted_label: p.predicted_label,
            final_label: p.predicted_label,
            confidence: p.confidence,
            ls_prediction_id: p.ls_prediction_id,
          }));
        predictions.value = rows;
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
  predictions.value = predictions.value.map((r) => ({
    ...r,
    final_label: r.predicted_label,
  }));
}

// ---------------------------------------------------------------------------
// Review table columns
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
    render: (row) => `${Number(row.summary.processed || 0)}/${Number(row.summary.total_samples || 0)}`,
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
    );
    currentReviewActionId.value = action.id;

    // Save annotations
    const items: SaveReviewAnnotationItem[] = predictions.value.map((r) => ({
      sample_id: r.sample_id,
      predicted_label: r.predicted_label,
      final_label: r.final_label,
      confidence: r.confidence,
      source_prediction_id: r.ls_prediction_id,
    }));
    return api.saveReviewAnnotations(action.id, items);
  },
  onSuccess: (data) => {
    message.success(`Saved ${data.created_count} annotations to version`);
    predictions.value = [];
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
