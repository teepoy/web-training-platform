<script setup lang="ts">
import { computed, onBeforeUnmount, ref } from "vue";
import {
  NButton,
  NDivider,
  NImage,
  NInput,
  NModal,
  NScrollbar,
  NTag,
  NText,
} from "naive-ui";
import type { AnnotationGridItem } from "@/shared/types/components";
import type { ReclassifyCodeLabel } from "../../application/useReclassifyPage";

const props = defineProps<{
  selectedCount: number;
  codeLabels: ReclassifyCodeLabel[];
  annotationDraft: Record<string, string>;
  draftCount: number;
  selectedDraftCount: number;
  isSubmitting: boolean;
  annotationGridItems: AnnotationGridItem[];
}>();

const emit = defineEmits<{
  "apply-code": [code: string];
  "set-shortcut": [code: string, shortcut: string];
  submit: [];
  "clear-drafts": [];
  "clear-selected-drafts": [];
}>();

const codeSearch = ref("");
const shortcutModalVisible = ref(false);
const shortcutTarget = ref<ReclassifyCodeLabel | null>(null);
const draftValues = computed(() => Object.values(props.annotationDraft));
const shortcutDisplay = computed(() => shortcutTarget.value?.shortcut || "-");

const filteredCodeLabels = computed(() => {
  const query = codeSearch.value.trim().toLowerCase();
  if (!query) return props.codeLabels;
  return props.codeLabels.filter((label) =>
    label.name.toLowerCase().includes(query),
  );
});

function openShortcutModal(label: ReclassifyCodeLabel): void {
  shortcutTarget.value = label;
  shortcutModalVisible.value = true;
  window.addEventListener("keydown", handleShortcutKeydown, true);
}

function closeShortcutModal(): void {
  shortcutModalVisible.value = false;
  shortcutTarget.value = null;
  window.removeEventListener("keydown", handleShortcutKeydown, true);
}

function clearShortcut(): void {
  if (!shortcutTarget.value) return;
  emit("set-shortcut", shortcutTarget.value.code, "");
  closeShortcutModal();
}

function handleShortcutKeydown(event: KeyboardEvent): void {
  if (!shortcutTarget.value) return;
  if (event.key === "Escape") {
    event.stopPropagation();
    event.preventDefault();
    closeShortcutModal();
    return;
  }
  if (
    event.ctrlKey ||
    event.metaKey ||
    event.altKey ||
    event.key.length !== 1
  ) {
    return;
  }
  event.stopPropagation();
  event.preventDefault();
  emit("set-shortcut", shortcutTarget.value.code, event.key.toLowerCase());
  closeShortcutModal();
}

onBeforeUnmount(() => {
  window.removeEventListener("keydown", handleShortcutKeydown, true);
});
</script>

