<template>
  <div>
    <template v-if="!orgStore.currentOrgId">
      <div style="padding: 48px; text-align: center;">
        <n-empty description="You are not a member of any organization. Contact an admin." />
      </div>
    </template>
    <template v-else>
    <n-space justify="space-between" align="center" style="margin-bottom: 16px">
      <n-h2 style="margin: 0">Training Presets</n-h2>
      <n-button type="primary" @click="showModal = true">
        + Create Preset
      </n-button>
    </n-space>

    <n-spin :show="isLoading">
      <n-alert v-if="isError" type="error" style="margin-bottom: 12px">
        Failed to load presets: {{ (error as Error)?.message ?? 'Unknown error' }}
      </n-alert>
      <n-data-table
        :columns="columns"
        :data="presets ?? []"
        :bordered="false"
      />
    </n-spin>

    <!-- Create Preset Modal -->
    <n-modal
      v-model:show="showModal"
      preset="card"
      title="Create Preset"
      style="width: 560px"
      :mask-closable="false"
      @after-leave="resetForm"
    >
      <n-form
        ref="formRef"
        :model="formData"
        :rules="formRules"
        label-placement="left"
        label-width="130px"
        require-mark-placement="right-hanging"
      >
        <!-- Name -->
        <n-form-item label="Name" path="name">
          <n-input
            v-model:value="formData.name"
            placeholder="e.g. resnet18-cls"
            clearable
          />
        </n-form-item>

        <!-- Architecture -->
        <n-form-item label="Architecture" path="architecture">
          <n-select
            v-model:value="formData.architecture"
            :options="architectureOptions"
            filterable
            tag
            placeholder="Select or type architecture"
          />
        </n-form-item>

        <!-- Num Classes -->
        <n-form-item label="Num Classes" path="num_classes">
          <n-input-number
            v-model:value="formData.num_classes"
            :min="2"
            placeholder="e.g. 10"
            style="width: 100%"
          />
        </n-form-item>

        <!-- OmegaConf YAML -->
        <n-form-item label="OmegaConf YAML" path="omegaconf_yaml">
          <n-input
            v-model:value="formData.omegaconf_yaml"
            type="textarea"
            :rows="6"
            placeholder="lr: 0.001&#10;batch_size: 32&#10;epochs: 10"
          />
        </n-form-item>

        <!-- Dataloader Ref (optional) -->
        <n-form-item label="Dataloader Ref" path="dataloader_ref">
          <n-input
            v-model:value="formData.dataloader_ref"
            placeholder="e.g. custom.loader:build (optional)"
            clearable
          />
        </n-form-item>
      </n-form>

      <template #footer>
        <n-space justify="end">
          <n-button @click="showModal = false">Cancel</n-button>
          <n-button
            type="primary"
            :loading="createPresetMutation.isPending.value"
            @click="onSubmit"
          >
            Create
          </n-button>
        </n-space>
      </template>
    </n-modal>
    </template>
  </div>
</template>

<script setup lang="ts">
import { ref, h, computed } from "vue";
import { useMutation, useQuery, useQueryClient } from "@tanstack/vue-query";
import { useMessage, type FormInst, type FormRules } from "naive-ui";
import { NTag } from "naive-ui";
import { api } from "../api";
import type { TrainingPreset } from "../types";
import { useOrgStore } from "../stores/org";

// ─── message / query client ──────────────────────────────────────────────────
const message = useMessage();
const qc = useQueryClient();
const orgStore = useOrgStore();

// ─── query ───────────────────────────────────────────────────────────────────
const { data: presets, isLoading, isError, error } = useQuery({
  queryKey: computed(() => ["presets", orgStore.currentOrgId]),
  queryFn: api.listPresets,
  enabled: computed(() => !!orgStore.currentOrgId),
});

// ─── mutation ────────────────────────────────────────────────────────────────
const createPresetMutation = useMutation({
  mutationFn: (data: {
    name: string;
    architecture: string;
    num_classes: number;
    omegaconf_yaml: string;
    dataloader_ref: string;
  }) =>
    api.createPreset({
      name: data.name,
      model_spec: {
        architecture: data.architecture,
        num_classes: data.num_classes,
      },
      omegaconf_yaml: data.omegaconf_yaml,
      dataloader_ref: data.dataloader_ref || undefined,
    }),
  onSuccess: () => {
    message.success("Preset created");
    qc.invalidateQueries({ queryKey: ["presets", orgStore.currentOrgId] });
    showModal.value = false;
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
  architecture: null as string | null,
  num_classes: null as number | null,
  omegaconf_yaml: "",
  dataloader_ref: "",
});

const formData = ref(defaultFormData());

const architectureOptions = [
  { label: "resnet18", value: "resnet18" },
  { label: "resnet50", value: "resnet50" },
  { label: "bert-base", value: "bert-base" },
];

const formRules: FormRules = {
  name: [
    {
      required: true,
      message: "Name is required",
      trigger: "blur",
    },
  ],
  architecture: [
    {
      required: true,
      message: "Architecture is required",
      trigger: ["blur", "change"],
    },
  ],
  num_classes: [
    {
      required: true,
      type: "number",
      min: 2,
      message: "Num classes must be at least 2",
      trigger: ["blur", "change"],
    },
  ],
  omegaconf_yaml: [
    {
      required: true,
      message: "YAML config required",
      trigger: ["blur", "input"],
    },
  ],
};

function resetForm() {
  formData.value = defaultFormData();
}

function onSubmit() {
  formRef.value?.validate((errors) => {
    if (errors) return;
    createPresetMutation.mutate({
      name: formData.value.name,
      architecture: formData.value.architecture!,
      num_classes: formData.value.num_classes!,
      omegaconf_yaml: formData.value.omegaconf_yaml,
      dataloader_ref: formData.value.dataloader_ref,
    });
  });
}

// ─── table columns ────────────────────────────────────────────────────────────
const columns = [
  {
    title: "Name",
    key: "name",
    render: (row: TrainingPreset) =>
      h("span", { style: "font-weight: 500" }, row.name),
  },
  {
    title: "Architecture",
    key: "architecture",
    render: (row: TrainingPreset) =>
      h(NTag, { type: "info", size: "small" }, { default: () => row.model_spec.architecture }),
  },
  {
    title: "Num Classes",
    key: "num_classes",
    render: (row: TrainingPreset) =>
      h("span", {}, String(row.model_spec.num_classes)),
  },
  {
    title: "Actions",
    key: "actions",
    render: (row: TrainingPreset) =>
      h(
        "span",
        { style: "color: var(--n-text-color-3); font-size: 12px" },
        row.id.slice(0, 8)
      ),
  },
];
</script>
