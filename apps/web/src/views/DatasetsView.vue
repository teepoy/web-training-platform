<template>
  <div>
    <template v-if="!orgStore.currentOrgId">
      <div style="padding: 48px; text-align: center;">
        <n-empty description="You are not a member of any organization. Contact an admin." />
      </div>
    </template>
    <template v-else>
    <n-space justify="space-between" align="center" style="margin-bottom: 16px">
      <n-h2 style="margin: 0">Datasets</n-h2>
      <n-space>
        <n-button @click="showImportModal = true">
          Import Dataset
        </n-button>
        <n-button type="primary" @click="showModal = true">
          + New Dataset
        </n-button>
      </n-space>
    </n-space>

    <n-spin :show="isLoading">
      <n-data-table
        :columns="columns"
        :data="datasets ?? []"
        :row-props="rowProps"
        :bordered="false"
        style="cursor: pointer"
      />
    </n-spin>

    <!-- Create Dataset Modal -->
    <n-modal
      v-model:show="showModal"
      preset="card"
      title="New Dataset"
      style="width: 480px"
      :mask-closable="false"
    >
      <n-form
        ref="formRef"
        :model="formData"
        :rules="formRules"
        label-placement="left"
        label-width="110px"
        require-mark-placement="right-hanging"
      >
        <n-form-item label="Name" path="name">
          <n-input
            v-model:value="formData.name"
            placeholder="e.g. my-dataset"
            clearable
          />
        </n-form-item>

        <n-form-item label="Dataset Type" path="dataset_type">
          <n-select
            v-model:value="formData.dataset_type"
            :options="datasetTypeOptions"
            placeholder="Select dataset type"
          />
        </n-form-item>

        <n-form-item label="Task Type" path="task_type">
          <n-input :value="formData.task_type ?? ''" disabled />
        </n-form-item>

        <n-form-item v-if="formData.dataset_type === 'image_classification'" label="Label Space" path="label_space">
          <n-dynamic-tags v-model:value="formData.label_space" />
        </n-form-item>
      </n-form>

      <template #footer>
        <n-space justify="end">
          <n-button @click="showModal = false">Cancel</n-button>
          <n-button
            type="primary"
            :loading="createDataset.isPending.value"
            @click="onSubmit"
          >
            Create
          </n-button>
        </n-space>
      </template>
      </n-modal>

      <n-modal
        v-model:show="showImportModal"
        preset="card"
        title="Import Dataset"
        style="width: 560px"
        :mask-closable="false"
      >
        <n-form label-placement="left" label-width="110px">
          <n-form-item label="Name">
            <n-input v-model:value="importForm.name" placeholder="e.g. imported-dataset" clearable />
          </n-form-item>

          <n-form-item label="Dataset Type">
            <n-select
              v-model:value="importForm.dataset_type"
              :options="datasetTypeOptions"
              placeholder="Select dataset type"
            />
          </n-form-item>

          <n-form-item label="Task Type">
            <n-input :value="importForm.task_type ?? ''" disabled />
          </n-form-item>

          <n-form-item v-if="importForm.dataset_type === 'image_classification'" label="Label Space">
            <n-dynamic-tags v-model:value="importForm.label_space" />
          </n-form-item>

          <n-form-item label="Samples JSON">
            <input type="file" accept="application/json" @change="handleImportFileChange" />
          </n-form-item>

          <n-alert v-if="importFileName" type="info" :show-icon="false">
            {{ importFileName }}
          </n-alert>
        </n-form>

        <template #footer>
          <n-space justify="end">
            <n-button @click="closeImportModal">Cancel</n-button>
            <n-button type="primary" :loading="importDataset.isPending.value" @click="onImportDataset">
              Import
            </n-button>
          </n-space>
        </template>
      </n-modal>
    </template>
  </div>
</template>

<script setup lang="ts">
import { ref, h, computed, watch } from "vue";
import { useRouter } from "vue-router";
import { useMutation, useQuery, useQueryClient } from "@tanstack/vue-query";
import { useMessage, type FormInst, type FormRules, type DataTableRowKey } from "naive-ui";
import { NButton, NTag } from "naive-ui";
import { api } from "../api";
import type { BulkCreateSampleItem, Dataset } from "../types";
import { useOrgStore } from "../stores/org";
import { useAuthStore } from "../stores/auth";

