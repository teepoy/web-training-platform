<script setup lang="ts">
import { computed, onMounted } from "vue";
import { useRoute } from "vue-router";
import {
  NInput,
  NInputNumber,
  NButton,
  NDataTable,
  NDatePicker,
  NModal,
  NProgress,
  NSelect,
  NSpin,
  NResult,
  NSpace,
  NText,
  useThemeVars,
} from "naive-ui";
import InspectionQuad from "@/features/sc/presentation/components/InspectionQuad.vue";
import { FullScreenLayout } from "@/shared/components/full-screen-layout";
import { usePreviewPage } from "@/features/sc/application/usePreviewPage";

const page = usePreviewPage();
const route = useRoute();
const themeVars = useThemeVars();

onMounted(async () => {
  const { inspectionTime, waferKey } = route.params;
  if (!inspectionTime || !waferKey) return;

  const inspDt = new Date(decodeURIComponent(inspectionTime as string));
  const pad = (n: number) => String(n).padStart(2, "0");
  const fmtTs = (d: Date) =>
    `${d.getUTCFullYear()}-${pad(d.getUTCMonth() + 1)}-${pad(d.getUTCDate())} ${pad(d.getUTCHours())}:${pad(d.getUTCMinutes())}:${pad(d.getUTCSeconds())}`;

  const dayBefore = new Date(inspDt.getTime() - 86400000);
  const dayAfter = new Date(inspDt.getTime() + 86400000);
  page.dateRange.value = [dayBefore.getTime(), dayAfter.getTime()];

  await page.searchInspections();

  const waferKeyNum = Number(waferKey);
  const expectedTimeStr = fmtTs(inspDt);
  const row = page.summaries.value.find(
    (r) => r.inspection_time === expectedTimeStr && r.wafer_key === waferKeyNum,
  );
  if (row) {
    page.openInspectionTab(row);
  }
});

const containerStyle = computed(() => ({
  "--cv-bg": themeVars.value.bodyColor,
  "--cv-card-bg": themeVars.value.cardColor,
  "--cv-text": themeVars.value.textColor1,
  "--cv-text-secondary": themeVars.value.textColor3,
  "--cv-text-disabled": themeVars.value.textColorDisabled,
  "--cv-border": themeVars.value.borderColor,
  "--cv-primary": themeVars.value.primaryColor,
  "--cv-primary-hover": themeVars.value.primaryColorHover,
  "--cv-hover": themeVars.value.hoverColor,
  "--cv-divider": themeVars.value.dividerColor,
}));

function rowKey(row: Parameters<typeof page.rowKey>[0]): string {
  return page.rowKey(row);
}

function rowProps(row: Parameters<typeof page.rowProps>[0]): Record<string, unknown> {
  return page.rowProps(row);
}

function openClassify(url: string) {
  window.open(url, '_blank');
}
</script>

