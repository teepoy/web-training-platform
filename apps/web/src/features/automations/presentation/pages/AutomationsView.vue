<template>
  <ResourcePageShell
    :is-loading="runsQuery.isLoading.value"
    :has-org="!!orgStore.currentOrgId"
    :error="runsQuery.error.value as Error | null"
  >
    <div class="automations-view" data-testid="automations-page">
      <div class="automation-toolbar">
        <ResourceToolbar :title="t('automations.title')" />
        <NButton size="small" :loading="runsQuery.isFetching.value" @click="runsQuery.refetch()">
          {{ t("automations.refresh") }}
        </NButton>
      </div>

      <NAlert type="info" :show-icon="false">
        {{ t("automations.description") }}
      </NAlert>

      <div class="automation-filters">
        <NInput
          v-model:value="search"
          clearable
          size="small"
          :placeholder="t('automations.search')"
          :aria-label="t('automations.searchLabel')"
        />
        <NSelect
          v-model:value="statusFilter"
          clearable
          size="small"
          :placeholder="t('automations.allStatuses')"
          :aria-label="t('automations.statusLabel')"
          :options="statusOptions"
        />
        <NSelect
          v-model:value="kindFilter"
          clearable
          size="small"
          :placeholder="t('automations.allWorkTypes')"
          :aria-label="t('automations.workTypeLabel')"
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
          <NEmpty :description="t('automations.empty')" />
        </template>
      </NDataTable>
    </div>
  </ResourcePageShell>
</template>

<script setup lang="ts">
import { computed, h, reactive, ref, watch } from "vue";
import { useMutation, useQuery, useQueryClient } from "@tanstack/vue-query";
import { refDebounced } from "@vueuse/core";
import { useRouter } from "vue-router";
import { useI18n } from "vue-i18n";
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
import { ResourcePageShell, ResourceToolbar } from "@/shared";
import { formatDateTime } from "@/shared/i18n/format";

const router = useRouter();
const { t } = useI18n();
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

const statusOptions = computed(() => [
  { label: t("automations.needsAttention"), value: "needs_attention" },
  { label: t("automations.waiting"), value: "pending" },
  { label: t("status.running"), value: "running" },
  { label: t("status.completed"), value: "completed" },
  { label: t("status.failed"), value: "failed" },
  { label: t("automations.partlyCompleted"), value: "partial" },
]);
const kindOptions = computed<Array<{ label: string; value: AutomationRecipeKind }>>(() => [
  { label: t("automations.dataUpdates"), value: "discovery" },
  { label: t("automations.historicalImports"), value: "backfill" },
  { label: t("automations.retries"), value: "retry" },
  { label: t("automations.predictions"), value: "prediction" },
]);

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
    message.success(t("automations.retryStarted"));
    await queryClient.invalidateQueries({
      queryKey: orgScopedQueryKey(orgStore.currentOrgId, ["automations"]),
    });
  },
  onError: (error) => message.error(toUserMessage(error, t("automations.retryFailed"))),
});

function recipeLabel(value: string): string {
  if (
    value === "discovery" ||
    value === "backfill" ||
    value === "retry" ||
    value === "prediction"
  ) {
    return t(
      `automations.${value === "discovery" ? "dataUpdate" : value === "backfill" ? "historicalImport" : value}`,
    );
  }
  return value;
}
function statusLabel(status: string): string {
  if (status === "pending") return t("automations.waiting");
  if (status === "partial") return t("automations.partlyCompleted");
  if (status === "needs_attention") return t("automations.needsAttention");
  return t(`status.${status}`);
}

function statusType(status: string): "default" | "info" | "success" | "warning" | "error" {
  if (status === "completed") return "success";
  if (status === "running") return "info";
  if (status === "failed") return "error";
  if (status === "partial" || status === "needs_attention") return "warning";
  return "default";
}

function formatDate(value: string | null): string {
  return value ? formatDateTime(value) : "—";
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

const columns = computed<DataTableColumns<AutomationRunOverview>>(() => [
  {
    title: t("resources.collection"),
    key: "target_label",
    minWidth: 220,
    render: (row) =>
      h(NSpace, { vertical: true, size: 0 }, () => [
        h(NText, { strong: true }, () => row.target_label),
        h(NText, { depth: 3, style: "font-size: 12px" }, () => row.target_id),
      ]),
  },
  {
    title: t("automations.work"),
    key: "recipe_kind",
    width: 150,
    render: (row) => recipeLabel(row.recipe_kind),
  },
  {
    title: t("jobs.status"),
    key: "status",
    minWidth: 220,
    render: (row) =>
      h(NSpace, { vertical: true, size: 2 }, () => [
        h(NTag, { size: "small", type: statusType(row.status) }, () =>
          row.needs_attention ? t("automations.needsAttention") : statusLabel(row.status),
        ),
        ...(row.needs_attention && row.detail
          ? [h(NText, { depth: 3, style: "font-size: 12px" }, () => row.detail)]
          : []),
      ]),
  },
  {
    title: t("automations.started"),
    key: "started_at",
    width: 180,
    render: (row) => formatDate(row.started_at),
  },
  {
    title: t("automations.finished"),
    key: "completed_at",
    width: 180,
    render: (row) => formatDate(row.completed_at),
  },
  {
    title: t("automations.recovery"),
    key: "actions",
    width: 130,
    fixed: "right",
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
            () => t("automations.retry"),
          )
        : h(NButton, { size: "small", text: true, onClick: () => openTarget(row) }, () =>
            t("automations.openCollection"),
          ),
  },
]);
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
