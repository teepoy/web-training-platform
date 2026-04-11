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
          <n-form-item label="Template" path="templateId">
            <n-select
              v-model:value="uploadForm.templateId"
              :options="templateOptions"
              placeholder="Select upload template"
            />
          </n-form-item>
          <n-form-item label="Profile" path="profileId">
            <n-select
              v-model:value="uploadForm.profileId"
              :options="profileOptions"
              placeholder="Select prefill profile"
            />
          </n-form-item>
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
          <n-form-item label="Framework" path="framework">
            <n-input v-model:value="uploadForm.framework" placeholder="e.g. pytorch" />
          </n-form-item>
          <n-form-item label="Architecture" path="architecture">
            <n-input v-model:value="uploadForm.architecture" placeholder="e.g. resnet50" />
          </n-form-item>
          <n-form-item label="Base Model" path="baseModel">
            <n-input v-model:value="uploadForm.baseModel" placeholder="e.g. torchvision/resnet50" />
          </n-form-item>
          <n-form-item v-if="requiresLabelSpace" label="Label Space" path="labelSpace">
            <n-dynamic-tags v-model:value="uploadForm.labelSpace" />
          </n-form-item>
          <n-form-item v-if="requiresEmbeddingMetadata" label="Embedding Dim" path="embeddingDimension">
            <n-input-number v-model:value="uploadForm.embeddingDimension" :min="1" style="width: 100%" />
          </n-form-item>
          <n-form-item v-if="requiresEmbeddingMetadata" label="Normalized Output" path="normalizedOutput">
            <n-switch v-model:value="uploadForm.normalizedOutput" />
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
import { ref, computed, h, watch } from "vue";
import { useMutation, useQuery, useQueryClient } from "@tanstack/vue-query";
import type { DataTableColumns, FormInst, FormRules, SelectOption, UploadFileInfo } from "naive-ui";
import { useMessage, NTag, NButton, NSpace } from "naive-ui";
import { api, uploadModel, API_BASE } from "../api";
import type { Model, ModelUploadTemplate, UploadModelMetadata } from "../types";
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

const { data: uploadTemplates } = useQuery({
  queryKey: ["model-upload-templates"],
  queryFn: api.listModelUploadTemplates,
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

const templateOptions = computed<SelectOption[]>(() =>
  (uploadTemplates.value ?? []).map((template) => ({ label: template.name, value: template.id }))
);

const selectedTemplate = computed<ModelUploadTemplate | undefined>(() =>
  (uploadTemplates.value ?? []).find((template) => template.id === uploadForm.value.templateId)
);

const profileOptions = computed<SelectOption[]>(() =>
  (selectedTemplate.value?.profiles ?? []).map((profile) => ({ label: profile.name, value: profile.id }))
);

const requiresLabelSpace = computed(() => selectedTemplate.value?.label_space_mode === "required");
const requiresEmbeddingMetadata = computed(() => selectedTemplate.value?.requires_embedding_metadata === true);

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
  templateId: null as string | null,
  profileId: "custom",
  name: "",
  format: null as string | null,
  jobId: null as string | null,
  framework: "",
  architecture: "",
  baseModel: "",
  labelSpace: [] as string[],
  embeddingDimension: null as number | null,
  normalizedOutput: true,
  file: null as File | null,
});

const uploadRules: FormRules = {
  templateId: [{ required: true, message: "Please select an upload template", trigger: "change" }],
  name: [{ required: true, message: "Please enter a model name", trigger: "blur" }],
  format: [{ required: true, message: "Please select a format", trigger: "change" }],
  jobId: [{ required: true, message: "Please select a training job", trigger: "change" }],
  framework: [{ required: true, message: "Please enter framework", trigger: "blur" }],
  architecture: [{ required: true, message: "Please enter architecture", trigger: "blur" }],
  baseModel: [{ required: true, message: "Please enter base model", trigger: "blur" }],
  labelSpace: [{
    validator: () => {
      if (requiresLabelSpace.value && uploadForm.value.labelSpace.length === 0) {
        return new Error("Label space is required for classifier uploads");
      }
      return true;
    },
    trigger: ["blur", "change"],
  }],
};

function handleFileChange(data: { file: UploadFileInfo; fileList: UploadFileInfo[] }) {
  uploadForm.value.file = data.file.file ?? null;
}

const uploadMutation = useMutation({
  mutationFn: () => {
    if (!uploadForm.value.file || !uploadForm.value.format || !uploadForm.value.jobId || !uploadForm.value.templateId) {
      throw new Error("Missing required fields");
    }
    const metadata: UploadModelMetadata = {
      name: uploadForm.value.name,
      format: uploadForm.value.format as UploadModelMetadata["format"],
      job_id: uploadForm.value.jobId,
      template_id: uploadForm.value.templateId,
      profile_id: uploadForm.value.profileId,
      model_spec: {
        framework: uploadForm.value.framework,
        architecture: uploadForm.value.architecture,
        base_model: uploadForm.value.baseModel,
      },
      compatibility: {
        dataset_types: selectedTemplate.value?.dataset_types ?? [],
        task_types: selectedTemplate.value?.task_types ?? [],
        prediction_targets: selectedProfileTargets.value,
        label_space: uploadForm.value.labelSpace,
        embedding_dimension: uploadForm.value.embeddingDimension,
        normalized_output: requiresEmbeddingMetadata.value ? uploadForm.value.normalizedOutput : null,
      },
    };
    return uploadModel(
      uploadForm.value.file,
      metadata,
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
  uploadForm.value = {
    templateId: null,
    profileId: "custom",
    name: "",
    format: null,
    jobId: null,
    framework: "",
    architecture: "",
    baseModel: "",
    labelSpace: [],
    embeddingDimension: null,
    normalizedOutput: true,
    file: null,
  };
  uploadFormRef.value?.restoreValidation();
}

const selectedProfileTargets = computed(() => {
  const template = selectedTemplate.value;
  const profile = template?.profiles.find((item) => item.id === uploadForm.value.profileId);
  return profile?.default_prediction_targets ?? [];
});

watch(
  () => uploadForm.value.templateId,
  (templateId) => {
    const template = (uploadTemplates.value ?? []).find((item) => item.id === templateId);
    uploadForm.value.profileId = template?.profiles[0]?.id ?? "custom";
    if (template?.label_space_mode === "forbidden") {
      uploadForm.value.labelSpace = [];
    }
  }
);

watch(
  () => [uploadForm.value.templateId, uploadForm.value.profileId],
  () => {
    const template = selectedTemplate.value;
    const profile = template?.profiles.find((item) => item.id === uploadForm.value.profileId);
    const modelSpec = profile?.model_spec ?? {};
    uploadForm.value.framework = modelSpec.framework ?? uploadForm.value.framework;
    uploadForm.value.architecture = modelSpec.architecture ?? uploadForm.value.architecture;
    uploadForm.value.baseModel = modelSpec.base_model ?? uploadForm.value.baseModel;
  }
);

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
