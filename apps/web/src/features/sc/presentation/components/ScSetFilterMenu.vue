<script setup lang="ts">
import { computed, onMounted, ref, watch } from "vue";
import { NButton, NCheckbox, NInput, NSpace, NText } from "naive-ui";

const props = defineProps<{
  search: string;
  appliedValues: Array<string | number>;
  draftValues: string[];
  options: Array<{ label: string; value: string | number }>;
}>();

const emit = defineEmits<{
  (e: "update:search", value: string): void;
  (e: "update:draftValues", value: string[]): void;
  (e: "search-options", value: string): void;
  (e: "apply", value: Array<string | number>): void;
  (e: "close"): void;
}>();

onMounted(() => {
  emit("search-options", "");
});

const searchText = computed(() => props.search.trim().toLowerCase());
const isSearching = computed(() => searchText.value.length > 0);
const appliedKeys = computed(() => new Set(props.appliedValues.map(String)));
const draftKeys = computed(() => new Set(props.draftValues));
const visibleOptions = computed(() =>
  isSearching.value
    ? props.options.filter((option) => option.label.toLowerCase().includes(searchText.value))
    : props.options,
);
const visibleKeys = computed(() => visibleOptions.value.map((option) => String(option.value)));
const selectedVisibleCount = computed(
  () => visibleKeys.value.filter((key) => draftKeys.value.has(key)).length,
);
const allVisibleSelected = computed(
  () => visibleKeys.value.length > 0 && selectedVisibleCount.value === visibleKeys.value.length,
);
const someVisibleSelected = computed(
  () => selectedVisibleCount.value > 0 && !allVisibleSelected.value,
);
const knownValuesByKey = ref(new Map<string, string | number>());

watch(
  [() => props.options, () => props.appliedValues],
  ([options, appliedValues]) => {
    const next = new Map(knownValuesByKey.value);
    for (const option of options) next.set(String(option.value), option.value);
    for (const value of appliedValues) next.set(String(value), value);
    knownValuesByKey.value = next;
  },
  { deep: true, immediate: true },
);

function updateSearch(value: string): void {
  emit("update:search", value);
  emit("search-options", value);
}

function updateDraft(option: string | number, checked: boolean): void {
  const next = new Set(draftKeys.value);
  const key = String(option);
  if (checked) next.add(key);
  else next.delete(key);
  emit("update:draftValues", Array.from(next));
}

function updateAllVisible(checked: boolean): void {
  const next = new Set(draftKeys.value);
  for (const key of visibleKeys.value) {
    if (checked) next.add(key);
    else next.delete(key);
  }
  emit("update:draftValues", Array.from(next));
}

function resetDraft(): void {
  updateSearch("");
  emit("update:draftValues", props.appliedValues.map(String));
}

function clearDraft(): void {
  emit("update:draftValues", []);
}

function applyDraft(): void {
  emit(
    "apply",
    props.draftValues
      .map((key) => knownValuesByKey.value.get(key))
      .filter(
        (value): value is string | number => typeof value === "string" || typeof value === "number",
      ),
  );
  emit("close");
}
</script>

<template>
  <div class="sst-filter-popover sst-filter-popover--set">
    <div class="sst-filter-search-row">
      <NInput
        :value="search"
        placeholder="Search"
        size="small"
        clearable
        @update:value="updateSearch"
      />
    </div>
    <NCheckbox
      v-if="visibleOptions.length > 0"
      class="sst-set-filter-select-all"
      :checked="allVisibleSelected"
      :indeterminate="someVisibleSelected"
      @update:checked="updateAllVisible"
    >
      Select all ({{ visibleOptions.length }})
    </NCheckbox>
    <div class="sst-set-filter-options">
      <template v-if="visibleOptions.length > 0">
        <NCheckbox
          v-for="option in visibleOptions"
          :key="String(option.value)"
          class="sst-set-filter-option"
          :checked="draftKeys.has(String(option.value))"
          @update:checked="updateDraft(option.value, $event)"
        >
          {{ option.label }}
        </NCheckbox>
      </template>
      <NText v-else-if="isSearching" depth="3" class="sst-set-filter-empty">No matches</NText>
      <NText
        v-else-if="appliedKeys.size === 0 && visibleOptions.length === 0"
        depth="3"
        class="sst-set-filter-empty"
      >
        Loading...
      </NText>
    </div>
    <NSpace :size="4">
      <NButton size="tiny" quaternary @click="resetDraft">Reset</NButton>
      <NButton size="tiny" quaternary @click="clearDraft">Clear</NButton>
      <NButton size="tiny" type="primary" @click="applyDraft">Apply</NButton>
    </NSpace>
  </div>
</template>

<style scoped>
.sst-filter-popover {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 8px;
  max-width: min(320px, calc(100vw - 48px));
  min-width: 0;
}

.sst-filter-popover--set {
  width: 260px;
}

.sst-set-filter-options {
  display: flex;
  flex-direction: column;
  gap: 4px;
  max-height: 220px;
  min-width: 0;
  max-width: 100%;
  overflow-y: auto;
  overflow-x: hidden;
}

.sst-set-filter-select-all {
  padding-bottom: 6px;
  border-bottom: 1px solid color-mix(in srgb, currentColor 12%, transparent);
  font-weight: 600;
}

.sst-filter-search-row {
  display: flex;
  gap: 6px;
}

.sst-filter-search-row :deep(.n-input) {
  flex: 1;
  min-width: 0;
}

.sst-set-filter-option {
  min-width: 0;
  max-width: 100%;
}

.sst-set-filter-option :deep(.n-checkbox__label) {
  display: block;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.sst-set-filter-empty {
  font-size: 12px;
  padding: 4px 0;
}
</style>
