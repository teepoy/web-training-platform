<template>
  <n-space vertical size="large">
    <template v-if="!orgStore.currentOrgId">
      <div style="padding: 48px; text-align: center;">
        <n-empty description="You are not a member of any organization. Contact an admin." />
      </div>
    </template>
    <template v-else>
      <n-page-header title="Trained Models">
        <template #extra>
          <n-space>
            <n-select
              v-model:value="filterDatasetId"
              :options="datasetOptions"
              placeholder="Filter by Dataset"
              clearable
              style="width: 200px"
            />
            <n-button type="primary" @click="showUploadModal = true">Upload Model</n-button>
          </n-space>
        </template>
      </n-page-header>

      <n-spin :show="isLoading">
        <n-data-table
          :columns="columns"
          :data="models ?? []"
          :bordered="true"
          :striped="true"
          :loading="isLoading"
        />
      </n-spin>

      <!-- Upload Modal -->
      <n-modal
        v-model:show="showUploadModal"
        preset="dialog"
        title="Upload Model"
        positive-text="Upload"
        negative-text="Cancel"
        :loading="uploadMutation.isPending.value"
        @positive-click="onUploadSubmit"
        @negative-click="onUploadCancel"
      >
        <n-form
          ref="uploadFormRef"
          :model="uploadForm"
          :rules="uploadRules"
          label-placement="left"
          label-width="auto"
        >
          <n-form-item label="Model Name" path="name">
            <n-input v-model:value="uploadForm.name" placeholder="e.g. my-classifier-v1" />
          </n-form-item>
          <n-form-item label="Format" path="format">
            <n-select
              v-model:value="uploadForm.format"
              :options="formatOptions"
              placeholder="Select format"
            />
          </n-form-item>
          <n-form-item label="Training Job" path="jobId">
            <n-select
              v-model:value="uploadForm.jobId"
              :options="jobOptions"
              :loading="jobsLoading"
              placeholder="Select job to associate"
              filterable
            />
          </n-form-item>
          <n-form-item label="Model File" path="file">
            <n-upload
              :max="1"
              :default-upload="false"
              @change="handleFileChange"
            >
              <n-button>Select File</n-button>
            </n-upload>
            <span v-if="uploadForm.file" style="margin-left: 8px">{{ uploadForm.file.name }}</span>
          </n-form-item>
        </n-form>
      </n-modal>

      <!-- Delete Confirmation Modal -->
      <n-modal
        v-model:show="showDeleteModal"
        preset="dialog"
        title="Delete Model"
        type="warning"
        positive-text="Delete"
        negative-text="Cancel"
        :loading="deleteMutation.isPending.value"
        @positive-click="confirmDelete"
        @negative-click="showDeleteModal = false"
      >
        <p>Are you sure you want to delete this model? This action cannot be undone.</p>
        <p v-if="modelToDelete"><strong>{{ modelToDelete.name || modelToDelete.id }}</strong></p>
      </n-modal>

      <!-- Predict Modal -->
      <PredictModal
        v-model:show="showPredictModal"
        :model="modelToPredict"
      />
    </template>
  </n-space>
</template>

<script setup lang="ts">
import { ref, computed, h } from "vue";
import { useMutation, useQuery, useQueryClient } from "@tanstack/vue-query";
import type { DataTableColumns, FormInst, FormRules, SelectOption, UploadFileInfo } from "naive-ui";
import { useMessage, NTag, NButton, NSpace } from "naive-ui";
import { api, uploadModel, API_BASE } from "../api";
import type { Model } from "../types";
import { useOrgStore } from "../stores/org";
import { useAuthStore } from "../stores/auth";
import PredictModal from "../components/PredictModal.vue";

const message = useMessage();
const qc = useQueryClient();
const orgStore = useOrgStore();
const authStore = useAuthStore();

// ---------------------------------------------------------------------------
// Filters
// ---------------------------------------------------------------------------

const filterDatasetId = ref<string | null>(null);

// ---------------------------------------------------------------------------
// Queries
// ---------------------------------------------------------------------------

const { data: models, isLoading } = useQuery({
  queryKey: computed(() => ["models", orgStore.currentOrgId, filterDatasetId.value]),
  queryFn: () => api.listModels(filterDatasetId.value ?? undefined),
  enabled: computed(() => !!orgStore.currentOrgId),
});

const { data: datasets } = useQuery({
  queryKey: computed(() => ["datasets", orgStore.currentOrgId]),
  queryFn: api.listDatasets,
  enabled: computed(() => !!orgStore.currentOrgId),
});

const { data: jobs, isLoading: jobsLoading } = useQuery({
  queryKey: computed(() => ["jobs", orgStore.currentOrgId]),
  queryFn: api.listJobs,
  enabled: computed(() => !!orgStore.currentOrgId),
});

// ---------------------------------------------------------------------------
// Select options
// ---------------------------------------------------------------------------

const datasetOptions = computed<SelectOption[]>(() =>
  (datasets.value ?? []).map((d) => ({ label: d.name, value: d.id }))
);

const jobOptions = computed<SelectOption[]>(() =>
  (jobs.value ?? [])
    .filter((j) => j.status === "completed")
    .map((j) => ({ label: `${j.id.slice(0, 8)}... (${j.status})`, value: j.id }))
);

