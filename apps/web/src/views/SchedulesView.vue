<template>
  <n-space vertical size="large">
    <template v-if="!orgStore.currentOrgId">
      <div style="padding: 48px; text-align: center;">
        <n-empty description="You are not a member of any organization. Contact an admin." />
      </div>
    </template>
    <template v-else>
    <n-page-header title="Schedules">
      <template #extra>
        <n-button style="margin-right: 8px" @click="router.push('/tasks')">Open Task Explorer</n-button>
        <n-button type="primary" @click="openCreateModal">Create Schedule</n-button>
      </template>
    </n-page-header>

    <n-spin :show="isLoading">
      <n-data-table
        :columns="columns"
        :data="schedules ?? []"
        :row-props="rowProps"
        :bordered="true"
        :striped="true"
        :loading="isLoading"
      />
    </n-spin>

    <!-- Create Schedule Modal -->
    <n-modal
      v-model:show="showModal"
      preset="dialog"
      title="Create Schedule"
      positive-text="Create"
      negative-text="Cancel"
      :loading="createMutation.isPending.value"
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
        <n-form-item label="Name" path="name">
          <n-input
            v-model:value="formModel.name"
            placeholder="my-schedule"
          />
        </n-form-item>
        <n-form-item label="Flow" path="flow_name">
          <n-select
            v-model:value="formModel.flow_name"
            :options="flowOptions"
            placeholder="Select a flow"
          />
        </n-form-item>
        <n-form-item label="Cron" path="cron">
          <n-input
            v-model:value="formModel.cron"
            placeholder="*/5 * * * *"
          />
        </n-form-item>
        <n-form-item label="Parameters" path="parameters">
          <n-input
            v-model:value="formModel.parameters"
            type="textarea"
            placeholder="{}"
            :autosize="{ minRows: 3, maxRows: 6 }"
          />
        </n-form-item>
        <n-form-item label="Description" path="description">
          <n-input
            v-model:value="formModel.description"
            placeholder="Optional description"
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
import type { DataTableColumns, FormInst, FormRules } from "naive-ui";
import { useMessage, NTag, NButton, NPopconfirm, NSpace } from "naive-ui";
import { api } from "../api";
import type { Schedule } from "../types";
import { useOrgStore } from "../stores/org";

const router = useRouter();
const message = useMessage();
const qc = useQueryClient();
const orgStore = useOrgStore();

// ---------------------------------------------------------------------------
// Query
// ---------------------------------------------------------------------------

const { data: schedules, isLoading } = useQuery({
  queryKey: computed(() => ["schedules", orgStore.currentOrgId]),
  queryFn: api.listSchedules,
  enabled: computed(() => !!orgStore.currentOrgId),
});

// ---------------------------------------------------------------------------
// Mutations
// ---------------------------------------------------------------------------

const createMutation = useMutation({
  mutationFn: (body: Parameters<typeof api.createSchedule>[0]) =>
    api.createSchedule(body),
  onSuccess: () => {
    qc.invalidateQueries({ queryKey: ["schedules", orgStore.currentOrgId] });
    message.success("Schedule created");
    showModal.value = false;
    resetForm();
  },
  onError: (err: Error) => message.error(err.message ?? "Failed to create schedule"),
});

const deleteMutation = useMutation({
  mutationFn: (id: string) => api.deleteSchedule(id),
  onSuccess: () => {
    qc.invalidateQueries({ queryKey: ["schedules", orgStore.currentOrgId] });
    message.success("Schedule deleted");
  },
  onError: (err: Error) => message.error(err.message ?? "Failed to delete schedule"),
});

const pauseMutation = useMutation({
  mutationFn: (id: string) => api.pauseSchedule(id),
  onSuccess: () => {
    qc.invalidateQueries({ queryKey: ["schedules", orgStore.currentOrgId] });
    message.success("Schedule paused");
  },
  onError: (err: Error) => message.error(err.message ?? "Failed to pause schedule"),
});

const resumeMutation = useMutation({
  mutationFn: (id: string) => api.resumeSchedule(id),
  onSuccess: () => {
    qc.invalidateQueries({ queryKey: ["schedules", orgStore.currentOrgId] });
    message.success("Schedule resumed");
  },
  onError: (err: Error) => message.error(err.message ?? "Failed to resume schedule"),
});

// ---------------------------------------------------------------------------
// Table columns
// ---------------------------------------------------------------------------

