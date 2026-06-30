<script setup lang="ts">
import { computed, onUpdated, ref } from "vue";
import { NButton, NPopover, NSpace, NTag, NText } from "naive-ui";
import type { ScSampleTableFilter } from "@/features/sc/domain/sampleTable";
import ScRangeFilterMenu from "./ScRangeFilterMenu.vue";
import ScSetFilterMenu from "./ScSetFilterMenu.vue";

type SetField = "test_id" | "annotation_label" | "prediction_label" | "final_class";
type RangeField = "prediction_confidence";
type GlobalField = SetField | RangeField;

const SET_FIELDS: Array<{ field: SetField; label: string }> = [
  { field: "test_id", label: "Test ID" },
  { field: "prediction_label", label: "Prediction" },
  { field: "final_class", label: "Final Class" },
];

const props = defineProps<{
  filter: ScSampleTableFilter;
  distinctValues: Partial<Record<SetField, Array<string | number>>>;
}>();

const emit = defineEmits<{
  (e: "update:filter", filter: ScSampleTableFilter): void;
  (e: "search-options", payload: { field: SetField; search: string }): void;
}>();

const searchByField = ref<Partial<Record<SetField, string>>>({});
const draftByField = ref<Partial<Record<SetField, string[]>>>({});
const rangeDraft = ref<Record<RangeField, { min: number | null; max: number | null }>>({
  prediction_confidence: { min: null, max: null },
});

const activeCount = computed(() => Object.keys(props.filter ?? {}).length);

function setFilterValues(field: SetField): Array<string | number> {
  const filter = props.filter[field];
  return filter?.filterType === "set" ? filter.values : [];
}

function rangeFilterValues(field: RangeField): { min: number | null; max: number | null } {
  const filter = props.filter[field];
  return filter?.filterType === "number" && filter.type === "inRange"
    ? { min: filter.filter, max: filter.filterTo }
    : { min: null, max: null };
}

function optionsFor(field: SetField): Array<{ label: string; value: string | number }> {
  const values = new Map<string, string | number>();
  for (const value of props.distinctValues[field] ?? []) values.set(String(value), value);
  for (const value of setFilterValues(field)) values.set(String(value), value);
  return Array.from(values.values())
    .sort((left, right) =>
      typeof left === "number" && typeof right === "number"
        ? left - right
        : String(left).localeCompare(String(right), undefined, { numeric: true }),
    )
    .map((value) => ({ label: String(value), value }));
}

function applySetFilter(field: SetField, values: Array<string | number>): void {
  const next = { ...(props.filter ?? {}) };
  if (values.length === 0) delete next[field];
  else next[field] = { filterType: "set", values };
  emit("update:filter", next);
}

function applyRangeFilter(field: RangeField): void {
  const draft = rangeDraft.value[field];
  const next = { ...(props.filter ?? {}) };
  if (draft.min === null || draft.max === null || draft.min > draft.max) delete next[field];
  else {
    next[field] = {
      filterType: "number",
      type: "inRange",
      filter: draft.min,
      filterTo: draft.max,
    };
  }
  emit("update:filter", next);
}

function clearRangeFilter(field: RangeField): void {
  rangeDraft.value[field] = { min: null, max: null };
  const next = { ...(props.filter ?? {}) };
  delete next[field];
  emit("update:filter", next);
}

function clearAll(): void {
  draftByField.value = {};
  searchByField.value = {};
  rangeDraft.value.prediction_confidence = { min: null, max: null };
  emit("update:filter", {});
}

onUpdated(() => console.debug("[render] ScGlobalFilterBar"));
</script>

<template>
  <div class="sc-global-filter-bar">
    <NText depth="3" class="sc-global-filter-title">Global Filters</NText>
    <NSpace :size="6" align="center">
      <NPopover
        v-for="item in SET_FIELDS"
        :key="item.field"
        trigger="click"
        placement="bottom-start"
      >
        <template #trigger>
          <NButton size="tiny" :type="setFilterValues(item.field).length ? 'primary' : 'default'">
            {{ item.label }}
            <NTag
              v-if="setFilterValues(item.field).length"
              size="tiny"
              round
              class="sc-filter-count"
            >
              {{ setFilterValues(item.field).length }}
            </NTag>
          </NButton>
        </template>
        <ScSetFilterMenu
          :search="searchByField[item.field] ?? ''"
          :applied-values="setFilterValues(item.field)"
          :draft-values="draftByField[item.field] ?? setFilterValues(item.field).map(String)"
          :options="optionsFor(item.field)"
          @update:search="searchByField[item.field] = $event"
          @update:draft-values="draftByField[item.field] = $event"
          @search-options="emit('search-options', { field: item.field, search: $event })"
          @apply="applySetFilter(item.field, $event)"
        />
      </NPopover>

      <NPopover trigger="click" placement="bottom-start">
        <template #trigger>
          <NButton
            size="tiny"
            :type="props.filter.prediction_confidence ? 'primary' : 'default'"
            @click="rangeDraft.prediction_confidence = rangeFilterValues('prediction_confidence')"
          >
            Confidence
          </NButton>
        </template>
        <ScRangeFilterMenu
          :min="rangeDraft.prediction_confidence.min"
          :max="rangeDraft.prediction_confidence.max"
          @update:min="rangeDraft.prediction_confidence.min = $event"
          @update:max="rangeDraft.prediction_confidence.max = $event"
          @apply="applyRangeFilter('prediction_confidence')"
          @clear="clearRangeFilter('prediction_confidence')"
        />
      </NPopover>

      <NButton size="tiny" quaternary :disabled="activeCount === 0" @click="clearAll"
        >Clear</NButton
      >
    </NSpace>
  </div>
</template>

<style scoped>
.sc-global-filter-bar {
  display: flex;
  align-items: center;
  gap: 8px;
  min-height: 32px;
  padding: 4px 6px;
  border-bottom: 1px solid var(--cv-border, rgba(255, 255, 255, 0.1));
}

.sc-global-filter-title {
  font-size: 12px;
  white-space: nowrap;
}

.sc-filter-count {
  margin-left: 4px;
}
</style>
