<template>
  <n-space vertical size="large">
    <n-page-header :title="schedule?.name ?? 'Schedule Detail'" @back="router.push('/schedules')">
      <template #subtitle>
        <n-tag :type="schedule?.is_schedule_active ? 'success' : 'warning'" size="small" round>
          {{ schedule?.is_schedule_active ? 'Active' : 'Paused' }}
        </n-tag>
      </template>
      <template #extra>
        <n-space>
          <n-button
            v-if="schedule"
            size="small"
            :loading="pauseMutation.isPending.value || resumeMutation.isPending.value"
            @click="onTogglePause"
          >
            {{ schedule.is_schedule_active ? 'Pause' : 'Resume' }}
          </n-button>
          <n-button size="small" @click="showEditModal = true">Edit</n-button>
          <n-button
            size="small"
            type="primary"
            :loading="triggerMutation.isPending.value"
            @click="onTrigger"
          >
            Trigger Now
          </n-button>
          <n-button
            size="small"
            type="error"
            :loading="deleteMutation.isPending.value"
            @click="onDelete"
          >
            Delete
          </n-button>
          <n-button
            v-if="schedule?.prefect_deployment_id"
            size="small"
            tag="a"
            :href="`http://localhost:4200/deployments/${schedule.prefect_deployment_id}`"
            target="_blank"
          >
            View in Prefect ↗
          </n-button>
        </n-space>
      </template>
    </n-page-header>

    <n-spin :show="scheduleLoading">
      <n-card v-if="schedule">
        <n-descriptions label-placement="left" :column="2" bordered>
          <n-descriptions-item label="Flow Name">{{ schedule.flow_name }}</n-descriptions-item>
          <n-descriptions-item label="Cron">{{ schedule.cron ?? '—' }}</n-descriptions-item>
          <n-descriptions-item label="Description">{{ schedule.description || '—' }}</n-descriptions-item>
          <n-descriptions-item label="Deployment ID">
            {{ schedule.prefect_deployment_id || '—' }}
          </n-descriptions-item>
          <n-descriptions-item label="Created">
            {{ schedule.created ? new Date(schedule.created).toLocaleString() : '—' }}
          </n-descriptions-item>
          <n-descriptions-item label="Updated">
            {{ schedule.updated ? new Date(schedule.updated).toLocaleString() : '—' }}
          </n-descriptions-item>
        </n-descriptions>
      </n-card>
    </n-spin>

    <n-card title="Run History">
      <n-spin :show="runsLoading">
        <n-data-table
          :columns="runColumns"
          :data="runs ?? []"
          :bordered="true"
          :striped="true"
          :row-props="runRowProps"
          :loading="runsLoading"
        />
      </n-spin>
      <div v-if="selectedRunId" style="margin-top: 16px;">
        <RunLogViewer :runId="selectedRunId" />
      </div>
    </n-card>
  </n-space>

  <n-modal
    v-model:show="showEditModal"
    preset="dialog"
    title="Edit Schedule"
    positive-text="Save"
    negative-text="Cancel"
    :loading="updateMutation.isPending.value"
    @positive-click="onEditSubmit"
    @negative-click="showEditModal = false"
  >
    <n-form ref="editFormRef" :model="editForm" label-placement="left" label-width="auto">
      <n-form-item label="Cron">
        <n-input v-model:value="editForm.cron" placeholder="*/5 * * * *" />
      </n-form-item>
      <n-form-item label="Parameters">
        <n-input v-model:value="editForm.parameters" type="textarea" placeholder="{}" :autosize="{ minRows: 3, maxRows: 6 }" />
      </n-form-item>
      <n-form-item label="Description">
        <n-input v-model:value="editForm.description" placeholder="Optional description" />
      </n-form-item>
    </n-form>
  </n-modal>
</template>

