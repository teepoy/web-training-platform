<template>
  <n-space vertical size="large">
    <n-page-header
      :title="schedule?.name ?? t('schedules.detail')"
      @back="router.push('/schedules')"
    >
      <template #subtitle>
        <n-tag :type="schedule?.is_schedule_active ? 'success' : 'warning'" size="small" round>
          {{ schedule?.is_schedule_active ? t("status.active") : t("status.paused") }}
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
            {{ schedule.is_schedule_active ? t("common.pause") : t("common.resume") }}
          </n-button>
          <n-button size="small" @click="showEditModal = true">{{ t("common.edit") }}</n-button>
          <n-button
            size="small"
            type="primary"
            :loading="triggerMutation.isPending.value"
            @click="onTrigger"
          >
            {{ t("schedules.triggerNow") }}
          </n-button>
          <n-button
            size="small"
            type="error"
            :loading="deleteMutation.isPending.value"
            @click="onDelete"
          >
            {{ t("common.delete") }}
          </n-button>
          <n-button
            v-if="schedule?.prefect_deployment_url"
            size="small"
            tag="a"
            :href="schedule.prefect_deployment_url"
            target="_blank"
          >
            {{ t("schedules.viewInPrefect") }}
          </n-button>
        </n-space>
      </template>
    </n-page-header>

    <n-spin :show="scheduleLoading">
      <n-card v-if="schedule">
        <n-descriptions label-placement="left" :column="2" bordered>
          <n-descriptions-item :label="t('schedules.flowName')">{{
            schedule.flow_name
          }}</n-descriptions-item>
          <n-descriptions-item :label="t('schedules.cron')">{{
            schedule.cron ?? "—"
          }}</n-descriptions-item>
          <n-descriptions-item :label="t('schedules.timezone')">{{
            schedule.timezone
          }}</n-descriptions-item>
          <n-descriptions-item :label="t('common.description')">{{
            schedule.description || "—"
          }}</n-descriptions-item>
          <n-descriptions-item :label="t('schedules.deploymentId')">
            {{ schedule.prefect_deployment_id || "—" }}
          </n-descriptions-item>
          <n-descriptions-item :label="t('settings.created')">
            {{ schedule.created ? formatDateTime(schedule.created) : "—" }}
          </n-descriptions-item>
          <n-descriptions-item :label="t('tasks.updated')">
            {{ schedule.updated ? formatDateTime(schedule.updated) : "—" }}
          </n-descriptions-item>
        </n-descriptions>
      </n-card>
    </n-spin>

    <n-card :title="t('schedules.runHistory')">
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
      <div v-if="selectedRunId" style="margin-top: 16px">
        <RunLogViewer :runId="selectedRunId" />
      </div>
    </n-card>
  </n-space>

  <n-modal
    v-model:show="showEditModal"
    preset="dialog"
    :title="t('schedules.edit')"
    :positive-text="t('common.save')"
    :negative-text="t('common.cancel')"
    :loading="updateMutation.isPending.value"
    @positive-click="onEditSubmit"
    @negative-click="showEditModal = false"
  >
    <n-form ref="editFormRef" :model="editForm" label-placement="left" label-width="auto">
      <n-form-item :label="t('schedules.cron')">
        <n-input v-model:value="editForm.cron" placeholder="*/5 * * * *" />
      </n-form-item>
      <n-form-item :label="t('schedules.timezone')">
        <n-input
          v-model:value="editForm.timezone"
          :placeholder="t('schedules.timezonePlaceholder')"
        />
      </n-form-item>
      <n-form-item :label="t('schedules.parameters')">
        <n-input
          v-model:value="editForm.parameters"
          type="textarea"
          placeholder="{}"
          :autosize="{ minRows: 3, maxRows: 6 }"
        />
      </n-form-item>
      <n-form-item :label="t('common.description')">
        <n-input
          v-model:value="editForm.description"
          :placeholder="t('schedules.optionalDescription')"
        />
      </n-form-item>
    </n-form>
  </n-modal>
