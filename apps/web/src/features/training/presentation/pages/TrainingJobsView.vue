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
          <n-button type="primary" :disabled="!canTrain" @click="showModal = true">Start New Job</n-button>
        </template>
      </n-page-header>

      <n-spin :show="isLoading">
        <n-data-table
          :columns="columns"
          :data="jobs ?? []"
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
          <n-form-item v-if="!props.datasetId" label="Dataset" path="dataset_id">
            <n-select
              v-model:value="formModel.dataset_id"
              :options="datasetOptions"
              :loading="datasetsLoading"
              placeholder="Select a dataset"
              filterable
            />
          </n-form-item>
          <n-form-item label="Trainer" path="trainer_id">
            <template v-if="props.datasetId && !trainersLoading && trainerOptions.length === 0">
              <n-empty description="No compatible trainer for this dataset" />
            </template>
            <n-select
              v-else
              v-model:value="formModel.trainer_id"
              :options="trainerOptions"
              :loading="trainersLoading"
              placeholder="Select a trainer"
              filterable
            />
          </n-form-item>
        </n-form>
      </n-modal>

      <TaskInsightModal
        v-model:show="insightVisible"
        :task="selectedTask"
        :handoff-enabled="false"
      />
    </template>
  </n-space>
</template>

<script setup lang="ts">
import { ref, computed, h, provide, watch } from "vue";
import type { MaybeRef } from "vue";
import { useRoute, useRouter } from "vue-router";
import { useQuery, useQueryClient } from "@tanstack/vue-query";
import type { DataTableColumns, FormInst, FormRules, SelectOption } from "naive-ui";
import { useMessage, NTag, NButton } from "naive-ui";
import { listDatasets } from "@/shared/api/datasets";
import { useOrgStore } from '@/features/auth/application/org';
import {
  useListJobsApiV1TrainingJobsGet,
  useCreateTrainingJobApiV1TrainingJobsPost,
  useListTrainersRouteApiV1TrainersGet,
} from "@/generated/orval/endpoints/api";
import type { ListJobsApiV1TrainingJobsGetParams } from "@/generated/orval/models/listJobsApiV1TrainingJobsGetParams";
import type { JobStatus, TaskTrackerSummaryResponse as TaskTrackerSummary, TrainingJob } from '@/generated/orval/models';
import type { Trainer } from "@/shared/api/types";
import TaskInsightModal, { TASK_INSIGHT_ORG_ID_KEY } from "@/shared/components/task-insight-modal";

const router = useRouter();
const route = useRoute();
const message = useMessage();
const qc = useQueryClient();
const orgStore = useOrgStore();
const props = defineProps<{ datasetId?: string | null; allowTrain?: boolean; compatibleViewTypes?: string[] | null }>();
const canTrain = computed(() => props.allowTrain !== false);
provide(TASK_INSIGHT_ORG_ID_KEY, computed(() => orgStore.currentOrgId));

const jobsQueryParams = computed(() =>
  props.datasetId ? { dataset_id: props.datasetId } : undefined,
) as MaybeRef<ListJobsApiV1TrainingJobsGetParams>;

const { data: jobs, isLoading } = useListJobsApiV1TrainingJobsGet(jobsQueryParams, {
  query: {
    select: (response) => response.data,
    queryKey: computed(() => ["jobs", orgStore.currentOrgId, props.datasetId]),
    refetchInterval: 5000,
    enabled: computed(() => !!orgStore.currentOrgId),
  },
});

const { data: datasets, isLoading: datasetsLoading } = useQuery({
  queryKey: computed(() => ["datasets", orgStore.currentOrgId]),
  queryFn: listDatasets,
  enabled: computed(() => !!orgStore.currentOrgId),
});

const { data: trainers, isLoading: trainersLoading } = useListTrainersRouteApiV1TrainersGet({
  query: {
    // ast-grep-ignore: forbid-unsafe-type-casts
    select: (response) => response.data as unknown as Trainer[],
    queryKey: computed(() => ["trainers", orgStore.currentOrgId]),
    refetchInterval: 30000,
    enabled: computed(() => !!orgStore.currentOrgId),
  },
});

const datasetOptions = computed<SelectOption[]>(
  () => (datasets.value ?? []).map((d) => ({ label: d.name, value: d.id })),
);

const selectedDataset = computed(() =>
  (datasets.value ?? []).find((d) => d.id === formModel.value.dataset_id),
);

const trainerOptions = computed<SelectOption[]>(
  () =>
    (trainers.value ?? [])
      .filter((t) => t.trainable !== false)
      .filter((t) => {
        if (!props.compatibleViewTypes?.length) return true;
        if (!hasTrainerViewType(t)) return false;
        return props.compatibleViewTypes.includes(t.view_type);
      })
      .map((t) => ({ label: t.name, value: t.id })),
);

