<script setup lang="ts">
import { computed, onUpdated, ref } from "vue";
import { NButton, NPopover, NSpace, NTag, NText } from "naive-ui";
import type { ScSampleTableFilter } from "@/features/sc/domain/sampleTable";
import { scGlobalFilterColumns, type ScFilterColumnDefinition } from "./scSampleTableColumns";
import ScRangeFilterMenu from "./ScRangeFilterMenu.vue";
import ScSetFilterMenu from "./ScSetFilterMenu.vue";
import ScTextFilterMenu from "./ScTextFilterMenu.vue";

const props = defineProps<{
  filter: ScSampleTableFilter;
  distinctValues: Record<string, Array<string | number>>;
  showReclassifyColumns?: boolean;
}>();

const emit = defineEmits<{
  (e: "update:filter", filter: ScSampleTableFilter): void;
  (e: "search-options", payload: { field: string; search: string }): void;
}>();

const searchByField = ref<Record<string, string>>({});
const draftByField = ref<Record<string, string[]>>({});
const rangeDraft = ref<Record<string, { min: number | null; max: number | null }>>({});

const activeCount = computed(() => Object.keys(props.filter ?? {}).length);
const fieldDefinitions = computed(() =>
  scGlobalFilterColumns(props.showReclassifyColumns === true),
);

function setFilterValues(field: string): Array<string | number> {
  const filter = props.filter[field];
  return filter?.filterType === "set" ? filter.values : [];
}

function rangeFilterValues(field: string): { min: number | null; max: number | null } {
  const filter = props.filter[field];
  return filter?.filterType === "number" && filter.type === "inRange"
    ? { min: filter.filter, max: filter.filterTo }
    : { min: null, max: null };
}

function getRangeDraft(field: string): { min: number | null; max: number | null } {
  if (!rangeDraft.value[field]) {
    rangeDraft.value[field] = rangeFilterValues(field);
  }
  return rangeDraft.value[field];
}

function optionsFor(field: string): Array<{ label: string; value: string | number }> {
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

function normalizeFilterValue(field: string, value: string | number): string | number {
  if (field !== "defect_id") return value;
  const numeric = Number(value);
  return Number.isFinite(numeric) ? numeric : value;
}

function applySetFilter(field: string, values: Array<string | number>): void {
  const next = { ...(props.filter ?? {}) };
  if (values.length === 0) delete next[field];
  else {
    next[field] = {
      filterType: "set",
      values: values.map((value) => normalizeFilterValue(field, value)),
    };
  }
  emit("update:filter", next);
}

function applyRangeFilter(field: string): void {
  const draft = getRangeDraft(field);
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

function clearRangeFilter(field: string): void {
  rangeDraft.value[field] = { min: null, max: null };
  const next = { ...(props.filter ?? {}) };
  delete next[field];
  emit("update:filter", next);
}

function clearAll(): void {
  draftByField.value = {};
  searchByField.value = {};
  rangeDraft.value = {};
  emit("update:filter", {});
}

function openFilter(definition: ScFilterColumnDefinition, open: boolean): void {
  if (!open) return;
  const field = String(definition.key);
  if (definition.filter === "range") {
    rangeDraft.value[field] = rangeFilterValues(field);
  } else {
    draftByField.value[field] = setFilterValues(field).map(String);
  }
}

onUpdated(() => console.debug("[render] ScGlobalFilterBar"));
</script>

<template>
  <div class="sc-global-filter-bar">
    <NText depth="3" class="sc-global-filter-title">Global Filters</NText>
    <div class="sc-global-filter-fields">
      <NSpace :size="8" align="center" :wrap="true">
        <NPopover
          v-for="definition in fieldDefinitions"
          :key="String(definition.key)"
          trigger="click"
          placement="bottom-start"
          @update:show="openFilter(definition, $event)"
        >
          <template #trigger>
            <NButton
              size="tiny"
              :type="props.filter[String(definition.key)] ? 'primary' : 'default'"
            >
              {{ definition.title }}
              <NTag
                v-if="setFilterValues(String(definition.key)).length"
                size="tiny"
                round
                class="sc-filter-count"
              >
                {{ setFilterValues(String(definition.key)).length }}
              </NTag>
            </NButton>
          </template>
          <ScTextFilterMenu
            v-if="definition.key === 'defect_id'"
            :applied-values="setFilterValues('defect_id')"
            @apply="applySetFilter('defect_id', $event)"
          />
          <ScSetFilterMenu
            v-else-if="definition.filter === 'set'"
            :search="searchByField[String(definition.key)] ?? ''"
            :applied-values="setFilterValues(String(definition.key))"
            :draft-values="
              draftByField[String(definition.key)] ??
              setFilterValues(String(definition.key)).map(String)
            "
            :options="optionsFor(String(definition.key))"
            @update:search="searchByField[String(definition.key)] = $event"
            @update:draft-values="draftByField[String(definition.key)] = $event"
            @search-options="
              emit('search-options', { field: String(definition.key), search: $event })
            "
            @apply="applySetFilter(String(definition.key), $event)"
          />
          <ScRangeFilterMenu
            v-else
            :min="getRangeDraft(String(definition.key)).min"
            :max="getRangeDraft(String(definition.key)).max"
            @update:min="getRangeDraft(String(definition.key)).min = $event"
            @update:max="getRangeDraft(String(definition.key)).max = $event"
            @apply="applyRangeFilter(String(definition.key))"
            @clear="clearRangeFilter(String(definition.key))"
          />
        </NPopover>
      </NSpace>
    </div>

    <NButton size="tiny" quaternary :disabled="activeCount === 0" @click="clearAll">Clear</NButton>
  </div>
</template>

<style scoped>
.sc-global-filter-bar {
  display: flex;
  align-items: flex-start;
  gap: 12px;
  min-height: 32px;
  padding: 4px 6px;
  border-bottom: 1px solid var(--cv-border, rgba(255, 255, 255, 0.1));
}

.sc-global-filter-title {
  flex: 0 0 auto;
  padding-top: 5px;
  font-size: 12px;
  white-space: nowrap;
}

.sc-global-filter-fields {
  flex: 1 1 auto;
  min-width: 0;
}

.sc-filter-count {
  margin-left: 4px;
}
</style>
