<template>
  <n-space vertical size="large">
    <template v-if="!orgStore.currentOrgId">
      <div style="padding: 48px; text-align: center">
        <n-empty :description="t('user.noOrganization')" />
      </div>
    </template>
    <template v-else>
      <n-page-header :title="t('schedules.title')">
        <template #extra>
          <n-button style="margin-right: 8px" @click="openTaskExplorer">
            {{ t("schedules.openTasks") }}
          </n-button>
          <n-button type="primary" @click="openCreateModal">{{ t("schedules.create") }}</n-button>
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
        :title="t('schedules.create')"
        :positive-text="t('common.create')"
        :negative-text="t('common.cancel')"
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
          <n-form-item :label="t('schedules.name')" path="name">
            <n-input v-model:value="formModel.name" :placeholder="t('schedules.namePlaceholder')" />
          </n-form-item>
          <n-form-item :label="t('schedules.flow')" path="flow_name">
            <n-select
              v-model:value="formModel.flow_name"
              :options="flowOptions"
              :placeholder="t('schedules.selectFlow')"
            />
          </n-form-item>
          <n-form-item :label="t('schedules.cron')" path="cron">
            <n-input v-model:value="formModel.cron" placeholder="*/5 * * * *" />
          </n-form-item>
          <n-form-item :label="t('schedules.timezone')" path="timezone">
            <n-input
              v-model:value="formModel.timezone"
              :placeholder="t('schedules.timezonePlaceholder')"
            />
          </n-form-item>
          <n-form-item :label="t('schedules.parameters')" path="parameters">
            <n-input
              v-model:value="formModel.parameters"
              type="textarea"
              placeholder="{}"
              :autosize="{ minRows: 3, maxRows: 6 }"
            />
          </n-form-item>
          <n-form-item :label="t('common.description')" path="description">
            <n-input
              v-model:value="formModel.description"
              :placeholder="t('schedules.optionalDescription')"
            />
          </n-form-item>
        </n-form>
      </n-modal>
    </template>
  </n-space>
</template>

<script setup lang="ts">
import { ref, computed, h } from "vue";
import { useRoute, useRouter } from "vue-router";
import { useQueryClient } from "@tanstack/vue-query";
import type { DataTableColumns, FormInst, FormRules } from "naive-ui";
import { useMessage, NTag, NButton, NPopconfirm, NSpace } from "naive-ui";
import { useI18n } from "vue-i18n";
import {
  useListSchedulesApiV1SchedulesGet,
  useListScheduleCapabilitiesApiV1SchedulesCapabilitiesGet,
  useCreateScheduleApiV1SchedulesPost,
  useDeleteScheduleApiV1SchedulesScheduleIdDelete,
  usePauseScheduleApiV1SchedulesScheduleIdPausePost,
  useResumeScheduleApiV1SchedulesScheduleIdResumePost,
} from "@/generated/orval/endpoints/api";
import { orgScopedQueryKey, toUserMessage } from "@/shared/api";
import { useOrgStore } from "@/features/auth/application/org";
import type { ScheduleResponse as Schedule } from "@/generated/orval/models";

const router = useRouter();
const { t } = useI18n();
const route = useRoute();
const message = useMessage();
const qc = useQueryClient();
const orgStore = useOrgStore();
const schedulesQueryKey = computed(() => orgScopedQueryKey(orgStore.currentOrgId, ["schedules"]));
const scheduleCapabilitiesQueryKey = computed(() =>
  orgScopedQueryKey(orgStore.currentOrgId, ["schedule-capabilities"]),
);

// ---------------------------------------------------------------------------
// Query
// ---------------------------------------------------------------------------

const { data: schedules, isLoading } = useListSchedulesApiV1SchedulesGet(
  { offset: 0, limit: 200 },
  {
    query: {
      select: (response) => response.items,
      queryKey: schedulesQueryKey,
      enabled: computed(() => !!orgStore.currentOrgId),
    },
  },
);

const { data: scheduleCapabilities } = useListScheduleCapabilitiesApiV1SchedulesCapabilitiesGet({
  query: {
    queryKey: scheduleCapabilitiesQueryKey,
    enabled: computed(() => !!orgStore.currentOrgId),
  },
});

// ---------------------------------------------------------------------------
// Mutations
// ---------------------------------------------------------------------------

const createMutation = useCreateScheduleApiV1SchedulesPost({
  mutation: {
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: schedulesQueryKey.value });
      message.success(t("schedules.created"));
      showModal.value = false;
      resetForm();
    },
    onError: (error) => message.error(toUserMessage(error, t("schedules.createFailed"))),
  },
});

