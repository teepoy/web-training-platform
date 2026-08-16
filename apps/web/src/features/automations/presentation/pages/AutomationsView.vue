<template>
  <DatasetPageShell
    :is-loading="runsQuery.isLoading.value"
    :has-org="!!orgStore.currentOrgId"
    :error="runsQuery.error.value as Error | null"
  >
    <div class="automations-view" data-testid="automations-page">
      <div class="automation-toolbar">
        <DatasetToolbar title="Automations" />
        <NButton size="small" :loading="runsQuery.isFetching.value" @click="runsQuery.refetch()">
          Refresh
        </NButton>
      </div>

      <NAlert type="info" :show-icon="false">
        Monitor data updates and predictions across your Collections. To change what runs or when it
        runs, open that Collection. Recovery for data updates also starts there so changed Source
        records are never mistaken for failed work. Automations cannot be created without a target.
      </NAlert>

      <div class="automation-filters">
        <NInput
          v-model:value="search"
          clearable
          size="small"
          placeholder="Search Collections or run IDs"
          aria-label="Search automations"
        />
        <NSelect
          v-model:value="statusFilter"
          clearable
          size="small"
          placeholder="All statuses"
          aria-label="Automation status"
          :options="statusOptions"
        />
        <NSelect
          v-model:value="kindFilter"
          clearable
          size="small"
          placeholder="All work types"
          aria-label="Automation work type"
          :options="kindOptions"
        />
      </div>

      <NDataTable
        remote
        size="small"
        :bordered="false"
        :columns="columns"
        :data="runs"
        :pagination="tablePagination"
        :row-key="(row: AutomationRunOverview) => `${row.run_source}:${row.id}`"
        :row-props="rowProps"
        :scroll-x="980"
      >
        <template #empty>
          <NEmpty description="No automation activity matches these filters" />
        </template>
      </NDataTable>
    </div>
  </DatasetPageShell>
</template>

<script setup lang="ts">
import { computed, h, reactive, ref, watch } from "vue";
import { useMutation, useQuery, useQueryClient } from "@tanstack/vue-query";
import { refDebounced } from "@vueuse/core";
import { useRouter } from "vue-router";
import {
  NAlert,
  NButton,
  NDataTable,
  NEmpty,
  NInput,
  NSelect,
  NSpace,
  NTag,
  NText,
  useMessage,
  type DataTableColumns,
  type PaginationProps,
} from "naive-ui";
import { useOrgStore } from "@/features/auth/application/org";
import {
  listAutomationRuns,
  retryAutomationRun,
  type AutomationRecipeKind,
  type AutomationRunOverview,
} from "@/features/automations/api/automationOverview";
import { orgScopedQueryKey, toUserMessage } from "@/shared/api";
import { DatasetPageShell, DatasetToolbar } from "@/shared";

const router = useRouter();
const queryClient = useQueryClient();
const message = useMessage();
const orgStore = useOrgStore();
const search = ref("");
const debouncedSearch = refDebounced(search, 250);
const statusFilter = ref<string | null>(null);
const kindFilter = ref<AutomationRecipeKind | null>(null);
const pagination = reactive<PaginationProps>({
  page: 1,
  pageSize: 20,
  itemCount: 0,
  showSizePicker: true,
  pageSizes: [10, 20, 50, 100],
  onUpdatePage: (page: number) => {
    pagination.page = page;
  },
  onUpdatePageSize: (pageSize: number) => {
    pagination.pageSize = pageSize;
    pagination.page = 1;
  },
});

const statusOptions = [
  { label: "Needs attention", value: "needs_attention" },
  { label: "Waiting", value: "pending" },
  { label: "Running", value: "running" },
  { label: "Completed", value: "completed" },
  { label: "Failed", value: "failed" },
  { label: "Partly completed", value: "partial" },
];
const kindOptions: Array<{ label: string; value: AutomationRecipeKind }> = [
  { label: "Data updates", value: "discovery" },
  { label: "Historical imports", value: "backfill" },
  { label: "Retries", value: "retry" },
  { label: "Predictions", value: "prediction" },
];

const filters = computed(() => ({
  offset: ((pagination.page ?? 1) - 1) * (pagination.pageSize ?? 20),
  limit: pagination.pageSize ?? 20,
  status: statusFilter.value ?? undefined,
  kind: kindFilter.value ?? undefined,
  q: debouncedSearch.value.trim() || undefined,
}));
const overviewQueryKey = computed(() =>
  orgScopedQueryKey(orgStore.currentOrgId, ["automations", filters.value]),
);
const runsQuery = useQuery({
  queryKey: overviewQueryKey,
  queryFn: () => listAutomationRuns(filters.value),
  enabled: computed(() => !!orgStore.currentOrgId),
  refetchInterval: 10_000,
});
const runs = computed(() => runsQuery.data.value?.items ?? []);
const tablePagination = computed(() =>
  (pagination.itemCount ?? 0) > (pagination.pageSize ?? 20) ? pagination : false,
);