<template>
  <aside class="sc-sidebar">
    <div class="sc-annotate">
      <div class="sc-annotate-header">
        <NText strong>Annotation</NText>
        <NTag
          v-if="selectedCount > 0"
          size="tiny"
          :bordered="false"
          type="warning"
        >
          {{ selectedCount }} sample{{ selectedCount === 1 ? "" : "s" }}
        </NTag>
      </div>

      <NDivider style="margin: 8px 0" />

      <div class="sc-code-search">
        <label class="sc-code-search-label">Search</label>
        <NInput
          v-model:value="codeSearch"
          clearable
          data-testid="reclassify-code-search-input"
          placeholder="Filter code names..."
          size="small"
        />
      </div>

      <div class="sc-bulk-apply">
        <NText depth="3" class="sc-bulk-hint"> Apply to all selected: </NText>
        <NScrollbar
          class="sc-code-list"
          content-style="max-height: min(330px, 50vh);"
          data-testid="reclassify-code-list"
          style="max-height: min(330px, 50vh)"
        >
          <div class="sc-code-row sc-code-row-head">
            <span>Code</span>
            <span>Name</span>
            <span>Key</span>
          </div>
          <div
            v-for="label in filteredCodeLabels"
            :key="label.code"
            class="sc-code-row sc-code-button"
            :class="{
              'is-active': draftValues.some((value) => value === label.code),
            }"
            :data-testid="`reclassify-code-row-${label.code}`"
            role="button"
            tabindex="0"
            @click="emit('apply-code', label.code)"
            @keydown.enter.prevent="emit('apply-code', label.code)"
            @keydown.space.prevent="emit('apply-code', label.code)"
          >
            <span class="sc-code-value">{{ label.code }}</span>
            <span class="sc-code-name">{{ label.name }}</span>
            <NButton
              class="sc-shortcut-button"
              :data-testid="`reclassify-shortcut-button-${label.code}`"
              size="tiny"
              quaternary
              :aria-label="`Set shortcut for code ${label.code}`"
              @click.stop="openShortcutModal(label)"
              @keydown.stop
            >
              {{ label.shortcut || "-" }}
            </NButton>
          </div>
          <div v-if="filteredCodeLabels.length === 0" class="sc-code-empty">
            No code names match "{{ codeSearch.trim() }}"
          </div>
        </NScrollbar>
      </div>

      <div v-if="draftCount > 0" class="sc-draft-summary">
        <NText depth="3">
          {{ draftCount }} annotation{{ draftCount === 1 ? "" : "s" }} pending
        </NText>
      </div>

      <NDivider style="margin: 8px 0" />

      <div class="sc-actions">
        <NButton
          type="primary"
          size="small"
          :disabled="draftCount === 0"
          :loading="isSubmitting"
          @click="emit('submit')"
        >
          Submit {{ draftCount > 0 ? `(${draftCount})` : "" }}
        </NButton>
        <NButton
          v-if="draftCount > 0"
          size="small"
          @click="emit('clear-drafts')"
        >
          Clear Drafts
        </NButton>
        <NButton
          v-if="selectedCount > 0"
          size="small"
          :disabled="selectedDraftCount === 0"
          @click="emit('clear-selected-drafts')"
        >
          Clear Selected Draft{{ selectedDraftCount === 1 ? "" : "s" }}
        </NButton>
      </div>

      <NDivider style="margin: 8px 0" />

      <div class="sc-sample-detail">
        <NText depth="3" class="sc-detail-title">Sample Detail</NText>
        <div
          v-for="item in annotationGridItems"
          :key="item.id"
          class="sc-detail-row"
        >
          <div class="sc-detail-images">
            <NImage
              v-for="(src, i) in item.imageSrcs.slice(0, 3)"
              :key="i"
              :src="src"
              width="80"
              height="80"
              object-fit="cover"
              class="sc-detail-img"
              lazy
            />
          </div>
          <div class="sc-detail-meta">
            <div class="sc-meta-item">
              <span class="sc-meta-key">ID</span>
              <span class="sc-meta-val">{{ item.id.slice(0, 12) }}</span>
            </div>
            <div class="sc-meta-item">
              <span class="sc-meta-key">Defect</span>
              <span class="sc-meta-val">{{
                item.metadata.defectId ?? "\u2014"
              }}</span>
            </div>
            <div class="sc-meta-item">
              <span class="sc-meta-key">Class</span>
              <span class="sc-meta-val">{{
                item.metadata.classNumber ?? "\u2014"
              }}</span>
            </div>
            <div class="sc-meta-item">
              <span class="sc-meta-key">Current Label</span>
              <NTag
                v-if="item.currentLabel"
                size="tiny"
                :bordered="false"
                type="success"
              >
                {{ item.currentLabel }}
              </NTag>
              <span v-else class="sc-meta-val">\u2014</span>
            </div>
          </div>
        </div>
      </div>
    </div>

    <NModal
      v-model:show="shortcutModalVisible"
      preset="card"
      title="Assign Key"
      :style="{ width: '320px' }"
      @update:show="(show) => !show && closeShortcutModal()"
      @keydown.stop
    >
      <div class="sc-shortcut-modal">
        <div class="sc-shortcut-target">
          <NText depth="3">Code</NText>
          <NTag size="small" :bordered="false">{{ shortcutTarget?.code }}</NTag>
          <NText class="sc-shortcut-target-name">
            {{ shortcutTarget?.name }}
          </NText>
        </div>
        <div class="sc-shortcut-status" aria-live="polite">
          <NText depth="3" class="sc-shortcut-hint">
            Press a single key to assign it.
          </NText>
          <span class="sc-shortcut-current">{{ shortcutDisplay }}</span>
        </div>
      </div>
      <template #footer>
        <div class="sc-shortcut-footer">
          <NButton size="small" @click="clearShortcut">Clear</NButton>
          <NButton size="small" type="primary" @click="closeShortcutModal">
            Done
          </NButton>
        </div>
      </template>
    </NModal>
  </aside>
