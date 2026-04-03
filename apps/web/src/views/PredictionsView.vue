<template>
  <div>
    <n-space justify="space-between" align="center" style="margin-bottom: 16px">
      <n-h2 style="margin: 0">Predictions</n-h2>
      <n-button type="primary" @click="showCreateModal = true">
        + Create Prediction
      </n-button>
    </n-space>

    <n-alert v-if="isError" type="error" style="margin-bottom: 16px">
      Failed to load predictions: {{ (error as Error)?.message ?? "Unknown error" }}
    </n-alert>

    <n-spin :show="isLoading">
      <n-data-table
        :columns="columns"
        :data="predictions ?? []"
        :bordered="false"
      />
    </n-spin>

    <!-- Create Prediction Modal -->
    <n-modal
      v-model:show="showCreateModal"
      preset="card"
      title="Create Prediction"
      style="width: 500px"
      :mask-closable="false"
      @after-leave="resetCreateForm"
    >
      <n-form
        ref="createFormRef"
        :model="createFormData"
        :rules="createFormRules"
        label-placement="left"
        label-width="140px"
        require-mark-placement="right-hanging"
      >
        <n-form-item label="Sample ID" path="sample_id">
          <n-input
            v-model:value="createFormData.sample_id"
            placeholder="Enter sample ID"
            clearable
          />
        </n-form-item>

        <n-form-item label="Predicted Label" path="predicted_label">
          <n-input
            v-model:value="createFormData.predicted_label"
            placeholder="e.g. cat"
            clearable
          />
        </n-form-item>

        <n-form-item label="Score" path="score">
          <n-input-number
            v-model:value="createFormData.score"
            :min="0"
            :max="1"
            :step="0.01"
            :precision="4"
            placeholder="0.0 – 1.0"
            style="width: 100%"
          />
        </n-form-item>

        <n-form-item label="Model Artifact ID" path="model_artifact_id">
          <n-input
            v-model:value="createFormData.model_artifact_id"
            placeholder="Optional artifact ID"
            clearable
          />
        </n-form-item>
      </n-form>

      <template #footer>
        <n-space justify="end">
          <n-button @click="showCreateModal = false">Cancel</n-button>
          <n-button
            type="primary"
            :loading="createPrediction.isPending.value"
            @click="onCreateSubmit"
          >
            Create
          </n-button>
        </n-space>
      </template>
    </n-modal>

    <!-- Edit Prediction Modal -->
    <n-modal
      v-model:show="showEditModal"
      preset="card"
      title="Edit Prediction"
      style="width: 480px"
      :mask-closable="false"
      @after-leave="resetEditForm"
    >
      <n-form
        ref="editFormRef"
        :model="editFormData"
        :rules="editFormRules"
        label-placement="left"
        label-width="140px"
        require-mark-placement="right-hanging"
      >
        <n-form-item label="Corrected Label" path="corrected_label">
          <n-input
            v-model:value="editFormData.corrected_label"
            placeholder="Enter corrected label"
            clearable
          />
        </n-form-item>

        <n-form-item label="Edited By" path="edited_by">
          <n-input
            v-model:value="editFormData.edited_by"
            placeholder="Your name or ID"
            clearable
          />
        </n-form-item>
      </n-form>

      <template #footer>
        <n-space justify="end">
          <n-button @click="showEditModal = false">Cancel</n-button>
          <n-button
            type="primary"
            :loading="editPrediction.isPending.value"
            @click="onEditSubmit"
          >
            Save
          </n-button>
        </n-space>
      </template>
    </n-modal>
  </div>
</template>

<script setup lang="ts">
import { ref, h, watch } from "vue";
import { useMutation, useQuery, useQueryClient } from "@tanstack/vue-query";
import { useMessage, type FormInst, type FormRules } from "naive-ui";
import { NButton, NTag, NImage, NImageGroup } from "naive-ui";
import { api } from "../api";
import type { PredictionResult, Sample } from "../types";
import { resolveImageUri, resolveImageUris } from "../utils/imageAdapters";

// ─── message / query client ──────────────────────────────────────────────────
const message = useMessage();
const qc = useQueryClient();

// ─── query ───────────────────────────────────────────────────────────────────
const { data: predictions, isLoading, isError, error } = useQuery({
  queryKey: ["predictions"],
  queryFn: api.listPredictions,
});

// ─── sample image cache ──────────────────────────────────────────────────────
const sampleImageCache = ref<Record<string, string[]>>({});
const sampleLoadingSet = ref<Set<string>>(new Set());

async function fetchSampleImage(sampleId: string) {
  if (sampleImageCache.value[sampleId] || sampleLoadingSet.value.has(sampleId)) return;
  sampleLoadingSet.value.add(sampleId);
  try {
    const sample: Sample = await api.getSample(sampleId);
    sampleImageCache.value = { ...sampleImageCache.value, [sampleId]: sample.image_uris };
  } catch {
    // silently skip — preview just won't show
  } finally {
    sampleLoadingSet.value = new Set([...sampleLoadingSet.value].filter((id) => id !== sampleId));
  }
}

// Fetch sample images when predictions load
watch(
  () => predictions.value,
  (preds) => {
    if (!preds) return;
    const uniqueIds = [...new Set(preds.map((p) => p.sample_id))];
    uniqueIds.forEach((id) => fetchSampleImage(id));
  },
  { immediate: true }
);