</template>

<script setup lang="ts">
import { ref, computed, h, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import { useI18n } from "vue-i18n";
import { useQueryClient } from "@tanstack/vue-query";
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
import {
  useGetScheduleApiV1SchedulesScheduleIdGet,
  useUpdateScheduleApiV1SchedulesScheduleIdPatch,
  useDeleteScheduleApiV1SchedulesScheduleIdDelete,
  useTriggerRunApiV1SchedulesScheduleIdRunPost,
  usePauseScheduleApiV1SchedulesScheduleIdPausePost,
  useResumeScheduleApiV1SchedulesScheduleIdResumePost,
  useListRunsApiV1SchedulesScheduleIdRunsGet,
} from "@/generated/orval/endpoints/api";
import { orgScopedQueryKey, toUserMessage } from "@/shared/api";
import { useOrgStore } from "@/features/auth/application/org";
import type {
  RunResponse as ScheduleRun,
  ScheduleResponse,
  UpdateScheduleRequest,
} from "@/generated/orval/models";
import RunLogViewer from "@/shared/components/run-log-viewer/RunLogViewer.vue";
import { formatDateTime, formatNumber } from "@/shared/i18n/format";

const route = useRoute();
const { t } = useI18n();
const router = useRouter();
const message = useMessage();
const qc = useQueryClient();
const orgStore = useOrgStore();

const id = computed(() => route.params.id as string);
const scheduleQueryKey = computed(() =>
  orgScopedQueryKey(orgStore.currentOrgId, ["schedule", id.value]),
);
const scheduleRunsQueryKey = computed(() =>
  orgScopedQueryKey(orgStore.currentOrgId, ["schedule-runs", id.value]),
);

// ---------------------------------------------------------------------------
// Queries
// ---------------------------------------------------------------------------

const { data: schedule, isLoading: scheduleLoading } = useGetScheduleApiV1SchedulesScheduleIdGet(
  id,
  {
    query: {
      queryKey: scheduleQueryKey,
      enabled: computed(() => !!orgStore.currentOrgId && !!id.value),
    },
  },
);

const { data: runs, isLoading: runsLoading } = useListRunsApiV1SchedulesScheduleIdRunsGet(
  id,
  undefined,
  {
    query: {
      queryKey: scheduleRunsQueryKey,
      enabled: computed(() => !!orgStore.currentOrgId && !!id.value),
    },
  },
);

// ---------------------------------------------------------------------------
// Mutations
// ---------------------------------------------------------------------------

const triggerMutation = useTriggerRunApiV1SchedulesScheduleIdRunPost({
  mutation: {
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: scheduleRunsQueryKey.value });
      message.success(t("schedules.runTriggered"));
    },
    onError: (error) => {
      message.error(toUserMessage(error, t("schedules.triggerFailed")));
    },
  },
});

const pauseMutation = usePauseScheduleApiV1SchedulesScheduleIdPausePost({
  mutation: {
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: scheduleQueryKey.value });
      message.success(t("schedules.paused"));
    },
    onError: (error) => {
      message.error(toUserMessage(error, t("schedules.pauseFailed")));
    },
  },
});

const resumeMutation = useResumeScheduleApiV1SchedulesScheduleIdResumePost({
  mutation: {
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: scheduleQueryKey.value });
      message.success(t("schedules.resumed"));
    },
    onError: (error) => {
      message.error(toUserMessage(error, t("schedules.resumeFailed")));
    },
  },
});

const deleteMutation = useDeleteScheduleApiV1SchedulesScheduleIdDelete({
  mutation: {
    onSuccess: () => {
      message.success(t("schedules.deleted"));
      router.push("/schedules");
    },
    onError: (error) => {
      message.error(toUserMessage(error, t("schedules.deleteFailed")));
    },
  },
});

// ---------------------------------------------------------------------------
// Edit modal
// ---------------------------------------------------------------------------

