<script setup lang="ts">
import { computed, h, reactive, ref } from "vue";
import { useI18n } from "vue-i18n";
import {
  NButton,
  NDataTable,
  NDatePicker,
  NEmpty,
  NInput,
  NList,
  NListItem,
  NModal,
  NSpace,
  NText,
  NTooltip,
  type DataTableColumns,
  type PaginationProps,
} from "naive-ui";
import type { InspectionSummaryItem } from "@/features/sc/domain/models";
import { shouldIgnoreSummaryRowClick } from "./summaryTableInteraction";

const props = defineProps<{
  dateRange: [number, number] | null;
  summariesLoading: boolean;
  summariesError: string | null;
  summariesEmpty: boolean;
  summaries: InspectionSummaryItem[];
  inspectionColumns: DataTableColumns<InspectionSummaryItem>;
  lastOpenedSummaryKey: string | null;
  lastOpenedSummaryLabel: string | null;
  lotIdFilter: string;
  eqpIdFilter: string;
  layerIdFilter: string;
  deviceFilter: string;
  selectedRowKeys: string[];
  importingInspectionKey: string | null;
}>();

const emit = defineEmits<{
  (e: "update:dateRange", value: [number, number] | null): void;
  (e: "update:lotIdFilter", value: string): void;
  (e: "update:eqpIdFilter", value: string): void;
  (e: "update:layerIdFilter", value: string): void;
  (e: "update:deviceFilter", value: string): void;
  (e: "search"): void;
  (e: "rowClick", row: InspectionSummaryItem): void;
  (e: "openDataset", datasetId: string): void;
  (e: "createDataset", row: InspectionSummaryItem): void;
  (e: "buildCollection"): void;
  (e: "update:selectedRowKeys", value: string[]): void;
}>();

const datasetListVisible = ref(false);
const { t } = useI18n();
const datasetList = ref<InspectionSummaryItem["datasets"]>([]);

function showDatasets(row: InspectionSummaryItem): void {
  datasetList.value = row.datasets ?? [];
  datasetListVisible.value = true;
}

function rowKey(row: InspectionSummaryItem): string {
  return `${row.inspection_time}_${row.wafer_key}`;
}

const selectableColumns = computed<DataTableColumns<InspectionSummaryItem>>(() => [
  { type: "selection", multiple: true, width: 42 },
  ...props.inspectionColumns,
  {
    key: "datasets",
    title: t("datasetDetail.dataset"),
    width: 150,
    fixed: "right",
    render: (row) => {
      const datasets = row.datasets ?? [];
      if (datasets.length === 0) {
        return h(NText, { depth: 3 }, { default: () => t("sc.none") });
      }
      if (datasets.length === 1) {
        const dataset = datasets[0];
        return h(
          NButton,
          {
            size: "tiny",
            secondary: true,
            type: "primary",
            "data-row-click-stop": true,
            "data-testid": `open-dataset-${dataset.id}`,
            onClick: (event: MouseEvent) => {
              event.stopPropagation();
              emit("openDataset", dataset.id);
            },
          },
          { default: () => t("sc.openDataset") },
        );
      }
      return h(
        NButton,
        {
          size: "tiny",
          secondary: true,
          type: "primary",
          "data-row-click-stop": true,
          "data-testid": `show-datasets-${rowKey(row)}`,
          onClick: (event: MouseEvent) => {
            event.stopPropagation();
            showDatasets(row);
          },
        },
        { default: () => t("sc.datasets", { count: datasets.length }) },
      );
    },
  },
  {
    key: "actions",
    title: t("common.actions"),
    width: 190,
    fixed: "right",
    render: (row) =>
      h(
        NSpace,
        { size: 6, wrap: false },
        {
          default: () => [
            h(
              NButton,
              {
                size: "tiny",
                secondary: true,
                "data-row-click-stop": true,
                "data-testid": `preview-inspection-${rowKey(row)}`,
                onClick: (event: MouseEvent) => {
                  event.stopPropagation();
                  emit("rowClick", row);
                },
              },
              { default: () => t("common.preview") },
            ),
            h(
              NButton,
              {
                size: "tiny",
                type: "primary",
                secondary: true,
                loading: props.importingInspectionKey === rowKey(row),
                disabled:
                  props.importingInspectionKey !== null &&
                  props.importingInspectionKey !== rowKey(row),
                "data-row-click-stop": true,
                "data-testid": `create-dataset-${rowKey(row)}`,
                onClick: (event: MouseEvent) => {
                  event.stopPropagation();
                  emit("createDataset", row);
                },
              },
              { default: () => t("sc.newDataset") },
            ),
          ],
        },
      ),
  },
]);

const clickableRowStyle = { cursor: "pointer" };
const tablePagination = reactive<PaginationProps>({
  page: 1,
  pageSize: 100,
  showSizePicker: true,
  pageSizes: [50, 100, 200, 500],
  onUpdatePage: (page: number) => {
    tablePagination.page = page;
  },
  onUpdatePageSize: (pageSize: number) => {
    tablePagination.pageSize = pageSize;
    tablePagination.page = 1;
  },
});

function rowProps(row: InspectionSummaryItem): Record<string, unknown> {
  const isLastOpened = rowKey(row) === props.lastOpenedSummaryKey;
  return {
    class: isLastOpened ? "sc-summary-row--last-opened" : "",
    style: clickableRowStyle,
    "data-testid": `inspection-row-${rowKey(row)}`,
    onClick: (event: MouseEvent) => {
      if (shouldIgnoreSummaryRowClick(event.target)) return;
      emit("rowClick", row);
    },
  };
}
</script>