watch(
  () => runsQuery.data.value?.total ?? 0,
  (total) => {
    pagination.itemCount = total;
  },
  { immediate: true },
);
watch([debouncedSearch, statusFilter, kindFilter], () => {
  pagination.page = 1;
});

const retryMutation = useMutation({
  mutationFn: retryAutomationRun,
  onSuccess: async () => {
    message.success("Retry started for the unfinished work");
    await queryClient.invalidateQueries({
      queryKey: orgScopedQueryKey(orgStore.currentOrgId, ["automations"]),
    });
  },
  onError: (error) => message.error(toUserMessage(error, "Retry could not be started")),
});

const recipeLabels: Record<AutomationRecipeKind, string> = {
  discovery: "Data update",
  backfill: "Historical import",
  retry: "Retry",
  prediction: "Prediction",
};

function recipeLabel(value: string): string {
  if (
    value === "discovery" ||
    value === "backfill" ||
    value === "retry" ||
    value === "prediction"
  ) {
    return recipeLabels[value];
  }
  return value;
}
const statusLabels: Record<string, string> = {
  pending: "Waiting",
  running: "Running",
  completed: "Completed",
  failed: "Failed",
  partial: "Partly completed",
  needs_attention: "Needs attention",
};

function statusType(status: string): "default" | "info" | "success" | "warning" | "error" {
  if (status === "completed") return "success";
  if (status === "running") return "info";
  if (status === "failed") return "error";
  if (status === "partial" || status === "needs_attention") return "warning";
  return "default";
}

function formatDate(value: string | null): string {
  if (!value) return "—";
  return new Intl.DateTimeFormat(undefined, {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(new Date(value));
}

function openTarget(row: AutomationRunOverview): void {
  void router.push(`/dataset-collections/${row.target_id}`);
}

function rowProps(row: AutomationRunOverview): Record<string, unknown> {
  return {
    style: "cursor: pointer",
    onClick: (event: MouseEvent) => {
      if (event.target instanceof Element && event.target.closest("button, a")) return;
      openTarget(row);
    },
  };
}

const columns: DataTableColumns<AutomationRunOverview> = [
  {
    title: "Collection",
    key: "target_label",
    minWidth: 220,
    render: (row) =>
      h(NSpace, { vertical: true, size: 0 }, () => [
        h(NText, { strong: true }, () => row.target_label),
        h(NText, { depth: 3, style: "font-size: 12px" }, () => row.target_id),
      ]),
  },
  {
    title: "Work",
    key: "recipe_kind",
    width: 150,
    render: (row) => recipeLabel(row.recipe_kind),
  },
  {
    title: "Status",
    key: "status",
    minWidth: 220,
    render: (row) =>
      h(NSpace, { vertical: true, size: 2 }, () => [
        h(NTag, { size: "small", type: statusType(row.status) }, () =>
          row.needs_attention ? "Needs attention" : (statusLabels[row.status] ?? row.status),
        ),
        ...(row.needs_attention && row.detail
          ? [h(NText, { depth: 3, style: "font-size: 12px" }, () => row.detail)]
          : []),
      ]),
  },
  { title: "Started", key: "started_at", width: 180, render: (row) => formatDate(row.started_at) },
  {
    title: "Finished",
    key: "completed_at",
    width: 180,
    render: (row) => formatDate(row.completed_at),
  },
  {
    title: "Recovery",
    key: "actions",
    width: 130,
    render: (row) =>
      row.retry_supported
        ? h(
            NButton,
            {
              size: "small",
              type: "warning",
              loading: retryMutation.isPending.value,
              onClick: () => retryMutation.mutate(row),
            },
            () => "Retry",
          )
        : h(
            NButton,
            { size: "small", text: true, onClick: () => openTarget(row) },
            () => "Open Collection",
          ),
  },
];
</script>

<style scoped>
.automations-view {
  display: flex;
  flex-direction: column;
  gap: 16px;
  min-height: 0;
}

.automation-toolbar {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
}

.automation-filters {
  display: grid;
  grid-template-columns: minmax(240px, 1fr) 190px 210px;
  gap: 12px;
}

@media (max-width: 767px) {
  .automation-filters {
    grid-template-columns: 1fr;
  }
}
</style>