const showEditModal = ref(false);
const editFormRef = ref<FormInst | null>(null);
const editForm = ref({ cron: "", timezone: "UTC", parameters: "{}", description: "" });

watch(
  schedule,
  (s) => {
    if (s) {
      editForm.value = {
        cron: s.cron ?? "",
        timezone: s.timezone,
        parameters: JSON.stringify(s.parameters ?? {}, null, 2),
        description: s.description ?? "",
      };
    }
  },
  { immediate: true },
);

const updateMutation = useUpdateScheduleApiV1SchedulesScheduleIdPatch({
  mutation: {
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: scheduleQueryKey.value });
      message.success(t("schedules.updated"));
      showEditModal.value = false;
    },
    onError: (error) => {
      message.error(toUserMessage(error, t("schedules.updateFailed")));
    },
  },
});

function onEditSubmit() {
  let parsedParams: Record<string, unknown>;
  try {
    parsedParams = JSON.parse(editForm.value.parameters);
    if (typeof parsedParams !== "object" || Array.isArray(parsedParams) || parsedParams === null) {
      message.error(t("schedules.parametersObject"));
      return false;
    }
  } catch {
    message.error(t("schedules.parametersJson"));
    return false;
  }

  const body: UpdateScheduleRequest = {};
  if (editForm.value.cron !== (schedule.value?.cron ?? "")) {
    body.cron = editForm.value.cron;
  }
  if (editForm.value.timezone !== schedule.value?.timezone) {
    body.timezone = editForm.value.timezone;
  }
  if (JSON.stringify(parsedParams) !== JSON.stringify(schedule.value?.parameters ?? {})) {
    body.parameters = parsedParams;
  }
  if (editForm.value.description !== (schedule.value?.description ?? "")) {
    body.description = editForm.value.description;
  }

  updateMutation.mutate({ scheduleId: id.value, data: body });
  return false;
}

// ---------------------------------------------------------------------------
// Handlers
// ---------------------------------------------------------------------------

function onTrigger() {
  triggerMutation.mutate({ scheduleId: id.value });
}

function onTogglePause() {
  if (schedule.value?.is_schedule_active) {
    pauseMutation.mutate({ scheduleId: id.value });
  } else {
    resumeMutation.mutate({ scheduleId: id.value });
  }
}

function onDelete() {
  deleteMutation.mutate({ scheduleId: id.value });
}

// ---------------------------------------------------------------------------
// Run state helpers
// ---------------------------------------------------------------------------

type TagType = "default" | "info" | "success" | "error" | "warning";

function runStateType(stateType: string | null | undefined): TagType {
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

function formatDuration(totalRunTime: number | null | undefined): string {
  if (totalRunTime === null || totalRunTime === undefined) return "—";
  if (totalRunTime > 60) return t("schedules.overOneMinute");
  return t("schedules.seconds", {
    value: formatNumber(totalRunTime, { minimumFractionDigits: 1, maximumFractionDigits: 1 }),
  });
}

// ---------------------------------------------------------------------------
// Table
// ---------------------------------------------------------------------------

const selectedRunId = ref<string | null>(null);

const runColumns = computed<DataTableColumns<ScheduleRun>>(() => [
  {
    title: t("schedules.runName"),
    key: "name",
    ellipsis: { tooltip: true },
    render: (row) => row.name ?? row.id.slice(0, 8) + "…",
  },
  {
    title: t("schedules.state"),
    key: "state_type",
    width: 130,
    render: (row) =>
      h(
        NTag,
        { type: runStateType(row.state_type), size: "small", round: true },
        { default: () => row.state_name ?? row.state_type ?? "—" },
      ),
  },
  {
    title: t("schedules.startTime"),
    key: "start_time",
    width: 180,
    render: (row) => (row.start_time ? formatDateTime(row.start_time) : "—"),
  },
  {
    title: t("schedules.duration"),
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