</template>

<style scoped>
.sc-sidebar {
  display: flex;
  flex-direction: column;
  border-left: 1px solid var(--cv-border, rgba(255, 255, 255, 0.12));
  background: var(--cv-card-bg, #1e1e2e);
  width: 340px;
  flex-shrink: 0;
  min-height: 0;
  overflow: hidden;
}

.sc-annotate {
  padding: 12px 16px 16px;
  display: flex;
  flex-direction: column;
  gap: 4px;
  flex: 1;
  min-height: 0;
  overflow-y: auto;
}

.sc-annotate-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.sc-code-search {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.sc-code-search-label {
  font-size: 12px;
  font-weight: 500;
  color: var(--cv-text-secondary, rgba(255, 255, 255, 0.5));
}

.sc-bulk-hint {
  margin-bottom: 6px;
  font-size: 12px;
}

.sc-code-list {
  display: block;
  overflow: hidden;
  border: 1px solid var(--cv-border, rgba(255, 255, 255, 0.1));
  border-radius: 6px;
}

.sc-code-row {
  display: grid;
  grid-template-columns: 42px minmax(0, 1fr) 44px;
  align-items: center;
  gap: 8px;
  min-height: 30px;
  padding: 4px 6px;
  font-size: 12px;
}

.sc-code-row-head {
  position: sticky;
  top: 0;
  z-index: 1;
  color: var(--cv-text-secondary, rgba(255, 255, 255, 0.5));
  background: var(--cv-card-bg, #1a1a2e);
  border-bottom: 1px solid var(--cv-border, rgba(255, 255, 255, 0.1));
}

.sc-code-button {
  width: 100%;
  border: 0;
  color: var(--cv-text, rgba(255, 255, 255, 0.88));
  background: transparent;
  text-align: left;
  cursor: pointer;
}

.sc-code-button:hover,
.sc-code-button.is-active {
  background: var(--cv-hover, rgba(255, 255, 255, 0.08));
}

.sc-code-button.is-active .sc-code-value {
  color: var(--cv-primary, #63e2b7);
  font-weight: 700;
}

.sc-code-name {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.sc-code-empty {
  padding: 14px 8px;
  color: var(--cv-text-secondary, rgba(255, 255, 255, 0.5));
  font-size: 12px;
  text-align: center;
}

.sc-shortcut-button {
  width: 38px;
  min-width: 38px;
  font-variant-numeric: tabular-nums;
}

.sc-draft-summary {
  margin-top: 4px;
}

.sc-actions {
  display: flex;
  gap: 8px;
  margin-top: 4px;
  flex-wrap: wrap;
}

.sc-detail-title {
  font-size: 12px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.4px;
}

.sc-detail-images {
  display: flex;
  gap: 6px;
  margin-top: 8px;
}

.sc-detail-img {
  border-radius: 4px;
  border: 1px solid var(--cv-border, rgba(255, 255, 255, 0.1));
  flex-shrink: 0;
}

.sc-detail-meta {
  margin-top: 10px;
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.sc-meta-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  font-size: 12px;
  padding: 2px 0;
}

.sc-meta-key {
  color: var(--cv-text-secondary, rgba(255, 255, 255, 0.45));
  min-width: 80px;
}

.sc-meta-val {
  color: var(--cv-text, #fff);
  text-align: right;
  font-variant-numeric: tabular-nums;
}

.sc-shortcut-modal {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.sc-shortcut-target {
  display: grid;
  grid-template-columns: auto auto minmax(0, 1fr);
  align-items: center;
  gap: 8px;
}

.sc-shortcut-target-name {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.sc-shortcut-status {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 10px;
  min-height: 88px;
  width: 100%;
  color: var(--cv-text, rgba(255, 255, 255, 0.88));
}

.sc-shortcut-hint {
  font-size: 12px;
}

.sc-shortcut-current {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 44px;
  min-height: 44px;
  padding: 0 10px;
  border-radius: 6px;
  background: var(--cv-hover, rgba(255, 255, 255, 0.06));
  font-size: 24px;
  font-weight: 700;
  line-height: 1;
  text-transform: uppercase;
}

.sc-shortcut-footer {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
}
</style>
