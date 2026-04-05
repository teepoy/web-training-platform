<template>
  <n-space vertical size="large">
    <template v-if="!orgStore.currentOrgId">
      <div style="padding: 48px; text-align: center;">
        <n-empty description="You are not a member of any organization. Contact an admin." />
      </div>
    </template>
    <template v-else>
    <n-page-header title="Training Jobs">
      <template #extra>
        <n-button type="primary" @click="showModal = true">Start New Job</n-button>
      </template>
    </n-page-header>

    <n-spin :show="isLoading">
      <n-data-table
        :columns="columns"
        :data="jobs ?? []"
        :row-props="rowProps"
        :bordered="true"
        :striped="true"
        :loading="isLoading"
      />
    </n-spin>

    <n-modal
      v-model:show="showModal"
      preset="dialog"
      title="Start New Job"
      positive-text="Start"
      negative-text="Cancel"
      :loading="createJobMutation.isPending.value"
      @positive-click="onSubmit"
      @negative-click="onCancel"
    >
      <n-form
        ref="formRef"
        :model="formModel"
        :rules="formRules"
        label-placement="left"
        label-width="auto"
      >
        <n-form-item label="Dataset" path="dataset_id">
          <n-select
            v-model:value="formModel.dataset_id"
            :options="datasetOptions"
            :loading="datasetsLoading"
            placeholder="Select a dataset"
            filterable
          />
        </n-form-item>
        <n-form-item label="Preset" path="preset_id">
          <n-select
            v-model:value="formModel.preset_id"
            :options="presetOptions"
            :loading="presetsLoading"
            placeholder="Select a preset"
            filterable
          />
        </n-form-item>
      </n-form>
    </n-modal>
    </template>
  </n-space>
</template>

<script setup lang="ts">
import { ref, computed, h } from "vue";
import { useRouter } from "vue-router";
import { useMutation, useQuery, useQueryClient } from "@tanstack/vue-query";
import type { DataTableColumns, FormInst, FormRules, SelectOption } from "naive-ui";
import { useMessage, NTag, NButton } from "naive-ui";
import { api } from "../api";
import type { TrainingJob, JobStatus } from "../types";
import { useOrgStore } from "../stores/org";

const router = useRouter();
const message = useMessage();
const qc = useQueryClient();
const orgStore = useOrgStore();

// ---------------------------------------------------------------------------
// Queries
// ---------------------------------------------------------------------------

const { data: jobs, isLoading } = useQuery({
  queryKey: computed(() => ["jobs", orgStore.currentOrgId]),
  queryFn: api.listJobs,
  refetchInterval: 5000,
  enabled: computed(() => !!orgStore.currentOrgId),
});

const { data: datasets, isLoading: datasetsLoading } = useQuery({
  queryKey: computed(() => ["datasets", orgStore.currentOrgId]),
  queryFn: api.listDatasets,
  enabled: computed(() => !!orgStore.currentOrgId),
});

const { data: presets, isLoading: presetsLoading } = useQuery({
  queryKey: computed(() => ["presets", orgStore.currentOrgId]),
  queryFn: api.listPresets,
  enabled: computed(() => !!orgStore.currentOrgId),
});

// ---------------------------------------------------------------------------
// Select options
// ---------------------------------------------------------------------------

const datasetOptions = computed<SelectOption[]>(
  () => (datasets.value ?? []).map((d) => ({ label: d.name, value: d.id }))
);

const presetOptions = computed<SelectOption[]>(
  () => (presets.value ?? []).map((p) => ({ label: p.name, value: p.id }))
);

// ---------------------------------------------------------------------------
// Status tag helper
// ---------------------------------------------------------------------------

type TagType = "default" | "info" | "success" | "error" | "warning";

function statusType(status: JobStatus): TagType {
  const map: Record<JobStatus, TagType> = {
    queued: "default",
    running: "info",
    completed: "success",
    failed: "error",
    cancelled: "warning",
  };
  return map[status] ?? "default";
}

// ---------------------------------------------------------------------------
// Table columns
// ---------------------------------------------------------------------------

const columns = computed<DataTableColumns<TrainingJob>>(() => [
  {
    title: "ID",
    key: "id",
    width: 120,
    render: (row) => row.id.slice(0, 8) + "…",
  },
  {
    title: "Status",
    key: "status",
    width: 130,
    render: (row) =>
      h(
        NTag,
        { type: statusType(row.status), size: "small", round: true },
        { default: () => row.status }
      ),
  },
  {
    title: "Dataset ID",
    key: "dataset_id",
    ellipsis: { tooltip: true },
    render: (row) => row.dataset_id.slice(0, 8) + "…",
  },
  {
    title: "Preset ID",
    key: "preset_id",
    ellipsis: { tooltip: true },
    render: (row) => row.preset_id.slice(0, 8) + "…",
  },
  {
    title: "Created At",
    key: "created_at",
    width: 180,
    render: (row) => new Date(row.created_at).toLocaleString(),
  },
  {
    title: "Actions",
    key: "actions",
    width: 90,
    render: (row) =>
      h(
        NButton,
        {
          size: "small",
          onClick: (e: Event) => {
            e.stopPropagation();
            router.push("/jobs/" + row.id);
          },
        },
        { default: () => "View" }
      ),
  },
]);

// Row click also navigates
function rowProps(row: TrainingJob) {
  return {
    style: "cursor: pointer",
    onClick: () => router.push("/jobs/" + row.id),
  };
}

// ---------------------------------------------------------------------------
// Modal / form
// ---------------------------------------------------------------------------

const showModal = ref(false);
const formRef = ref<FormInst | null>(null);
const formModel = ref({ dataset_id: null as string | null, preset_id: null as string | null });

const formRules: FormRules = {
  dataset_id: [{ required: true, message: "Please select a dataset", trigger: ["blur", "change"] }],
  preset_id: [{ required: true, message: "Please select a preset", trigger: ["blur", "change"] }],
};

const createJobMutation = useMutation({
  mutationFn: ({ dataset_id, preset_id }: { dataset_id: string; preset_id: string }) =>
    api.createJob(dataset_id, preset_id),
  onSuccess: () => {
    qc.invalidateQueries({ queryKey: ["jobs", orgStore.currentOrgId] });
    message.success("Job started");
    showModal.value = false;
    resetForm();
  },
  onError: (err: Error) => {
    message.error(err.message ?? "Failed to start job");
  },
});

function onSubmit() {
  formRef.value?.validate((errors) => {
    if (errors) return;
    if (!formModel.value.dataset_id || !formModel.value.preset_id) return;
    createJobMutation.mutate({
      dataset_id: formModel.value.dataset_id,
      preset_id: formModel.value.preset_id,
    });
  });
  // Return false to keep modal open while validating/mutating
  return false;
}

function onCancel() {
  resetForm();
}

function resetForm() {
  formModel.value = { dataset_id: null, preset_id: null };
  formRef.value?.restoreValidation();
}
</script>
