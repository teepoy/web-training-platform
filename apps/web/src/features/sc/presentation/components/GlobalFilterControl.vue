<script setup lang="ts">
import { computed, onScopeDispose, ref, watch } from "vue";
import { useI18n } from "vue-i18n";
import { NButton, NSpin, NTag, NText, useMessage } from "naive-ui";
import { buildScGlobalDataFilters } from "@/features/sc/application/workbenchDataFilter";
import { useScReclassifyStore } from "@/features/sc/application/reclassifyStore";
import {
  cloneScGlobalFilter,
  emptyScGlobalFilter,
  scGlobalFilterConditionCount,
  scGlobalFilterHasConditions,
  type ScGlobalFilter,
} from "@/features/sc/domain/globalFilter";
import type { ScDataColumn } from "@/features/sc/domain/workbenchDataSource";
import { useScDataWorkbench } from "@/features/sc/presentation/composables/useScDataWorkbench";
import { useScFilterLookupController } from "@/features/sc/presentation/composables/useScFilterLookupController";
import GlobalFilterModal from "./GlobalFilterModal.vue";
import { formatNumber } from "@/shared/i18n/format";

const props = defineProps<{
  datasetId: string;
}>();

const message = useMessage();
const { t } = useI18n();
const reclassifyStore = useScReclassifyStore();
const workbench = useScDataWorkbench();
const modalVisible = ref(false);
const columns = ref<ScDataColumn[]>([]);
const filterLookups = useScFilterLookupController();
const { distinctValues, numericRanges, numericRangeLoading, numericRangeErrors } = filterLookups;
const totalCount = ref<number | null>(null);
const filteredCount = ref<number | null>(null);
const statsLoading = ref(false);
const statsError = ref<string | null>(null);
let statsVersion = 0;
let columnsVersion = 0;
let unsubscribeInvalidations: (() => void) | null = null;

const globalFilter = computed<ScGlobalFilter>({
  get: () =>
    cloneScGlobalFilter(
      reclassifyStore.globalFiltersByWorkspace?.[props.datasetId] ?? emptyScGlobalFilter(),
    ),
  set: (filter) => reclassifyStore.setGlobalFilter(props.datasetId, filter),
});
const conditionCount = computed(() => scGlobalFilterConditionCount(globalFilter.value));
const filteredPercent = computed<number | null>(() => {
  if (totalCount.value === null || filteredCount.value === null) return null;
  if (totalCount.value === 0) return 0;
  return Math.round((filteredCount.value / totalCount.value) * 1000) / 10;
});
const excludedCount = computed<number | null>(() => {
  if (totalCount.value === null || filteredCount.value === null) return null;
  return Math.max(0, totalCount.value - filteredCount.value);
});

function sumGroups(groups: Record<string, number>): number {
  return Object.values(groups).reduce((sum, count) => sum + count, 0);
}

async function refreshStatistics(): Promise<void> {
  const source = workbench.dataSource.value;
  const version = ++statsVersion;
  if (!source) {
    totalCount.value = null;
    filteredCount.value = null;
    statsLoading.value = false;
    return;
  }
  statsLoading.value = true;
  statsError.value = null;
  try {
    const filterSnapshot = cloneScGlobalFilter(globalFilter.value);
    const hasFilter = scGlobalFilterHasConditions(filterSnapshot);
    const totalGroupsPromise = source.loadAggregates({ field: "class_number", filters: [] });
    const filteredGroupsPromise = hasFilter
      ? source.loadAggregates({
          field: "class_number",
          filters: buildScGlobalDataFilters(filterSnapshot),
        })
      : totalGroupsPromise;
    const [totalGroups, filteredGroups] = await Promise.all([
      totalGroupsPromise,
      filteredGroupsPromise,
    ]);
    if (version !== statsVersion || source !== workbench.dataSource.value) return;
    totalCount.value = sumGroups(totalGroups);
    filteredCount.value = sumGroups(filteredGroups);
  } catch (error) {
    if (version !== statsVersion || source !== workbench.dataSource.value) return;
    totalCount.value = null;
    filteredCount.value = null;
    statsError.value = error instanceof Error ? error.message : String(error);
  } finally {
    if (version === statsVersion) statsLoading.value = false;
  }
}

async function loadColumns(): Promise<void> {
  const source = workbench.dataSource.value;
  const version = ++columnsVersion;
  if (!source) {
    columns.value = [];
    return;
  }
  try {
    const nextColumns = await source.loadColumns();
    if (version === columnsVersion && source === workbench.dataSource.value) {
      columns.value = nextColumns;
    }
  } catch (error) {
    if (version === columnsVersion) {
      columns.value = [];
      message.error(error instanceof Error ? error.message : t("sc.filterColumnsFailed"));
    }
  }
}