const deleteMutation = useDeleteScheduleApiV1SchedulesScheduleIdDelete({
  mutation: {
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: schedulesQueryKey.value });
      message.success(t("schedules.deleted"));
    },
    onError: (error) => message.error(toUserMessage(error, t("schedules.deleteFailed"))),
  },
});

const pauseMutation = usePauseScheduleApiV1SchedulesScheduleIdPausePost({
  mutation: {
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: schedulesQueryKey.value });
      message.success(t("schedules.paused"));
    },
    onError: (error) => message.error(toUserMessage(error, t("schedules.pauseFailed"))),
  },
});

const resumeMutation = useResumeScheduleApiV1SchedulesScheduleIdResumePost({
  mutation: {
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: schedulesQueryKey.value });
      message.success(t("schedules.resumed"));
    },
    onError: (error) => message.error(toUserMessage(error, t("schedules.resumeFailed"))),
  },
});

function openTaskExplorer() {
  router.push({ path: "/tasks", query: { from: route.fullPath } });
}

// ---------------------------------------------------------------------------
// Table columns
// ---------------------------------------------------------------------------

const columns = computed<DataTableColumns<Schedule>>(() => [
  {
    title: t("schedules.name"),
    key: "name",
    ellipsis: { tooltip: true },
  },
  {
    title: t("schedules.flow"),
    key: "flow_name",
    width: 160,
  },
  {
    title: t("schedules.cron"),
    key: "cron",
    width: 160,
    render: (row) => row.cron ?? "—",
  },
  {
    title: t("schedules.timezone"),
    key: "timezone",
    width: 150,
  },
  {
    title: t("jobs.status"),
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
        { default: () => (row.is_schedule_active ? t("status.active") : t("status.paused")) },
      ),
  },
  {
    title: t("common.actions"),
    key: "actions",
    width: 240,
    render: (row) =>
      h(
        NSpace,
        { size: "small" },
        {
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
              { default: () => t("jobs.view") },
            ),
            h(
              NButton,
              {
                size: "small",
                type: row.is_schedule_active ? "warning" : "primary",
                loading: row.is_schedule_active
                  ? pauseMutation.isPending.value
                  : resumeMutation.isPending.value,
                onClick: (e: Event) => {
                  e.stopPropagation();
                  if (row.is_schedule_active) {
                    pauseMutation.mutate({ scheduleId: row.id });
                  } else {
                    resumeMutation.mutate({ scheduleId: row.id });
                  }
                },
              },
              { default: () => (row.is_schedule_active ? t("common.pause") : t("common.resume")) },
            ),
            h(
              NPopconfirm,
              {
                onPositiveClick: (e: MouseEvent) => {
                  e.stopPropagation();
                  deleteMutation.mutate({ scheduleId: row.id });
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
                    { default: () => t("common.delete") },
                  ),
                default: () => t("schedules.confirmDelete"),
              },
            ),
          ],
        },
      ),
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
  timezone: "UTC",
  parameters: "{}",
  description: "",
});

const flowOptions = computed(() =>
  (scheduleCapabilities.value ?? []).map((capability) => ({
    label: capability.flow_name,
    value: capability.flow_name,
  })),
);

const formRules: FormRules = {
  name: [{ required: true, message: t("schedules.nameRequired"), trigger: ["blur", "input"] }],
  flow_name: [
    { required: true, message: t("schedules.flowRequired"), trigger: ["blur", "change"] },
  ],
  cron: [
    { required: true, message: t("schedules.cronRequired"), trigger: ["blur", "input"] },
    {
      validator: (_rule: unknown, value: string) => {
        if (!value) return true;
        const parts = value.trim().split(/\s+/);
        return parts.length === 5 || new Error(t("schedules.cronFields"));
      },
      trigger: ["blur"],
    },
  ],
  timezone: [
    {
      required: true,
      message: t("schedules.timezoneRequired"),
      trigger: ["blur", "input"],
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
      if (
        typeof parsedParams !== "object" ||
        Array.isArray(parsedParams) ||
        parsedParams === null
      ) {
        message.error(t("schedules.parametersObject"));
        return;
      }
    } catch {
      message.error(t("schedules.parametersJson"));
      return;
    }

    createMutation.mutate({
      data: {
        name: formModel.value.name,
        flow_name: formModel.value.flow_name,
        cron: formModel.value.cron,
        timezone: formModel.value.timezone,
        parameters: parsedParams,
        description: formModel.value.description || undefined,
      },
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
    timezone: "UTC",
    parameters: "{}",
    description: "",
  };
  formRef.value?.restoreValidation();
}
</script>