<script setup lang="ts">
import { ref, computed, h, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import { useMutation, useQuery, useQueryClient } from "@tanstack/vue-query";
import type { DataTableColumns, FormInst } from "naive-ui";
import {
  useMessage,
  NTag,
  NButton,
  NPageHeader,
  NDescriptions,
  NDescriptionsItem,
  NDataTable,
  NSpace,
  NCard,
  NSpin,
  NModal,
  NForm,
  NFormItem,
  NInput,
} from "naive-ui";
import { api } from "../api";
import type { ScheduleRun } from "../types";
import type { UpdateScheduleBody } from "../api";
import RunLogViewer from "../components/RunLogViewer.vue";

const route = useRoute();
const router = useRouter();
const message = useMessage();
const qc = useQueryClient();

const id = computed(() => route.params.id as string);

// ---------------------------------------------------------------------------
// Queries
// ---------------------------------------------------------------------------

const { data: schedule, isLoading: scheduleLoading } = useQuery({
  queryKey: computed(() => ["schedule", id.value]),
  queryFn: () => api.getSchedule(id.value),
});

const { data: runs, isLoading: runsLoading } = useQuery({
  queryKey: computed(() => ["schedule-runs", id.value]),
  queryFn: () => api.listScheduleRuns(id.value),
});

// ---------------------------------------------------------------------------
// Mutations
// ---------------------------------------------------------------------------

const triggerMutation = useMutation({
  mutationFn: () => api.triggerScheduleRun(id.value),
  onSuccess: () => {
    qc.invalidateQueries({ queryKey: ["schedule-runs", id.value] });
    message.success("Run triggered");
  },
  onError: (err: Error) => {
    message.error(err.message ?? "Failed to trigger run");
  },
});

const pauseMutation = useMutation({
  mutationFn: () => api.pauseSchedule(id.value),
  onSuccess: () => {
    qc.invalidateQueries({ queryKey: ["schedule", id.value] });
    message.success("Schedule paused");
  },
  onError: (err: Error) => {
    message.error(err.message ?? "Failed to pause schedule");
  },
});

const resumeMutation = useMutation({
  mutationFn: () => api.resumeSchedule(id.value),
  onSuccess: () => {
    qc.invalidateQueries({ queryKey: ["schedule", id.value] });
    message.success("Schedule resumed");
  },
  onError: (err: Error) => {
    message.error(err.message ?? "Failed to resume schedule");
  },
});

const deleteMutation = useMutation({
  mutationFn: () => api.deleteSchedule(id.value),
  onSuccess: () => {
    message.success("Schedule deleted");
    router.push("/schedules");
  },
  onError: (err: Error) => {
    message.error(err.message ?? "Failed to delete schedule");
  },
});

// ---------------------------------------------------------------------------
// Edit modal
// ---------------------------------------------------------------------------

const showEditModal = ref(false);
const editFormRef = ref<FormInst | null>(null);
const editForm = ref({ cron: "", parameters: "{}", description: "" });

watch(
  schedule,
  (s) => {
    if (s) {
      editForm.value = {
        cron: s.cron ?? "",
        parameters: JSON.stringify(s.parameters ?? {}, null, 2),
        description: s.description ?? "",
      };
    }
  },
  { immediate: true }
);

const updateMutation = useMutation({
  mutationFn: (body: UpdateScheduleBody) => api.updateSchedule(id.value, body),
  onSuccess: () => {
    qc.invalidateQueries({ queryKey: ["schedule", id.value] });
    message.success("Schedule updated");
    showEditModal.value = false;
  },
  onError: (err: Error) => {
    message.error(err.message ?? "Failed to update schedule");
  },
});

function onEditSubmit() {
  let parsedParams: Record<string, unknown>;
  try {
    parsedParams = JSON.parse(editForm.value.parameters);
  } catch {
    message.error("Parameters must be valid JSON");
    return false;
  }

  const body: UpdateScheduleBody = {};
  if (editForm.value.cron !== (schedule.value?.cron ?? "")) {
    body.cron = editForm.value.cron;
  }
  if (
    JSON.stringify(parsedParams) !==
    JSON.stringify(schedule.value?.parameters ?? {})
  ) {
    body.parameters = parsedParams;
  }
  if (editForm.value.description !== (schedule.value?.description ?? "")) {
    body.description = editForm.value.description;
  }

  updateMutation.mutate(body);
  return false;
}

// ---------------------------------------------------------------------------
// Handlers
// ---------------------------------------------------------------------------

function onTrigger() {
  triggerMutation.mutate();
}

function onTogglePause() {
  if (schedule.value?.is_schedule_active) {
    pauseMutation.mutate();
  } else {
    resumeMutation.mutate();
  }
}

function onDelete() {
  deleteMutation.mutate();
}

// ---------------------------------------------------------------------------
// Run state helpers
// ---------------------------------------------------------------------------

type TagType = "default" | "info" | "success" | "error" | "warning";

function runStateType(stateType: string | null): TagType {
  switch (stateType) {
    case "COMPLETED":
      return "success";
    case "RUNNING":
      return "info";
    case "FAILED":
    case "CRASHED":
      return "error";
    case "CANCELLED":
      return "warning";
    case "PENDING":
    case "SCHEDULED":
    default:
      return "default";
  }
}

function formatDuration(totalRunTime: number | null): string {
  if (totalRunTime === null) return "—";
  if (totalRunTime > 60) return ">1m";
  return `${totalRunTime.toFixed(1)}s`;
}

// ---------------------------------------------------------------------------
// Table
// ---------------------------------------------------------------------------

const selectedRunId = ref<string | null>(null);

const runColumns = computed<DataTableColumns<ScheduleRun>>(() => [
  {
    title: "Run Name",
    key: "name",
    ellipsis: { tooltip: true },
    render: (row) => row.name ?? row.id.slice(0, 8) + "…",
  },
  {
    title: "State",
    key: "state_type",
    width: 130,
    render: (row) =>
      h(
        NTag,
        { type: runStateType(row.state_type), size: "small", round: true },
        { default: () => row.state_name ?? row.state_type ?? "—" }
      ),
  },
  {
    title: "Start Time",
    key: "start_time",
    width: 180,
    render: (row) => (row.start_time ? new Date(row.start_time).toLocaleString() : "—"),
  },
  {
    title: "Duration",
    key: "total_run_time",
    width: 100,
    render: (row) => formatDuration(row.total_run_time),
  },
]);

function runRowProps(row: ScheduleRun) {
  return {
    style: "cursor: pointer",
    onClick: () => {
      selectedRunId.value = selectedRunId.value === row.id ? null : row.id;
    },
  };
}
</script>
