<template>
  <div class="ag" @keydown="onKeyDown" tabindex="-1">
    <!-- Label panel (left) -->
    <div v-if="!readOnly" class="ag-label-panel">
      <input
        v-model="labelSearch"
        class="ag-label-search"
        :placeholder="t('widgets.searchLabels')"
        @keydown.stop
      />
      <div class="ag-label-list">
        <div
          v-for="(label, idx) in filteredLabels"
          :key="label"
          class="ag-label-item"
          :class="{ 'ag-label-item--active': false }"
          @click="applyLabelToSelection(label)"
          :title="label"
        >
          <span class="ag-label-dot" :style="{ background: labelColor(label) }" />
          <span class="ag-label-name">{{ label }}</span>
          <span v-if="idx < 9" class="ag-label-shortcut">{{ idx + 1 }}</span>
        </div>
      </div>
      <button v-if="showAddLabel" class="ag-label-add" @click="emit('add-label', '')">
        {{ t("widgets.addLabel") }}
      </button>
    </div>

    <!-- Shared Browser core (right) -->
    <SampleBrowser
      ref="browserRef"
      class="ag-browser-area"
      :items="browserItems"
      :totalCount="totalCount"
      :thumbSize="thumbSize"
      :layout="layout"
      :isLoading="isLoading"
      :selectionEnabled="!readOnly"
      :showCheckboxes="!readOnly"
      :showBottomBar="!readOnly"
      :showLabelRail="false"
      activationMode="select"
      @select="onBrowserSelect"
      @load-more="emit('load-more')"
    >
      <template #bar-left>
        <slot name="bar-left" />
      </template>
      <template #bar-right>
        <button
          class="ag-submit-btn"
          :disabled="submitting || draftCount === 0"
          @click="emit('submit')"
        >
          {{
            submitting ? t("widgets.submitting") : t("widgets.submitCount", { count: draftCount })
          }}
        </button>
      </template>
    </SampleBrowser>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from "vue";
import { useI18n } from "vue-i18n";
import type { AnnotationGridItem, BrowserItem } from "../../types/components";
import SampleBrowser from "../sample-browser/SampleBrowser.vue";

const { t } = useI18n();

// ---------------------------------------------------------------------------
// Props / Events
// ---------------------------------------------------------------------------

const props = withDefaults(
  defineProps<{
    items: AnnotationGridItem[];
    totalCount: number;
    labelSpace: string[];
    thumbSize?: number;
    layout?: "grid" | "list";
    isLoading?: boolean;
    submitting?: boolean;
    showAddLabel?: boolean;
    readOnly?: boolean;
  }>(),
  {
    thumbSize: 160,
    layout: "grid",
    isLoading: false,
    submitting: false,
    showAddLabel: true,
    readOnly: false,
  },
);

const emit = defineEmits<{
  select: [ids: Set<string>];
  "apply-label": [payload: { ids: string[]; label: string }];
  submit: [];
  "load-more": [];
  "add-label": [name: string];
}>();

// ---------------------------------------------------------------------------
// Colors
// ---------------------------------------------------------------------------

const LABEL_COLORS = [
  "#4CAF50",
  "#2196F3",
  "#FF9800",
  "#E91E63",
  "#9C27B0",
  "#00BCD4",
  "#FF5722",
  "#795548",
  "#607D8B",
  "#CDDC39",
];

function labelColor(label: string): string {
  const idx = props.labelSpace.indexOf(label);
  if (idx === -1) return "#9E9E9E";
  return LABEL_COLORS[idx % LABEL_COLORS.length];
}

// ---------------------------------------------------------------------------
// Label panel
// ---------------------------------------------------------------------------

const labelSearch = ref("");

const filteredLabels = computed(() => {
  if (!labelSearch.value) return props.labelSpace;
  const q = labelSearch.value.toLowerCase();
  return props.labelSpace.filter((l) => l.toLowerCase().includes(q));
});

// ---------------------------------------------------------------------------
// Data mapping & Selection
// ---------------------------------------------------------------------------

const browserRef = ref<InstanceType<typeof SampleBrowser> | null>(null);
const selectedIds = ref<Set<string>>(new Set());