<template>
  <FullScreenLayout>
  <div class="sc-preview" :style="containerStyle">
    <div class="sc-preview-body">
      <!-- State views (no tabs) -->
      <template v-if="page.tabs.value.length === 0">
        <div class="sc-preview-search-bar">
          <NSpace align="center" :wrap="false">
            <NDatePicker v-model:value="page.dateRange.value" type="daterange" clearable style="width: 280px" size="small" />
            <NButton type="primary" :disabled="page.dateRange.value === null" :loading="page.summariesLoading.value" @click="page.searchInspections()" size="small">Search</NButton>
          </NSpace>
        </div>
        <div v-if="page.summariesLoading.value && page.summaries.value.length === 0" class="sc-preview-state">
          <NSpin size="medium">
            <template #description>Loading inspections...</template>
          </NSpin>
        </div>

        <div v-else-if="page.summariesError.value" class="sc-preview-state">
          <NResult
            status="error"
            :title="page.summariesError.value"
            description="Failed to load inspection summaries"
          >
            <template #footer>
              <NButton @click="page.searchInspections()">Retry</NButton>
            </template>
          </NResult>
        </div>

        <div v-else-if="page.summariesEmpty.value" class="sc-preview-state">
          <NResult
            status="info"
            title="No inspections found"
            description="Try a different time range"
          />
        </div>

        <div v-else class="sc-preview-state">
          <NResult
            status="info"
            title="Enter a time range to search"
            description="Search for inspection summaries by start and end time"
          />
        </div>
      </template>

      <!-- Tabs view -->
      <template v-else>
        <div class="sc-preview-tab-bar">
          <div class="sc-preview-tabs">
            <button
              v-for="tab in page.tabs.value"
              :key="tab.id"
              class="sc-preview-tab"
              :class="{ active: tab.id === page.activeTabId.value }"
              @click="page.activeTabId.value = tab.id"
            >
              {{ tab.label }}
              <span class="sc-preview-tab-close" @click.stop="page.closeTab(tab.id)">x</span>
            </button>
            <button class="sc-preview-tab-add" @click="page.createSummaryTab()" title="New Summary tab">+</button>
          </div>
          <div class="sc-preview-toolbar">
            <NButton
              v-if="page.activeTab.value?.type === 'inspection' && page.activeTab.value.inspectionItem"
              size="small"
              type="primary"
              :loading="page.isImporting.value"
              @click="page.activeTab.value.inspectionItem && page.startImportDirectly(page.activeTab.value.inspectionItem)"
            >
              Import as Dataset
            </NButton>
          </div>
        </div>

        <div class="sc-preview-tab-content">
          <!-- Summary tab -->
          <div v-if="page.activeTab.value?.type === 'summary'" class="sc-preview-tab-summary">
            <div class="sc-preview-search-bar">
              <NSpace align="center" :wrap="false">
                <NDatePicker v-model:value="page.dateRange.value" type="daterange" clearable style="width: 280px" size="small" />
                <NButton type="primary" :disabled="page.dateRange.value === null" :loading="page.summariesLoading.value" @click="page.searchInspections()" size="small">Search</NButton>
            <NButton size="small" :disabled="!page.datasetId.value.trim()" @click="openClassify(page.classifyHref.value)">Classify</NButton>
              </NSpace>
            </div>
            <div class="sc-preview-table-wrapper">
              <NDataTable
                :columns="page.inspectionColumns"
                :data="page.summaries.value"
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

          <!-- Inspection tab -->
          <InspectionQuad
            v-else-if="page.activeTab.value?.type === 'inspection'"
            :key="page.activeTabId.value ?? undefined"
            :samples="page.activeTab.value.patchSamples"
            :samples-total="page.activeTab.value.inspectionItem?.defects ?? page.activeTab.value.samplesTotal"
            :samples-loading="page.activeTab.value.samplesLoading"
            :samples-error="page.activeTab.value.samplesError"
            :inspection-item="page.activeTab.value.inspectionItem"
            :inspection-time="page.activeTab.value.inspectionTime"
            :wafer-key="page.activeTab.value.waferKey"
            :review-samples="page.activeTab.value.reviewSamples"
            :review-loading="page.activeTab.value.reviewLoading"
            :review-error="page.activeTab.value.reviewError"
            :map-loading="page.activeTab.value.mapLoading"
            :map-error="page.activeTab.value.mapError"
            :active-map-tab="page.activeTab.value.activeMapTab"
            :wafer-geometry="page.activeTab.value.waferGeometry"
            :wafer-display="page.activeTab.value.waferDisplay"
            :die-display="page.activeTab.value.dieDisplay"
            :reticle-display="page.activeTab.value.reticleDisplay"
            :full-wafer-display="page.activeTab.value.fullWaferDisplay"
            :full-die-display="page.activeTab.value.fullDieDisplay"
            :full-reticle-display="page.activeTab.value.fullReticleDisplay"
            :class-list="page.activeTab.value.classList"
            :reticle-x-die-count="page.activeTab.value.reticleXDieCount"
            :reticle-y-die-count="page.activeTab.value.reticleYDieCount"
            :reticle-die-size-x="page.activeTab.value.reticleDieSizeX"
            :reticle-die-size-y="page.activeTab.value.reticleDieSizeY"
            :reticle-options="page.activeTab.value.reticleOptions"
            :zoom="page.activeTab.value.zoom"
            @update:active-map-tab="(v: 'wafer' | 'die' | 'reticle') => page.activeTab.value && page.setMapTab(page.activeTab.value.id, v)"
            @update:reticle-options="(v) => page.activeTab.value && page.updateReticleOptions(page.activeTab.value.id, v)"
            @zoom-in="(vp) => page.activeTab.value && page.setZoom(page.activeTab.value.id, vp)"
            @retry="page.activeTab.value && page.fetchPreviewDataForTab(page.activeTab.value)"
          />
        </div>
      </template>
    </div>
  </div>
  </FullScreenLayout>

  <!-- Import Modal -->
  <NModal
    v-model:show="page.showImportModal.value"
    preset="card"
    title="Import from SC Upstream"
    style="width: 520px;"
  >
    <div class="sc-import-form">
      <NInput
        v-model:value="page.importSourceInspectionTime.value"
        placeholder="Inspection Time"
        :disabled="page.isImporting.value"
      />
      <NInputNumber
        v-model:value="page.importSourceWaferKey.value"
        placeholder="Source Wafer Key"
        :disabled="page.isImporting.value"
      />
      <NInput
        v-model:value="page.importDatasetName.value"
        placeholder="My SC Dataset"
        :disabled="page.isImporting.value"
      />
      <NSelect
        v-model:value="page.importStorageMode.value"
        :options="page.storageModeOptions"
        :disabled="page.isImporting.value"
      />
      <div v-if="page.isImporting.value" class="sc-import-progress">
        <NProgress
          type="line"
          :percentage="
            page.importProgress.value.remaining_count
              ? Math.round(
                  ((page.importProgress.value.imported_count ?? 0) /
                    ((page.importProgress.value.imported_count ?? 0) +
                      (page.importProgress.value.remaining_count ?? 0))) *
                    100,
                )
              : 0
          "
          :indicator-placement="'inside'"
        />
        <NText depth="3">
          Imported {{ page.importProgress.value.imported_count }} of
          {{ (page.importProgress.value.imported_count ?? 0) + (page.importProgress.value.remaining_count ?? 0) }}
        </NText>
      </div>
      <div v-if="page.importError.value" class="sc-import-error">
        <NText type="error">{{ page.importError.value }}</NText>
      </div>
    </div>
    <template #footer>
      <NButton @click="page.showImportModal.value = false" :disabled="page.isImporting.value">
        Cancel
      </NButton>
      <NButton
        type="primary"
        :loading="page.isImporting.value"
        :disabled="!page.importSourceInspectionTime.value.trim() || !page.importDatasetName.value.trim()"
        @click="page.handleImport()"
      >
        Start Import
      </NButton>
    </template>
  </NModal>