const columns = computed<DataTableColumns<Schedule>>(() => [
  {
    title: "Name",
    key: "name",
    ellipsis: { tooltip: true },
  },
  {
    title: "Flow",
    key: "flow_name",
    width: 160,
  },
  {
    title: "Cron",
    key: "cron",
    width: 160,
    render: (row) => row.cron ?? "—",
  },
  {
    title: "Status",
    key: "is_schedule_active",
    width: 110,
    render: (row) =>
      h(
        NTag,
        {
          type: row.is_schedule_active ? "success" : "warning",
          size: "small",
          round: true,
        },
        { default: () => (row.is_schedule_active ? "active" : "paused") }
      ),
  },
  {
    title: "Actions",
    key: "actions",
    width: 240,
    render: (row) =>
      h(NSpace, { size: "small" }, {
        default: () => [
          h(
            NButton,
            {
              size: "small",
              onClick: (e: Event) => {
                e.stopPropagation();
                router.push("/schedules/" + row.id);
              },
            },
            { default: () => "View" }
          ),
          h(
            NButton,
            {
              size: "small",
              type: row.is_schedule_active ? "warning" : "primary",
              loading:
                (row.is_schedule_active
                  ? pauseMutation.isPending.value
                  : resumeMutation.isPending.value),
              onClick: (e: Event) => {
                e.stopPropagation();
                if (row.is_schedule_active) {
                  pauseMutation.mutate(row.id);
                } else {
                  resumeMutation.mutate(row.id);
                }
              },
            },
            { default: () => (row.is_schedule_active ? "Pause" : "Resume") }
          ),
          h(
            NPopconfirm,
            {
              onPositiveClick: (e: MouseEvent) => {
                e.stopPropagation();
                deleteMutation.mutate(row.id);
              },
            },
            {
              trigger: () =>
                h(
                  NButton,
                  {
                    size: "small",
                    type: "error",
                    loading: deleteMutation.isPending.value,
                    onClick: (e: Event) => e.stopPropagation(),
                  },
                  { default: () => "Delete" }
                ),
              default: () => "Are you sure you want to delete this schedule?",
            }
          ),
        ],
      }),
  },
]);

// Row click navigates to detail
function rowProps(row: Schedule) {
  return {
    style: "cursor: pointer",
    onClick: () => router.push("/schedules/" + row.id),
  };
}

// ---------------------------------------------------------------------------
// Modal / form
// ---------------------------------------------------------------------------

const showModal = ref(false);
const formRef = ref<FormInst | null>(null);

const formModel = ref({
  name: "",
  flow_name: null as string | null,
  cron: "",
  parameters: "{}",
  description: "",
});

const flowOptions = [
  { label: "drain-dataset", value: "drain-dataset" },
];

const formRules: FormRules = {
  name: [{ required: true, message: "Name is required", trigger: ["blur", "input"] }],
  flow_name: [{ required: true, message: "Please select a flow", trigger: ["blur", "change"] }],
  cron: [
    { required: true, message: "Cron expression is required", trigger: ["blur", "input"] },
    {
      validator: (_rule: unknown, value: string) => {
        if (!value) return true;
        const parts = value.trim().split(/\s+/);
        return parts.length === 5 || new Error("Cron must have exactly 5 fields (min hour dom month dow)");
      },
      trigger: ["blur"],
    },
  ],
};

function openCreateModal() {
  resetForm();
  showModal.value = true;
}

function onSubmit() {
  formRef.value?.validate((errors) => {
    if (errors) return;
    if (!formModel.value.flow_name) return;

    // Parse parameters JSON
    let parsedParams: Record<string, unknown> = {};
    try {
      parsedParams = JSON.parse(formModel.value.parameters || "{}");
      if (typeof parsedParams !== "object" || Array.isArray(parsedParams) || parsedParams === null) {
        message.error("Parameters must be a JSON object");
        return;
      }
    } catch {
      message.error("Parameters is not valid JSON");
      return;
    }

    createMutation.mutate({
      name: formModel.value.name,
      flow_name: formModel.value.flow_name,
      cron: formModel.value.cron,
      parameters: parsedParams,
      description: formModel.value.description || undefined,
    });
  });
  // Return false to keep modal open while validating/mutating
  return false;
}

function onCancel() {
  resetForm();
}

function resetForm() {
  formModel.value = {
    name: "",
    flow_name: null,
    cron: "",
    parameters: "{}",
    description: "",
  };
  formRef.value?.restoreValidation();
}
</script>