// ─── router / message ───────────────────────────────────────────────────────
const router = useRouter();
const message = useMessage();
const qc = useQueryClient();
const orgStore = useOrgStore();
const authStore = useAuthStore();

// ─── query ───────────────────────────────────────────────────────────────────
const { data: datasets, isLoading } = useQuery({
  queryKey: computed(() => ["datasets", orgStore.currentOrgId]),
  queryFn: api.listDatasets,
  enabled: computed(() => !!orgStore.currentOrgId),
});

// ─── mutations ───────────────────────────────────────────────────────────────
const createDataset = useMutation({
  mutationFn: (body: { name: string; dataset_type: string; task_type: string; label_space: string[] }) =>
    api.createDataset({
      name: body.name,
      dataset_type: body.dataset_type,
      task_spec: { task_type: body.task_type, label_space: body.label_space },
    }),
  onSuccess: () => {
    message.success("Dataset created");
    qc.invalidateQueries({ queryKey: ["datasets", orgStore.currentOrgId] });
    showModal.value = false;
    resetForm();
  },
  onError: (err: Error) => {
    message.error(err.message ?? "Failed to create dataset");
  },
});

const toggleDatasetPublic = useMutation({
  mutationFn: ({ id, isPublic }: { id: string; isPublic: boolean }) =>
    api.toggleDatasetPublic(id, isPublic),
  onSuccess: () => {
    qc.invalidateQueries({ queryKey: ["datasets", orgStore.currentOrgId] });
  },
  onError: (err: Error) => {
    message.error(err.message ?? "Failed to update visibility");
  },
});

const importDataset = useMutation({
  mutationFn: async (payload: {
    name: string;
    dataset_type: string;
    task_type: string;
    label_space: string[];
    items: BulkCreateSampleItem[];
  }) => {
    const dataset = await api.createDataset({
      name: payload.name,
      dataset_type: payload.dataset_type,
      task_spec: { task_type: payload.task_type, label_space: payload.label_space },
    });
    const chunkSize = 5000;
    for (let offset = 0; offset < payload.items.length; offset += chunkSize) {
      const chunk = payload.items.slice(offset, offset + chunkSize);
      await api.importSamples(dataset.id, chunk);
    }
    return dataset;
  },
  onSuccess: () => {
    message.success("Dataset imported");
    qc.invalidateQueries({ queryKey: ["datasets", orgStore.currentOrgId] });
    closeImportModal();
  },
  onError: (err: Error) => {
    message.error(err.message ?? "Failed to import dataset");
  },
});

// ─── modal / form ────────────────────────────────────────────────────────────
const showModal = ref(false);
const showImportModal = ref(false);
const formRef = ref<FormInst | null>(null);

const defaultFormData = () => ({
  name: "",
  dataset_type: null as string | null,
  task_type: null as string | null,
  label_space: [] as string[],
});

const formData = ref(defaultFormData());
const importForm = ref(defaultFormData());
const importItems = ref<BulkCreateSampleItem[]>([]);
const importFileName = ref("");

const datasetTypeOptions = [
  { label: "Image Classification", value: "image_classification" },
  { label: "Image VQA", value: "image_vqa" },
];

function taskTypeForDatasetType(datasetType: string | null): string | null {
  if (datasetType === "image_classification") {
    return "classification";
  }
  if (datasetType === "image_vqa") {
    return "vqa";
  }
  return null;
}

const formRules: FormRules = {
  name: [
    {
      required: true,
      min: 1,
      message: "Name is required",
      trigger: ["blur", "input"],
    },
  ],
  dataset_type: [
    {
      required: true,
      message: "Dataset type is required",
      trigger: ["blur", "change"],
    },
  ],
  label_space: [
    {
      validator: () => {
        if (formData.value.dataset_type === "image_classification" && formData.value.label_space.length === 0) {
          return new Error("Label space is required for image classification datasets");
        }
        return true;
      },
      trigger: ["blur", "change"],
    },
  ],
};

function resetForm() {
  formData.value = defaultFormData();
}

function resetImportForm() {
  importForm.value = defaultFormData();
  importItems.value = [];
  importFileName.value = "";
}

function closeImportModal() {
  showImportModal.value = false;
  resetImportForm();
}

function onSubmit() {
  formRef.value?.validate((errors) => {
    if (errors) return;
    createDataset.mutate({
      name: formData.value.name,
      dataset_type: formData.value.dataset_type!,
      task_type: formData.value.task_type!,
      label_space: formData.value.label_space,
    });
  });
}