const formatOptions: SelectOption[] = [
  { label: "PyTorch (.pt)", value: "pytorch" },
  { label: "ONNX (.onnx)", value: "onnx" },
  { label: "SafeTensors (.safetensors)", value: "safetensors" },
  { label: "Keras (.keras)", value: "keras" },
];

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function formatFileSize(bytes: number | null): string {
  if (bytes === null) return "-";
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  if (bytes < 1024 * 1024 * 1024) return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  return `${(bytes / (1024 * 1024 * 1024)).toFixed(2)} GB`;
}

function downloadModel(model: Model) {
  const token = authStore.token;
  const url = `${API_BASE}/models/${model.id}/download${token ? `?token=${encodeURIComponent(token)}` : ""}`;
  window.open(url, "_blank");
}

// ---------------------------------------------------------------------------
// Table columns
// ---------------------------------------------------------------------------

const columns = computed<DataTableColumns<Model>>(() => [
  {
    title: "Name",
    key: "name",
    width: 200,
    render: (row) => row.name || row.id.slice(0, 12) + "...",
  },
  {
    title: "Format",
    key: "format",
    width: 120,
    render: (row) =>
      row.format
        ? h(NTag, { size: "small", type: "info" }, { default: () => row.format })
        : "-",
  },
  {
    title: "Size",
    key: "file_size",
    width: 100,
    render: (row) => formatFileSize(row.file_size),
  },
  {
    title: "Dataset",
    key: "dataset_name",
    ellipsis: { tooltip: true },
  },
  {
    title: "Preset",
    key: "preset_name",
    ellipsis: { tooltip: true },
  },
  {
    title: "Created",
    key: "created_at",
    width: 160,
    render: (row) => (row.created_at ? new Date(row.created_at).toLocaleString() : "-"),
  },
  {
    title: "Actions",
    key: "actions",
    width: 260,
    render: (row) =>
      h(NSpace, { size: "small" }, () => [
        h(
          NButton,
          {
            size: "small",
            type: "info",
            onClick: () => {
              modelToPredict.value = row;
              showPredictModal.value = true;
            },
          },
          { default: () => "Predict" }
        ),
        h(
          NButton,
          {
            size: "small",
            type: "primary",
            onClick: () => downloadModel(row),
          },
          { default: () => "Download" }
        ),
        h(
          NButton,
          {
            size: "small",
            type: "error",
            onClick: () => {
              modelToDelete.value = row;
              showDeleteModal.value = true;
            },
          },
          { default: () => "Delete" }
        ),
      ]),
  },
]);

// ---------------------------------------------------------------------------
// Upload Modal
// ---------------------------------------------------------------------------

const showUploadModal = ref(false);
const uploadFormRef = ref<FormInst | null>(null);
const uploadForm = ref({
  name: "",
  format: null as string | null,
  jobId: null as string | null,
  file: null as File | null,
});

const uploadRules: FormRules = {
  name: [{ required: true, message: "Please enter a model name", trigger: "blur" }],
  format: [{ required: true, message: "Please select a format", trigger: "change" }],
  jobId: [{ required: true, message: "Please select a training job", trigger: "change" }],
};

function handleFileChange(data: { file: UploadFileInfo; fileList: UploadFileInfo[] }) {
  uploadForm.value.file = data.file.file ?? null;
}

const uploadMutation = useMutation({
  mutationFn: () => {
    if (!uploadForm.value.file || !uploadForm.value.format || !uploadForm.value.jobId) {
      throw new Error("Missing required fields");
    }
    return uploadModel(
      uploadForm.value.file,
      uploadForm.value.name,
      uploadForm.value.format,
      uploadForm.value.jobId
    );
  },
  onSuccess: () => {
    qc.invalidateQueries({ queryKey: ["models", orgStore.currentOrgId] });
    message.success("Model uploaded successfully");
    showUploadModal.value = false;
    resetUploadForm();
  },
  onError: (err: Error) => {
    message.error(err.message ?? "Failed to upload model");
  },
});

function onUploadSubmit() {
  uploadFormRef.value?.validate((errors) => {
    if (errors) return;
    if (!uploadForm.value.file) {
      message.error("Please select a file");
      return;
    }
    uploadMutation.mutate();
  });
  return false;
}

function onUploadCancel() {
  resetUploadForm();
}

function resetUploadForm() {
  uploadForm.value = { name: "", format: null, jobId: null, file: null };
  uploadFormRef.value?.restoreValidation();
}

// ---------------------------------------------------------------------------
// Delete Modal
// ---------------------------------------------------------------------------

const showDeleteModal = ref(false);
const modelToDelete = ref<Model | null>(null);

// ---------------------------------------------------------------------------
// Predict Modal
// ---------------------------------------------------------------------------

const showPredictModal = ref(false);
const modelToPredict = ref<Model | null>(null);

const deleteMutation = useMutation({
  mutationFn: (id: string) => api.deleteModel(id),
  onSuccess: () => {
    qc.invalidateQueries({ queryKey: ["models", orgStore.currentOrgId] });
    message.success("Model deleted");
    showDeleteModal.value = false;
    modelToDelete.value = null;
  },
  onError: (err: Error) => {
    message.error(err.message ?? "Failed to delete model");
  },
});

function confirmDelete() {
  if (modelToDelete.value) {
    deleteMutation.mutate(modelToDelete.value.id);
  }
  return false;
}
</script>
