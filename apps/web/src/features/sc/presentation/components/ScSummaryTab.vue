<script setup lang="ts">
import { reactive } from "vue";
import {
  NButton,
  NDataTable,
  NDatePicker,
  NInput,
  NSpace,
  NText,
  type DataTableColumns,
  type PaginationProps,
} from "naive-ui";
import type { InspectionSummaryItem } from "@/features/sc/domain/models";

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
}>();

const emit = defineEmits<{
  (e: "update:dateRange", value: [number, number] | null): void;
  (e: "update:lotIdFilter", value: string): void;
  (e: "update:eqpIdFilter", value: string): void;
  (e: "update:layerIdFilter", value: string): void;
  (e: "update:deviceFilter", value: string): void;
  (e: "search"): void;
  (e: "rowClick", row: InspectionSummaryItem): void;
}>();

function rowKey(row: InspectionSummaryItem): string {
  return `${row.inspection_time}_${row.wafer_key}`;
}

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
    onClick: () => emit("rowClick", row),
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
        <NInput
          :value="deviceFilter"
          placeholder="Device (*, a,b)"
          size="small"
          style="width: 140px"
          clearable
          @update:value="emit('update:deviceFilter', $event)"
        />
        <NInput
          :value="layerIdFilter"
          placeholder="Layer ID (*, a,b)"
          size="small"
          style="width: 140px"
          clearable
          @update:value="emit('update:layerIdFilter', $event)"
        />
        <NInput
          :value="lotIdFilter"
          placeholder="Lot ID (*, a,b)"
          size="small"
          style="width: 140px"
          clearable
          @update:value="emit('update:lotIdFilter', $event)"
        />
        <NInput
          :value="eqpIdFilter"
          placeholder="Equipment ID (*, a,b)"
          size="small"
          style="width: 160px"
          clearable
          @update:value="emit('update:eqpIdFilter', $event)"
        />
        <NButton
          type="primary"
          :disabled="dateRange === null"
          :loading="summariesLoading"
          @click="emit('search')"
          size="small"
        >
          Search
        </NButton>
        <NText
          v-if="lastOpenedSummaryLabel"
          depth="3"
          class="sc-preview-last-opened"
        >
          Last opened: {{ lastOpenedSummaryLabel }}
        </NText>
      </NSpace>
    </div>
    <div class="sc-preview-table-wrapper">
      <NDataTable
        :columns="inspectionColumns"
        :data="summaries"
        :loading="summariesLoading"
        :row-key="rowKey"
        :row-props="rowProps"
        :pagination="tablePagination"
        :single-line="false"
        :virtual-scroll="true"
        :min-row-height="32"
        striped
        size="small"
        flex-height
        style="flex: 1"
      >
        <template #empty>
          <div class="sc-preview-empty">
            <NText v-if="summariesError" type="error">{{
              summariesError
            }}</NText>
            <NText v-else-if="summariesEmpty" depth="3"
              >No inspections found</NText
            >
            <NText v-else depth="3">Enter a time range to search</NText>
            <NButton v-if="summariesError" size="small" @click="emit('search')">
              Retry
            </NButton>
          </div>
        </template>
      </NDataTable>
    </div>
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
  margin-bottom: 8px;
}

.sc-preview-table-wrapper {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.sc-preview-empty {
  display: inline-flex;
  align-items: center;
  gap: 8px;
}

.sc-preview-last-opened {
  font-size: 12px;
  white-space: nowrap;
}

:deep(.sc-summary-row--last-opened td) {
  background: color-mix(in srgb, var(--cv-primary, #18a058) 14%, transparent);
}

:deep(.sc-summary-row--last-opened td:first-child) {
  box-shadow: inset 3px 0 0 var(--cv-primary, #18a058);
}
</style>