// ─── create mutation ─────────────────────────────────────────────────────────
const createPrediction = useMutation({
  mutationFn: (body: {
    sample_id: string;
    predicted_label: string;
    score: number;
    model_artifact_id: string;
  }) => api.createPrediction(body),
  onSuccess: () => {
    message.success("Prediction created");
    qc.invalidateQueries({ queryKey: ["predictions"] });
    showCreateModal.value = false;
  },
  onError: (err: Error) => {
    message.error(err.message ?? "Failed to create prediction");
  },
});

// ─── edit mutation ────────────────────────────────────────────────────────────
const editPrediction = useMutation({
  mutationFn: ({ id, corrected_label, edited_by }: { id: string; corrected_label: string; edited_by: string }) =>
    api.editPrediction(id, { corrected_label, edited_by }),
  onSuccess: () => {
    message.success("Prediction updated");
    qc.invalidateQueries({ queryKey: ["predictions"] });
    showEditModal.value = false;
  },
  onError: (err: Error) => {
    message.error(err.message ?? "Failed to update prediction");
  },
});

// ─── create modal / form ─────────────────────────────────────────────────────
const showCreateModal = ref(false);
const createFormRef = ref<FormInst | null>(null);

const defaultCreateFormData = () => ({
  sample_id: "",
  predicted_label: "",
  score: null as number | null,
  model_artifact_id: "",
});

const createFormData = ref(defaultCreateFormData());

const createFormRules: FormRules = {
  sample_id: [
    {
      required: true,
      min: 1,
      message: "Sample ID is required",
      trigger: ["blur", "input"],
    },
  ],
  predicted_label: [
    {
      required: true,
      min: 1,
      message: "Predicted label is required",
      trigger: ["blur", "input"],
    },
  ],
  score: [
    {
      type: "number",
      min: 0,
      max: 1,
      message: "Score must be between 0 and 1",
      trigger: ["blur", "change"],
    },
  ],
};

function resetCreateForm() {
  createFormData.value = defaultCreateFormData();
}

function onCreateSubmit() {
  createFormRef.value?.validate((errors) => {
    if (errors) return;
    createPrediction.mutate({
      sample_id: createFormData.value.sample_id,
      predicted_label: createFormData.value.predicted_label,
      score: createFormData.value.score ?? 0,
      model_artifact_id: createFormData.value.model_artifact_id,
    });
  });
}

// ─── edit modal / form ────────────────────────────────────────────────────────
const showEditModal = ref(false);
const editFormRef = ref<FormInst | null>(null);
const editingPredictionId = ref<string>("");

const defaultEditFormData = () => ({
  corrected_label: "",
  edited_by: "",
});

const editFormData = ref(defaultEditFormData());

const editFormRules: FormRules = {
  corrected_label: [
    {
      required: true,
      min: 1,
      message: "Corrected label is required",
      trigger: ["blur", "input"],
    },
  ],
};

function resetEditForm() {
  editFormData.value = defaultEditFormData();
  editingPredictionId.value = "";
}

function openEditModal(row: PredictionResult) {
  editingPredictionId.value = row.id;
  editFormData.value = defaultEditFormData();
  showEditModal.value = true;
}

function onEditSubmit() {
  editFormRef.value?.validate((errors) => {
    if (errors) return;
    editPrediction.mutate({
      id: editingPredictionId.value,
      corrected_label: editFormData.value.corrected_label,
      edited_by: editFormData.value.edited_by,
    });
  });
}

// ─── table columns ────────────────────────────────────────────────────────────
const columns = [
  {
    title: "Preview",
    key: "preview",
    width: 72,
    render: (row: PredictionResult) => {
      const imageUris = sampleImageCache.value[row.sample_id];
      const srcs = resolveImageUris(imageUris);
      if (srcs.length === 1) {
        return h(NImage, {
          src: srcs[0],
          width: 48,
          height: 48,
          objectFit: "cover",
          style: "border-radius: 4px; cursor: pointer",
        });
      }
      return h(NImageGroup, null, {
        default: () =>
          srcs.map((src, i) =>
            h(NImage, {
              key: i,
              src,
              width: 48,
              height: 48,
              objectFit: "cover",
              style: i === 0
                ? "border-radius: 4px; cursor: pointer"
                : "display: none",
            })
          ),
      });
    },
  },
  {
    title: "ID",
    key: "id",
    render: (row: PredictionResult) =>
      h("span", { style: "font-family: monospace; font-size: 0.85em" }, row.id.slice(0, 8) + "…"),
  },
  {
    title: "Sample ID",
    key: "sample_id",
    render: (row: PredictionResult) =>
      h("span", { style: "font-family: monospace; font-size: 0.85em" }, row.sample_id.slice(0, 12) + (row.sample_id.length > 12 ? "…" : "")),
  },
  {
    title: "Predicted Label",
    key: "predicted_label",
    render: (row: PredictionResult) =>
      h(NTag, { type: "success", size: "small" }, { default: () => row.predicted_label }),
  },
  {
    title: "Score",
    key: "score",
    render: (row: PredictionResult) =>
      h("span", {}, typeof row.score === "number" ? row.score.toFixed(4) : "—"),
  },
  {
    title: "Actions",
    key: "actions",
    render: (row: PredictionResult) =>
      h(
        NButton,
        {
          size: "small",
          onClick: (e: MouseEvent) => {
            e.stopPropagation();
            openEditModal(row);
          },
        },
        { default: () => "Edit" }
      ),
  },
];
</script>