async function searchFilterOptions(payload: { field: string; search: string }): Promise<void> {
  const source = workbench.dataSource.value;
  if (!source) return;
  await filterLookups.searchDistinct(
    payload,
    () =>
      source.loadDistinctValues({
        field: payload.field,
        search: payload.search,
        limit: 500,
        filter: {},
        sort: null,
        filters: [],
      }),
    (error) => message.error(error instanceof Error ? error.message : t("sc.filterOptionsFailed")),
  );
}

async function requestFilterRange(payload: { field: string; itemId?: string }): Promise<void> {
  const source = workbench.dataSource.value;
  if (!source) return;
  await filterLookups.requestRange(payload, () =>
    source.loadNumericRange({
      field: payload.field,
      filters: buildScGlobalDataFilters(globalFilter.value, { omitItemId: payload.itemId }),
    }),
  );
}

function updateGlobalFilter(filter: ScGlobalFilter): void {
  globalFilter.value = filter;
}

function clearGlobalFilter(): void {
  reclassifyStore.clearGlobalFilter(props.datasetId);
}

watch(
  () => props.datasetId,
  async (datasetId) => {
    filterLookups.reset();
    await workbench.connect({ kind: "reclassify", datasetId });
  },
  { immediate: true },
);

watch(
  workbench.dataSource,
  (source) => {
    unsubscribeInvalidations?.();
    unsubscribeInvalidations =
      source?.subscribeInvalidations(() => void refreshStatistics()) ?? null;
    void loadColumns();
  },
  { immediate: true },
);

watch([workbench.dataSource, globalFilter], () => void refreshStatistics(), {
  deep: true,
  immediate: true,
});

onScopeDispose(() => {
  statsVersion += 1;
  columnsVersion += 1;
  unsubscribeInvalidations?.();
});
</script>

<template>
  <section class="sc-dataset-global-filter" data-testid="sc-dataset-global-filter">
    <div class="sc-dataset-global-filter__actions">
      <NButton
        data-testid="sc-dataset-global-filter-trigger"
        size="small"
        :type="conditionCount > 0 ? 'primary' : 'default'"
        @click="modalVisible = true"
      >
        {{
          conditionCount > 0
            ? t("sc.globalFilterCount", { count: conditionCount })
            : t("sc.globalFilter")
        }}
      </NButton>
      <NButton
        v-if="conditionCount > 0"
        data-testid="sc-dataset-global-filter-clear"
        size="small"
        quaternary
        @click="clearGlobalFilter"
      >
        {{ t("common.clear") }}
      </NButton>
    </div>

    <div class="sc-dataset-global-filter__stats" data-testid="sc-dataset-filter-stats">
      <NSpin v-if="statsLoading" size="small" />
      <NText v-else-if="statsError" type="error">
        {{ t("sc.filterStatsUnavailable", { error: statsError }) }}
      </NText>
      <template v-else-if="totalCount !== null && filteredCount !== null">
        <NText>
          {{
            t("sc.sampleRatio", {
              filtered: formatNumber(filteredCount),
              total: formatNumber(totalCount),
            })
          }}
        </NText>
        <NTag v-if="conditionCount > 0 && filteredPercent !== null" size="small" round type="info">
          {{ filteredPercent }}%
        </NTag>
        <NText v-if="conditionCount > 0 && excludedCount !== null" depth="3">
          {{ t("sc.excluded", { count: formatNumber(excludedCount) }) }}
        </NText>
        <NText v-else depth="3">{{ t("sc.noFilter") }}</NText>
      </template>
    </div>

    <GlobalFilterModal
      v-model:show="modalVisible"
      :filter="globalFilter"
      :columns="columns"
      :distinct-values="distinctValues"
      :numeric-ranges="numericRanges"
      :numeric-range-loading="numericRangeLoading"
      :numeric-range-errors="numericRangeErrors"
      :reset-key="datasetId"
      show-reclassify-columns
      @update:filter="updateGlobalFilter"
      @search-options="searchFilterOptions"
      @request-range="requestFilterRange"
    />
  </section>
</template>

<style scoped>
.sc-dataset-global-filter {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  margin-bottom: 16px;
  padding: 10px 12px;
  border: 1px solid var(--n-border-color, #e0e0e6);
  border-radius: 6px;
}

.sc-dataset-global-filter__actions,
.sc-dataset-global-filter__stats {
  display: flex;
  align-items: center;
  gap: 8px;
}

@media (max-width: 720px) {
  .sc-dataset-global-filter {
    align-items: flex-start;
    flex-direction: column;
  }
}
</style>