function hasTrainerViewType(trainer: Trainer): trainer is Trainer & { view_type: string } {
  return typeof (trainer as { view_type?: unknown }).view_type === "string";
}

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

const columns = computed<DataTableColumns<TrainingJob>>(() => [
  {
    title: "ID",
    key: "id",
    width: 120,
    render: (row) => (row.id ?? '').slice(0, 8) + "…",
  },
  {
    title: "Status",
    key: "status",
    width: 130,
    render: (row) =>
      h(
        NTag,
        { type: statusType(row.status!), size: "small", round: true },
        { default: () => row.status },
      ),
  },
  {
    title: "Public",
    key: "is_public",
    width: 160,
    render: (row) => {
      const nodes = [];
      if (row.is_public) {
        nodes.push(h(NTag, { type: "info", size: "small" }, { default: () => "Public" }));
      }
      if (row.is_public && row.org_id !== orgStore.currentOrgId) {
        nodes.push(
          h("span", { style: "margin-left: 4px; font-size: 12px; color: #aaa" }, `(${row.org_name ?? "Other Org"})`),
        );
      }
      return h("span", {}, nodes);
    },
  },
  {
    title: "Dataset ID",
    key: "dataset_id",
    ellipsis: { tooltip: true },
    render: (row) => row.dataset_id.slice(0, 8) + "…",
  },
  {
    title: "Trainer",
    key: "trainer_id",
    ellipsis: { tooltip: true },
    render: (row) => row.trainer_id,
  },
  {
    title: "Created At",
    key: "created_at",
    width: 180,
    render: (row) => new Date(row.created_at!).toLocaleString(),
  },
  {
    title: "Actions",
    key: "actions",
    width: 150,
    render: (row) => {
      const nodes = [
        h(
          NButton,
          {
            size: "small",
            tertiary: true,
            disabled: !row.id,
            onClick: (e: Event) => {
              e.stopPropagation();
              openInsight(row);
            },
          },
          { default: () => "Task Progress" },
        ),
      ];
      return h("span", { style: "display: inline-flex; gap: 8px" }, nodes);
    },
  },
]);

const showModal = ref(false);
const insightVisible = ref(false);
const selectedTask = ref<TaskTrackerSummary | null>(null);
const formRef = ref<FormInst | null>(null);
const formModel = ref({ dataset_id: null as string | null, trainer_id: null as string | null });

watch(
  () => props.datasetId,
  (val) => { if (val) formModel.value.dataset_id = val; },
  { immediate: true },
);

const formRules: FormRules = {
  dataset_id: [{ required: true, message: "Please select a dataset", trigger: ["blur", "change"] }],
  trainer_id: [{ required: true, message: "Please select a trainer", trigger: ["blur", "change"] }],
};

const createJobMutation = useCreateTrainingJobApiV1TrainingJobsPost({
  mutation: {
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["jobs", orgStore.currentOrgId] });
      message.success("Job started");
      showModal.value = false;
      resetForm();
    },
    onError: (err: Error) => {
      message.error(err.message ?? "Failed to start job");
    },
  },
});

function onSubmit() {
  formRef.value?.validate((errors) => {
    if (errors) return;
    if (!formModel.value.dataset_id || !formModel.value.trainer_id) return;
    createJobMutation.mutate({
      data: {
        dataset_id: formModel.value.dataset_id!,
        trainer_id: formModel.value.trainer_id!,
      },
    });
  });
  return false;
}

function onCancel() {
  resetForm();
}

function resetForm() {
  formModel.value = { dataset_id: null, trainer_id: null };
  formRef.value?.restoreValidation();
}

function openTaskView(row: TrainingJob) {
  if (!row.id) return;
  router.push({
    path: "/tasks",
    query: { kind: "training", task: row.id, from: route.fullPath },
  });
}

function openInsight(row: TrainingJob) {
  if (!row.id) return;
  selectedTask.value = trainingTaskSummary(row);
  insightVisible.value = true;
}

function trainingTaskSummary(row: TrainingJob): TaskTrackerSummary {
  return {
    id: row.id ?? "",
    task_kind: "training",
    execution_kind: "training-default",
    display_name: `Training ${row.trainer_id}`,
    display_status: row.status ?? "queued",
    stage: row.status === "completed" || row.status === "failed" ? "validation_output" : "queue_allocation",
    dataset_id: row.dataset_id,
    model_id: null,
    trainer_id: row.trainer_id,
    created_by: row.created_by,
    created_at: row.created_at ?? "",
    updated_at: row.updated_at ?? row.created_at ?? "",
    prefect_state: null,
    work_pool_name: null,
    work_queue_name: null,
    queue_priority: null,
    queue_priority_label: "none",
    queue_depth_ahead: null,
    capacity_status: "unknown",
    pool_concurrency_limit: null,
    pool_slots_used: null,
  };
}
</script>