const draftCount = computed(() => props.items.filter((item) => item.draftLabel != null).length);

const browserItems = computed<BrowserItem[]>(() =>
  props.items.map((item) => ({
    ...item,
    activationLabel: null,
    sourceKind: "classify-review" as const,
  })),
);

function onBrowserSelect(ids: Set<string>) {
  selectedIds.value = ids;
  emit("select", ids);
}

function applyLabelToSelection(label: string) {
  if (selectedIds.value.size === 0) return;
  emit("apply-label", { ids: [...selectedIds.value], label });
}

// ---------------------------------------------------------------------------
// Keyboard shortcuts (1-9 for labels)
// ---------------------------------------------------------------------------

function onKeyDown(e: KeyboardEvent) {
  const el = document.activeElement;
  if (
    el instanceof HTMLInputElement ||
    el instanceof HTMLSelectElement ||
    el instanceof HTMLTextAreaElement ||
    (el instanceof HTMLElement && el.isContentEditable)
  )
    return;

  const num = parseInt(e.key, 10);
  if (isNaN(num) || num < 1 || num > 9) return;
  const label = props.labelSpace[num - 1];
  if (!label) return;
  if (selectedIds.value.size === 0) return;
  e.preventDefault();
  applyLabelToSelection(label);
}

// ---------------------------------------------------------------------------
// Expose for parent ref access
// ---------------------------------------------------------------------------

defineExpose({
  selectedIds,
  clearSelection: () => {
    if (browserRef.value) {
      browserRef.value.clearSelection();
    } else {
      selectedIds.value = new Set();
      emit("select", selectedIds.value);
    }
  },
});
</script>

<style scoped>
.ag {
  display: flex;
  width: 100%;
  height: 100%;
  min-height: 0;
  outline: none;
}

/* Label panel */
.ag-label-panel {
  display: flex;
  flex-direction: column;
  width: 170px;
  min-width: 170px;
  border-right: 1px solid var(--cv-border, rgba(255, 255, 255, 0.12));
  background: var(--cv-card-bg, #1e1e2e);
}

.ag-label-search {
  margin: 8px;
  padding: 6px 8px;
  border: 1px solid var(--cv-border, rgba(255, 255, 255, 0.12));
  border-radius: 4px;
  background: transparent;
  color: var(--cv-text, #fff);
  font-size: 12px;
  outline: none;
}

.ag-label-search::placeholder {
  color: var(--cv-text-disabled, rgba(255, 255, 255, 0.3));
}

.ag-label-list {
  flex: 1;
  overflow-y: auto;
  padding: 0 4px;
}

.ag-label-item {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 6px 8px;
  border-radius: 4px;
  cursor: pointer;
  user-select: none;
  font-size: 12px;
  color: var(--cv-text, #fff);
}

.ag-label-item:hover {
  background: var(--cv-hover, rgba(255, 255, 255, 0.08));
}

.ag-label-dot {
  width: 10px;
  height: 10px;
  border-radius: 50%;
  flex-shrink: 0;
}

.ag-label-name {
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.ag-label-shortcut {
  font-size: 10px;
  color: var(--cv-text-disabled, rgba(255, 255, 255, 0.3));
  flex-shrink: 0;
}

.ag-label-add {
  margin: 4px 8px 8px;
  padding: 6px;
  border: 1px dashed var(--cv-border, rgba(255, 255, 255, 0.12));
  border-radius: 4px;
  background: transparent;
  color: var(--cv-text-secondary, rgba(255, 255, 255, 0.5));
  cursor: pointer;
  font-size: 12px;
}

.ag-label-add:hover {
  border-color: var(--cv-primary, #4098fc);
  color: var(--cv-primary, #4098fc);
}

.ag-browser-area {
  flex: 1;
  min-width: 0;
}

.ag-submit-btn {
  padding: 6px 16px;
  border: none;
  border-radius: 4px;
  background: var(--cv-primary, #4098fc);
  color: white;
  font-size: 12px;
  font-weight: 600;
  cursor: pointer;
}

.ag-submit-btn:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}

.ag-submit-btn:not(:disabled):hover {
  background: var(--cv-primary-hover, #3080e0);
}
</style>
