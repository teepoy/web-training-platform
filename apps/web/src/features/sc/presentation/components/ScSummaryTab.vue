<script setup lang="ts">
import { ref } from "vue";
import {
  NButton,
  NDataTable,
  NDatePicker,
  NInput,
  NSpace,
  NText,
  type DataTableColumns,
} from "naive-ui";
import type { InspectionSummaryItem } from "@/features/sc/domain/models";

const props = defineProps<{
  dateRange: [number, number] | null;
  summariesLoading: boolean;
  summaries: InspectionSummaryItem[];
  inspectionColumns: DataTableColumns<InspectionSummaryItem>;
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

const filtersExpanded = ref(false);

function rowKey(row: InspectionSummaryItem): string {
  return `${row.inspection_time}_${row.wafer_key}`;
}

function rowProps(row: InspectionSummaryItem): Record<string, unknown> {
  return {
    style: { cursor: "pointer" },
    onClick: () => emit("rowClick", row),
  };
}
</script>

<template>
  <div class="sc-preview-tabsummary">
    <div class="sc-preview-search-bar">
      <NSpace vertical :size="8">
        <NSpace align="center" :wrap="false">
          <NDatePicker
            :value="dateRange"
            type="daterange"
            clearable
            style="width: 280px"
            size="small"
            @update:value="emit('update:dateRange', $event)"
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
          <NButton
            text
            size="small"
            @click="filtersExpanded = !filtersExpanded"
          >
            {{ filtersExpanded ? 'Filters ▴' : 'Filters ▾' }}
          </NButton>
        </NSpace>
        <NSpace v-if="filtersExpanded" align="center" :wrap="false">
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
        </NSpace>
      </NSpace>
    </div>
    <div class="sc-preview-table-wrapper">
      <NDataTable
        :columns="inspectionColumns"
        :data="summaries"
        :row-key="rowKey"
        :row-props="rowProps"
        :single-line="false"
        striped
        size="small"
        flex-height
        style="flex: 1"
      >
        <template #empty>
          <NText depth="3">No inspections</NText>
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
</style>