<template>
  <div class="sc-preview-tabsummary">
    <div class="sc-preview-search-bar">
      <NSpace align="center" :wrap="true" :size="8">
        <NDatePicker
          :value="dateRange"
          type="daterange"
          clearable
          style="width: 280px"
          size="small"
          @update:value="emit('update:dateRange', $event)"
        />
        <NTooltip trigger="hover">
          <template #trigger>
            <NInput
              :value="deviceFilter"
              :placeholder="t('sc.device')"
              size="small"
              style="width: 140px"
              clearable
              @update:value="emit('update:deviceFilter', $event)"
            />
          </template>
          {{ t("sc.filterHelp", { item: t("sc.device").toLowerCase() }) }}
        </NTooltip>
        <NTooltip trigger="hover">
          <template #trigger>
            <NInput
              :value="layerIdFilter"
              :placeholder="t('sc.layerId')"
              size="small"
              style="width: 140px"
              clearable
              @update:value="emit('update:layerIdFilter', $event)"
            />
          </template>
          {{ t("sc.filterHelp", { item: t("sc.layerId").toLowerCase() }) }}
        </NTooltip>
        <NTooltip trigger="hover">
          <template #trigger>
            <NInput
              :value="lotIdFilter"
              :placeholder="t('sc.lotId')"
              size="small"
              style="width: 140px"
              clearable
              @update:value="emit('update:lotIdFilter', $event)"
            />
          </template>
          {{ t("sc.filterHelp", { item: t("sc.lotId").toLowerCase() }) }}
        </NTooltip>
        <NTooltip trigger="hover">
          <template #trigger>
            <NInput
              :value="eqpIdFilter"
              :placeholder="t('sc.equipmentId')"
              size="small"
              style="width: 160px"
              clearable
              @update:value="emit('update:eqpIdFilter', $event)"
            />
          </template>
          {{ t("sc.filterHelp", { item: t("sc.equipmentId").toLowerCase() }) }}
        </NTooltip>
        <NButton
          type="primary"
          :disabled="dateRange === null"
          :loading="summariesLoading"
          @click="emit('search')"
          size="small"
        >
          {{ t("common.search") }}
        </NButton>
        <NButton
          v-if="selectedRowKeys.length > 0"
          size="small"
          type="primary"
          secondary
          data-testid="build-collection"
          @click="emit('buildCollection')"
        >
          {{ t("sc.buildCollection", { count: selectedRowKeys.length }) }}
        </NButton>
        <NText v-if="lastOpenedSummaryLabel" depth="3" class="sc-preview-last-opened">
          {{ t("sc.lastOpened", { label: lastOpenedSummaryLabel }) }}
        </NText>
      </NSpace>
    </div>
    <div class="sc-preview-table-wrapper">
      <NDataTable
        :columns="selectableColumns"
        :data="summaries"
        :loading="summariesLoading"
        :row-key="rowKey"
        :checked-row-keys="selectedRowKeys"
        @update:checked-row-keys="emit('update:selectedRowKeys', $event.map(String))"
        :row-props="rowProps"
        :pagination="tablePagination"
        :single-line="false"
        :virtual-scroll="true"
        :scroll-x="1480"
        :min-row-height="32"
        striped
        size="small"
        flex-height
        style="flex: 1"
      >
        <template #empty>
          <div class="sc-preview-empty">
            <NText v-if="summariesError" type="error">{{ summariesError }}</NText>
            <NEmpty v-else-if="summariesEmpty" :description="t('sc.noInspections')" size="small">
              <template #extra>
                <NText depth="3">{{ t("sc.widenRange") }}</NText>
              </template>
            </NEmpty>
            <NEmpty v-else :description="t('sc.chooseRange')" size="small" />
            <NButton v-if="summariesError" size="small" @click="emit('search')">
              {{ t("common.retry") }}
            </NButton>
          </div>
        </template>
      </NDataTable>
    </div>

    <NModal
      v-model:show="datasetListVisible"
      preset="card"
      :title="t('sc.inspectionDatasets')"
      style="width: min(560px, 92vw)"
    >
      <NList bordered>
        <NListItem v-for="dataset in datasetList" :key="dataset.id">
          <div class="sc-dataset-list-row">
            <NText>{{ dataset.name }}</NText>
            <NButton
              size="small"
              type="primary"
              secondary
              :data-testid="`open-dataset-${dataset.id}`"
              @click="emit('openDataset', dataset.id)"
            >
              {{ t("datasetDetail.openNewTab") }}
            </NButton>
          </div>
        </NListItem>
      </NList>
    </NModal>
  </div>
</template>

<style scoped>
.sc-preview-tabsummary {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.sc-preview-search-bar {
  flex-shrink: 0;
  padding: 8px 0;
  border-bottom: 1px solid var(--cv-border, rgba(255, 255, 255, 0.08));
}

.sc-preview-table-wrapper {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.sc-dataset-list-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
}

.sc-preview-empty {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  min-height: 180px;
}

.sc-preview-last-opened {
  font-size: 12px;
  white-space: nowrap;
}

:deep(.sc-summary-row--last-opened td) {
  background: rgba(24, 160, 88, 0.14);
  background: color-mix(in srgb, var(--cv-primary, #18a058) 14%, transparent);
}

:deep(.sc-summary-row--last-opened td:first-child) {
  box-shadow: inset 3px 0 0 var(--cv-primary, #18a058);
}

:deep(.n-data-table-th__title) {
  white-space: nowrap;
}
</style>
