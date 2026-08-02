<script setup lang="ts">
import { computed, ref, watch } from "vue";
import { NButton, NPopover, NText } from "naive-ui";
import type { ScSampleTableFilter } from "@/features/sc/domain/sampleTable";
import { scMissingFilterOption } from "@/features/sc/domain/missingFilterValue";
import { scGlobalFilterColumns, type ScFilterColumnDefinition } from "./scSampleTableColumns";
import ScRangeFilterMenu from "./ScRangeFilterMenu.vue";
import ScSetFilterMenu from "./ScSetFilterMenu.vue";
import ScTextFilterMenu from "./ScTextFilterMenu.vue";

const props = withDefaults(
  defineProps<{
    filter: ScSampleTableFilter;
    distinctValues: Record<string, Array<string | number>>;
    numericRanges?: Record<string, { min: number; max: number } | null>;
    numericRangeLoading?: Record<string, boolean>;
    numericRangeErrors?: Record<string, boolean>;
    showReclassifyColumns?: boolean;
  }>(),
  {
    numericRanges: () => ({}),
    numericRangeLoading: () => ({}),
    numericRangeErrors: () => ({}),
  },
);

const emit = defineEmits<{
  (e: "update:filter", filter: ScSampleTableFilter): void;
  (e: "search-options", payload: { field: string; search: string }): void;
  (e: "request-range", field: string): void;
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
    .map((value) => ({
      label:
        scMissingFilterOption(field)?.value === value
          ? (scMissingFilterOption(field)?.label ?? String(value))
          : String(value),
      value,
    }));
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
    emit("request-range", field);
  } else {
    draftByField.value[field] = setFilterValues(field).map(String);
  }
}

watch(
  () => props.numericRanges,
  (ranges) => {
    for (const [field, range] of Object.entries(ranges)) {
      if (!range || props.filter[field]?.filterType === "number") continue;
      const draft = rangeDraft.value[field];
      if (!draft || (draft.min === null && draft.max === null)) {
        rangeDraft.value[field] = { ...range };
      }
    }
  },
  { deep: true },
);
</script>

<template>
  <div class="sc-global-filter-bar">
    <div class="sc-global-filter-toolbar">
      <div>
        <NText strong class="sc-global-filter-title">Filter fields</NText>
        <NText depth="3" class="sc-global-filter-hint">
          Choose a field to set its allowed values or range.
        </NText>
      </div>
      <NButton
        size="small"
        quaternary
        type="primary"
        :disabled="activeCount === 0"
        @click="clearAll"
      >
        Clear all
      </NButton>
    </div>

    <div class="sc-global-filter-fields">
      <NPopover
        v-for="definition in fieldDefinitions"
        :key="String(definition.key)"
        trigger="click"
        placement="bottom-start"
        @update:show="openFilter(definition, $event)"
      >
        <template #trigger>
          <NButton
            size="small"
            secondary
            class="sc-global-filter-field"
            :type="props.filter[String(definition.key)] ? 'primary' : 'default'"
          >
            <span class="sc-global-filter-field-content">
              <span class="sc-global-filter-field-label">{{ definition.title }}</span>
              <span
                v-if="props.filter[String(definition.key)]"
                class="sc-global-filter-field-state"
              >
                {{
                  setFilterValues(String(definition.key)).length > 0
                    ? setFilterValues(String(definition.key)).length
                    : "On"
                }}
              </span>
            </span>
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
          :loading="numericRangeLoading[String(definition.key)] === true"
          :range-unavailable="numericRangeErrors[String(definition.key)] === true"
          @update:min="getRangeDraft(String(definition.key)).min = $event"
          @update:max="getRangeDraft(String(definition.key)).max = $event"
          @apply="applyRangeFilter(String(definition.key))"
          @clear="clearRangeFilter(String(definition.key))"
        />
      </NPopover>
    </div>
  </div>
</template>

<style scoped>
.sc-global-filter-bar {
  display: block;
  min-height: 0;
}

.sc-global-filter-toolbar {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
  margin-bottom: 14px;
}

.sc-global-filter-title,
.sc-global-filter-hint {
  display: block;
}

.sc-global-filter-title {
  font-size: 13px;
  line-height: 20px;
}

.sc-global-filter-hint {
  margin-top: 1px;
  font-size: 12px;
  line-height: 18px;
}

.sc-global-filter-fields {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(112px, 1fr));
  gap: 8px;
  max-height: min(420px, calc(100vh - 300px));
  padding: 1px 4px 4px 1px;
  overflow-y: auto;
}

.sc-global-filter-field {
  width: 100%;
}

.sc-global-filter-field-content {
  display: flex;
  width: 100%;
  min-width: 0;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}

.sc-global-filter-field-label {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.sc-global-filter-field-state {
  display: inline-grid;
  flex: 0 0 auto;
  min-width: 20px;
  height: 20px;
  padding: 0 5px;
  place-items: center;
  color: var(--cv-primary, #4c80f0);
  font-size: 10px;
  font-weight: 600;
  line-height: 20px;
  border-radius: 10px;
  background: color-mix(in srgb, var(--cv-primary, #4c80f0) 13%, transparent);
}
</style>