</template>

<style scoped>
.sc-preview {
  display: flex;
  flex-direction: column;
  flex: 1;
  min-height: 0;
  overflow: hidden;
  padding: 12px 16px;
  background: var(--cv-bg, #0f0f1a);
  color: var(--cv-text, #fff);
}

.sc-preview-body {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.sc-preview-state {
  display: flex;
  align-items: center;
  justify-content: center;
  flex: 1;
  min-height: 320px;
}

/* Tab bar */
.sc-preview-tab-bar {
  display: flex;
  flex-shrink: 0;
  align-items: center;
  justify-content: space-between;
  gap: 2px;
  background: var(--cv-card-bg, #1a1a2e);
  border-bottom: 1px solid var(--cv-border, rgba(255, 255, 255, 0.1));
  padding: 0 4px;
}

.sc-preview-tabs {
  display: flex;
  align-items: center;
  min-width: 0;
  overflow: hidden;
}

.sc-preview-toolbar {
  display: flex;
  align-items: center;
  flex-shrink: 0;
  padding-left: 12px;
}

.sc-preview-tab {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 6px 12px;
  cursor: pointer;
  font-size: 13px;
  border: none;
  background: transparent;
  color: var(--cv-text-secondary, rgba(255, 255, 255, 0.6));
  border-bottom: 2px solid transparent;
  white-space: nowrap;
  transition: color 0.15s, background 0.15s;
  font-family: inherit;
}

.sc-preview-tab:hover {
  color: var(--cv-text, #fff);
  background: var(--cv-primary-8, rgba(76, 128, 240, 0.05));
}

.sc-preview-tab.active {
  color: var(--cv-primary, #4c80f0);
  border-bottom-color: var(--cv-primary, #4c80f0);
  background: var(--cv-primary-8, rgba(76, 128, 240, 0.08));
}

.sc-preview-tab-close {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 16px;
  height: 16px;
  border-radius: 3px;
  font-size: 13px;
  line-height: 1;
  cursor: pointer;
  transition: background 0.1s;
}

.sc-preview-tab-close:hover {
  background: rgba(255, 255, 255, 0.1);
}

.sc-preview-tab-add {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 28px;
  height: 28px;
  margin-left: 4px;
  border: 1px dashed var(--cv-border, rgba(255, 255, 255, 0.2));
  border-radius: 4px;
  background: transparent;
  color: var(--cv-text-secondary, rgba(255, 255, 255, 0.5));
  cursor: pointer;
  font-size: 16px;
  font-family: inherit;
  transition: color 0.15s, border-color 0.15s;
}

.sc-preview-tab-add:hover {
  color: var(--cv-primary, #4c80f0);
  border-color: var(--cv-primary, #4c80f0);
}

/* Tab content */
.sc-preview-tab-content {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.sc-preview-tab-summary {
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

.sc-import-form {
  display: flex;
  flex-direction: column;
  gap: 12px;
  padding: 8px 0;
}

.sc-import-progress {
  margin-top: 4px;
}

.sc-import-error {
  margin-top: 4px;
}
</style>