watch(
  () => formData.value.dataset_type,
  (datasetType) => {
    formData.value.task_type = taskTypeForDatasetType(datasetType);
    if (datasetType === "image_vqa") {
      formData.value.label_space = [];
    }
  }
);

watch(
  () => importForm.value.dataset_type,
  (datasetType) => {
    importForm.value.task_type = taskTypeForDatasetType(datasetType);
    if (datasetType === "image_vqa") {
      importForm.value.label_space = [];
    }
  }
);

async function handleImportFileChange(event: Event) {
  const target = event.target as HTMLInputElement;
  const file = target.files?.[0];
  if (!file) {
    importItems.value = [];
    importFileName.value = "";
    return;
  }
  try {
    const text = await file.text();
    const parsed = JSON.parse(text);
    if (!Array.isArray(parsed)) {
      throw new Error("Import file must be a JSON array of sample items");
    }
    importItems.value = parsed.map((item) => ({
      image_uris: Array.isArray(item?.image_uris) ? item.image_uris.map(String) : [],
      metadata: typeof item?.metadata === "object" && item?.metadata !== null ? item.metadata as Record<string, unknown> : {},
      label: item?.label == null ? null : String(item.label),
    }));
    importFileName.value = `${file.name} (${importItems.value.length} samples)`;
  } catch (err: unknown) {
    importItems.value = [];
    importFileName.value = "";
    message.error((err as Error).message ?? "Failed to parse import file");
  }
}

function onImportDataset() {
  if (!importForm.value.name || !importForm.value.dataset_type || !importForm.value.task_type) {
    message.error("Dataset name and type are required");
    return;
  }
  if (importForm.value.dataset_type === "image_classification" && importForm.value.label_space.length === 0) {
    message.error("Label space is required for image classification datasets");
    return;
  }
  if (importItems.value.length === 0) {
    message.error("Select a JSON file with samples to import");
    return;
  }
  importDataset.mutate({
    name: importForm.value.name,
    dataset_type: importForm.value.dataset_type,
    task_type: importForm.value.task_type,
    label_space: importForm.value.label_space,
    items: importItems.value,
  });
}

// ─── table ───────────────────────────────────────────────────────────────────
const columns = [
  {
    title: "Name",
    key: "name",
    render: (row: Dataset) => {
      const nodes = [h("span", { style: "font-weight: 500" }, row.name)];
      if (row.is_public) {
        nodes.push(
          h(NTag, { type: "info", size: "small", style: "margin-left: 6px" }, { default: () => "Public" })
        );
      }
      if (row.is_public && row.org_id !== orgStore.currentOrgId) {
        nodes.push(
          h("span", { style: "margin-left: 4px; font-size: 12px; color: #aaa" }, `(${row.org_name ?? "Other Org"})`)
        );
      }
      return h("span", {}, nodes);
    },
  },
  {
    title: "Dataset Type",
    key: "dataset_type",
    render: (row: Dataset) =>
      h(NTag, { type: "default", size: "small" }, { default: () => row.dataset_type }),
  },
  {
    title: "Task Type",
    key: "task_type",
    render: (row: Dataset) =>
      h(NTag, { type: "info", size: "small" }, { default: () => row.task_spec.task_type }),
  },
  {
    title: "Created At",
    key: "created_at",
    render: (row: Dataset) =>
      h("span", {}, new Date(row.created_at).toLocaleString()),
  },
  {
    title: "Actions",
    key: "actions",
    render: (row: Dataset) => {
      const nodes = [
        h(
          NButton,
          {
            size: "small",
            onClick: (e: MouseEvent) => {
              e.stopPropagation();
              router.push(`/datasets/${row.id}`);
            },
          },
          { default: () => "View" }
        ),
      ];
      if (authStore.user?.is_superadmin === true && row.org_id === orgStore.currentOrgId) {
        nodes.push(
          h(
            NButton,
            {
              size: "small",
              style: "margin-left: 6px",
              onClick: (e: MouseEvent) => {
                e.stopPropagation();
                toggleDatasetPublic.mutate({ id: row.id, isPublic: !row.is_public });
              },
            },
            { default: () => (row.is_public ? "Make Private" : "Make Public") }
          )
        );
      }
      return h("span", {}, nodes);
    },
  },
];

function rowProps(row: Dataset) {
  return {
    onClick: () => {
      router.push(`/datasets/${row.id}`);
    },
  };
}
</script>
