<script setup lang="ts">
import { ref } from "vue";
import {
  NButton,
  NCard,
  NDataTable,
  NResult,
  NSelect,
  type DataTableColumns,
} from "naive-ui";
import { SampleBrowser } from "@platform/web-ui";
import type { PredictionJob } from "../../../types";
import { injectClassifyPage } from "../composables/useClassifyPage";

const page = injectClassifyPage();
</script>

<template>
  <!-- Sparse dataset: no per-sample browsing or annotation -->
  <n-result
    v-if="page.isSparse.value"
    status="info"
    title="Sparse Dataset"
    description="Per-sample browsing and annotation are not available for file-backed sparse datasets. Use the prediction and training workflows above."
    style="flex: 1; align-self: center"
  />

  <template v-else>
    <div
      :ref="(el: any) => (page.browserShellRef.value = el)"
      class="classify-browser-shell"
      tabindex="-1"
      @keydown="page.onKeyDown"
    >
      <SampleBrowser
        :ref="(el: any) => (page.gridRef.value = el)"
        :items="page.filteredBrowserItems.value"
        :total-count="page.activeTotalCount.value"
        :thumb-size="page.prefs.thumbSize"
        :layout="page.prefs.layout"
        :is-loading="page.activeGridLoading.value"
        :selection-enabled="true"
        :show-checkboxes="true"
        :show-label-rail="true"
        :show-bottom-bar="true"
        activation-mode="select"
        @select="page.onBrowserSelect"
        @load-more="page.onGridLoadMore"
      >
        <template #label-rail>
          <div class="classify-label-panel">
            <input
              v-model="page.labelSearch.value"
              class="classify-label-search"
              placeholder="Search labels..."
              @keydown.stop
            />
            <div class="classify-label-list">
              <div
                v-for="(label, idx) in page.filteredLabels.value"
                :key="label"
                class="classify-label-item"
                @click="page.applyLabelToSelection(label)"
                :title="label"
              >
                <span
                  class="classify-label-dot"
                  :style="{ background: page.labelColor(label) }"
                />
                <span class="classify-label-name">{{ label }}</span>
                <span v-if="idx < 9" class="classify-label-shortcut">{{
                  idx + 1
                }}</span>
              </div>
            </div>
            <button
              v-if="!page.isReviewMode.value && !page.isSparse.value"
              class="classify-label-add"
              @click="page.showAddLabelModal.value = true"
            >
              + Add label
            </button>
          </div>
        </template>
        <template #bar-left>
          <template v-if="page.isReviewMode.value">
            <n-button
              size="tiny"
              :loading="page.syncCollectionMutation.isPending.value"
              :disabled="page.isSparse.value"
              @click="page.syncCollectionToLs"
            >
              Sync to LS
            </n-button>
            <n-button size="tiny" @click="page.resetReviewEdits">
              Reset Edits
            </n-button>
            <n-button size="tiny" @click="page.clearPredictionReview">
              Back to Annotation
            </n-button>
          </template>
          <template v-else>
            <n-select
              v-model:value="page.labelFilter.value"
              :options="page.filterOptions.value"
              placeholder="Filter by label"
              size="tiny"
              clearable
              style="width: 160px"
            />
            <n-select
              v-model:value="page.orderBy.value"
              :options="page.orderOptions"
              size="tiny"
              style="width: 130px"
            />
          </template>
        </template>
        <template #bar-right>
          <button
            class="classify-submit-btn"
            :disabled="
              page.isSubmitting.value || page.browserSubmitCount.value === 0
            "
            @click="page.submitFromGrid"
          >
            {{
              page.isSubmitting.value
                ? "Submitting..."
                : `Submit ${page.browserSubmitCount.value}`
            }}
          </button>
        </template>
      </SampleBrowser>
    </div>

    <component
      :is="page.ClassifySidebar"
      :panels="page.mergedPanels.value"
      :context="page.pageDashboard"
      :collapsed="page.prefs.sidebarCollapsed"
      @update:collapsed="page.prefs.setSidebarCollapsed"
    />
  </template>
</template>

<style scoped>
.classify-browser-shell {
  flex: 1;
  min-width: 0;
  min-height: 0;
  outline: none;
}

.classify-label-panel {
  display: flex;
  flex-direction: column;
  width: 100%;
  height: 100%;
}

.classify-label-search {
  margin: 8px;
  padding: 6px 8px;
  border: 1px solid var(--cv-border, rgba(255, 255, 255, 0.12));
  border-radius: 4px;
  background: transparent;
  color: var(--cv-text, #fff);
  font-size: 12px;
  outline: none;
}

.classify-label-search::placeholder {
  color: var(--cv-text-disabled, rgba(255, 255, 255, 0.3));
}

.classify-label-list {
  flex: 1;
  overflow-y: auto;
  padding: 0 4px;
}

.classify-label-item {
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

.classify-label-item:hover {
  background: var(--cv-hover, rgba(255, 255, 255, 0.08));
}

.classify-label-dot {
  width: 10px;
  height: 10px;
  border-radius: 50%;
  flex-shrink: 0;
}

.classify-label-name {
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.classify-label-shortcut {
  font-size: 10px;
  color: var(--cv-text-disabled, rgba(255, 255, 255, 0.3));
  flex-shrink: 0;
}

.classify-label-add {
  margin: 4px 8px 8px;
  padding: 6px;
  border: 1px dashed var(--cv-border, rgba(255, 255, 255, 0.12));
  border-radius: 4px;
  background: transparent;
  color: var(--cv-text-secondary, rgba(255, 255, 255, 0.5));
  cursor: pointer;
  font-size: 12px;
}

.classify-label-add:hover {
  border-color: var(--cv-primary, #4098fc);
  color: var(--cv-primary, #4098fc);
}

.classify-submit-btn {
  padding: 6px 16px;
  border: none;
  border-radius: 4px;
  background: var(--cv-primary, #4098fc);
  color: white;
  font-size: 12px;
  font-weight: 600;
  cursor: pointer;
}

.classify-submit-btn:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}

.classify-submit-btn:not(:disabled):hover {
  background: var(--cv-primary-hover, #3080e0);
}
</style>
