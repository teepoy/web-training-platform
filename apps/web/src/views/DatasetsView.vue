<template>
  <div>
    <n-space justify="space-between" align="center" style="margin-bottom: 16px">
      <n-h2 style="margin: 0">Datasets</n-h2>
      <n-space>
        <n-button @click="onCreatePreset" :loading="createPreset.isPending.value">
          Create Default Preset
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

        <n-form-item label="Task Type" path="task_type">
          <n-select
            v-model:value="formData.task_type"
            :options="taskTypeOptions"
            placeholder="Select task type"
          />
        </n-form-item>

        <n-form-item label="Label Space" path="label_space">
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
  </div>
</template>

<script setup lang="ts">
import { ref, h } from "vue";
import { useRouter } from "vue-router";
import { useMutation, useQuery, useQueryClient } from "@tanstack/vue-query";
import { useMessage, type FormInst, type FormRules, type DataTableRowKey } from "naive-ui";
import { NButton, NTag } from "naive-ui";
import { api } from "../api";
import type { Dataset } from "../types";

// ─── router / message ───────────────────────────────────────────────────────
const router = useRouter();
const message = useMessage();
const qc = useQueryClient();

// ─── query ───────────────────────────────────────────────────────────────────
const { data: datasets, isLoading } = useQuery({
  queryKey: ["datasets"],
  queryFn: api.listDatasets,
});

// ─── mutations ───────────────────────────────────────────────────────────────
const createDataset = useMutation({
  mutationFn: (body: { name: string; task_type: string; label_space: string[] }) =>
    api.createDataset({
      name: body.name,
      task_spec: { task_type: body.task_type, label_space: body.label_space },
    }),
  onSuccess: () => {
    message.success("Dataset created");
    qc.invalidateQueries({ queryKey: ["datasets"] });
    showModal.value = false;
    resetForm();
  },
  onError: (err: Error) => {
    message.error(err.message ?? "Failed to create dataset");
  },
});

const createPreset = useMutation({
  mutationFn: () =>
    api.createPreset({
      name: "default-classification",
      model_spec: { architecture: "resnet18", num_classes: 2 },
      omegaconf_yaml: "trainer:\n  max_epochs: 3",
      dataloader_ref: "custom.loader:build",
    }),
  onSuccess: () => {
    message.success("Default preset created");
  },
  onError: (err: Error) => {
    message.error(err.message ?? "Failed to create preset");
  },
});

// ─── modal / form ────────────────────────────────────────────────────────────
const showModal = ref(false);
const formRef = ref<FormInst | null>(null);

const defaultFormData = () => ({
  name: "",
  task_type: null as string | null,
  label_space: [] as string[],
});

const formData = ref(defaultFormData());

const taskTypeOptions = [
  { label: "Classification", value: "classification" },
  { label: "Detection", value: "detection" },
];

const formRules: FormRules = {
  name: [
    {
      required: true,
      min: 1,
      message: "Name is required",
      trigger: ["blur", "input"],
    },
  ],
  task_type: [
    {
      required: true,
      message: "Task type is required",
      trigger: ["blur", "change"],
    },
  ],
};

function resetForm() {
  formData.value = defaultFormData();
}

function onSubmit() {
  formRef.value?.validate((errors) => {
    if (errors) return;
    createDataset.mutate({
      name: formData.value.name,
      task_type: formData.value.task_type!,
      label_space: formData.value.label_space,
    });
  });
}

function onCreatePreset() {
  createPreset.mutate();
}

// ─── table ───────────────────────────────────────────────────────────────────
const columns = [
  {
    title: "Name",
    key: "name",
    render: (row: Dataset) =>
      h("span", { style: "font-weight: 500" }, row.name),
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
    render: (row: Dataset) =>
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
