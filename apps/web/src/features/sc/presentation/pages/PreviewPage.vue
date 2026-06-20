<script setup lang="ts">
import { computed, onMounted, type Component } from "vue";
import { useRoute } from "vue-router";
import {
  NInput,
  NInputNumber,
  NButton,
  NModal,
  NProgress,
  NSelect,
  NText,
  useThemeVars,
} from "naive-ui";
import InspectionQuad from "@/features/sc/presentation/components/InspectionQuad.vue";
import ScSummaryTab from "@/features/sc/presentation/components/ScSummaryTab.vue";
import { useRouter } from "vue-router";
import { FullScreenLayout } from "@/shared/components/full-screen-layout";
import { usePreviewPage } from "@/features/sc/application/usePreviewPage";

const page = usePreviewPage();
const route = useRoute();
const router = useRouter();
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

const activeComponent = computed<Component>(() =>
  page.activeTab.value?.type === "inspection" ? InspectionQuad : ScSummaryTab,
);

const activeComponentProps = computed((): Record<string, unknown> => {
  const tab = page.activeTab.value;
  if (!tab) return {};
  if (tab.type === "summary") {
    return {
      dateRange: page.dateRange.value,
      summariesLoading: page.summariesLoading.value,
      summariesError: page.summariesError.value,
      summariesEmpty: page.summariesEmpty.value,
      summaries: page.summaries.value,
      inspectionColumns: page.inspectionColumns.value,
      lotIdFilter: page.lotIdFilter.value,
      eqpIdFilter: page.eqpIdFilter.value,
      layerIdFilter: page.layerIdFilter.value,
      deviceFilter: page.deviceFilter.value,
      "onUpdate:dateRange": (v: [number, number] | null) => { page.dateRange.value = v; },
      "onUpdate:lotIdFilter": (v: string) => { page.lotIdFilter.value = v; },
      "onUpdate:eqpIdFilter": (v: string) => { page.eqpIdFilter.value = v; },
      "onUpdate:layerIdFilter": (v: string) => { page.layerIdFilter.value = v; },
      "onUpdate:deviceFilter": (v: string) => { page.deviceFilter.value = v; },
      onSearch: () => page.searchInspections(),
      onRowClick: (row: Parameters<typeof page.openInspectionTab>[0]) => page.openInspectionTab(row),
    };
  }
  return {
    samples: tab.patchSamples,
    samplesTotal: tab.inspectionItem?.defects ?? tab.samplesTotal,
    samplesLoading: tab.samplesLoading,
    samplesError: tab.samplesError,
    inspectionItem: tab.inspectionItem,
    inspectionTime: tab.inspectionTime,
    waferKey: tab.waferKey,
    reviewSamples: tab.reviewSamples,
    reviewLoading: tab.reviewLoading,
    reviewError: tab.reviewError,
    mapLoading: tab.mapLoading,
    mapError: tab.mapError,
    activeMapTab: tab.activeMapTab,
    waferGeometry: tab.waferGeometry,
    waferDisplay: tab.waferDisplay,
    dieDisplay: tab.dieDisplay,
    reticleDisplay: tab.reticleDisplay,
    unzoomedWaferDisplay: tab.unzoomedWaferDisplay,
    unzoomedDieDisplay: tab.unzoomedDieDisplay,
    unzoomedReticleDisplay: tab.unzoomedReticleDisplay,
    legendGroups: tab.legendGroups,
    reticleXDieCount: tab.reticleXDieCount,
    reticleYDieCount: tab.reticleYDieCount,
    reticleDieSizeX: tab.reticleDieSizeX,
    reticleDieSizeY: tab.reticleDieSizeY,
    reticleOptions: tab.reticleOptions,
    zoom: tab.zoom,
    selectedDefectIds: tab.selectedDefectIds,
    tableFilter: tab.tableFilter,
    tableSort: tab.tableSort,
    "onUpdate:activeMapTab": (v: "wafer" | "die" | "reticle") => page.setMapTab(tab.id, v),
    "onUpdate:reticleOptions": (v: Parameters<typeof page.updateReticleOptions>[1]) => page.updateReticleOptions(tab.id, v),
    onZoomIn: (vp: Parameters<typeof page.setZoom>[1]) => page.setZoom(tab.id, vp),
    onTableSelectionChange: (ids: number[]) => page.setSelectedDefectIds(tab.id, ids),
    onTableFilterChange: (filter: Parameters<typeof page.handleTableFilterChange>[1]) => page.handleTableFilterChange(tab.id, filter),
    onTableSortChange: (sort: { field: string; direction: "asc" | "desc" | null }) => page.handleTableSortChange(tab.id, sort),
    onLegendGroupChange: (groupBy: string | null) => page.handleLegendGroupByChange(tab.id, groupBy),
    onRetry: () => page.fetchPreviewDataForTab(tab),
  };
});
</script>

<template>
  <FullScreenLayout>
  <div class="sc-preview" :style="containerStyle">
    <div class="sc-preview-body">
      <div class="sc-preview-tab-bar">
        <div class="sc-preview-tabs">
          <button
            v-for="tab in page.tabs.value"
            :key="tab.id"
            class="sc-preview-tab"
            :class="{ active: tab.id === page.activeTabId.value, pinned: tab.pinned }"
            @click="page.activeTabId.value = tab.id"
          >
            {{ tab.label }}
            <span
              v-if="!tab.pinned"
              class="sc-preview-tab-close"
              @click.stop="page.closeTab(tab.id)"
            >
              x
            </span>
          </button>
        </div>
        <div class="sc-preview-toolbar">
          <NButton
            size="small"
            quaternary
            @click="router.push('/sc/handbook')"
          >
            Handbook
          </NButton>
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
        <KeepAlive :max="3">
          <component
            :is="activeComponent"
            :key="page.activeTabId.value ?? 'summary'"
            v-bind="activeComponentProps"
          />
        </KeepAlive>
      </div>
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

.sc-preview-tab.pinned {
  padding-right: 14px;
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
