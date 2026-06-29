<script setup lang="ts">
import { computed } from "vue";
import { NButton, useThemeVars } from "naive-ui";
import ScSummaryTab from "@/features/sc/presentation/components/ScSummaryTab.vue";
import { useRouter } from "vue-router";
import { FullScreenLayout } from "@/shared/components/full-screen-layout";
import { usePreviewPage } from "@/features/sc/application/usePreviewPage";
import type { InspectionSummaryItem } from "@/features/sc/domain/models";

const page = usePreviewPage();
const router = useRouter();
const themeVars = useThemeVars();

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

function openInspectionInNewTab(row: InspectionSummaryItem): void {
  page.lastOpenedSummaryKey.value = page.rowKey(row);
  const target = router.resolve({
    name: "sc-inspection",
    params: {
      inspectionTime: row.inspection_time,
      waferKey: String(row.wafer_key),
    },
  });
  window.open(target.href, "_blank", "noopener");
}

</script>

<template>
  <FullScreenLayout>
    <div class="sc-preview" :style="containerStyle">
      <div class="sc-preview-body">
        <div class="sc-preview-tab-bar">
          <div class="sc-preview-title">Summary</div>
          <div class="sc-preview-toolbar">
            <NButton size="small" quaternary @click="router.push('/sc/handbook')">
              Handbook
            </NButton>
          </div>
        </div>

        <div class="sc-preview-tab-content">
          <ScSummaryTab
            :date-range="page.dateRange.value"
            :summaries-loading="page.summariesLoading.value"
            :summaries-error="page.summariesError.value"
            :summaries-empty="page.summariesEmpty.value"
            :summaries="page.summaries.value"
            :inspection-columns="page.inspectionColumns.value"
            :last-opened-summary-key="page.lastOpenedSummaryKey.value"
            :last-opened-summary-label="page.lastOpenedSummaryLabel.value"
            :lot-id-filter="page.lotIdFilter.value"
            :eqp-id-filter="page.eqpIdFilter.value"
            :layer-id-filter="page.layerIdFilter.value"
            :device-filter="page.deviceFilter.value"
            @update:date-range="page.dateRange.value = $event"
            @update:lot-id-filter="page.lotIdFilter.value = $event"
            @update:eqp-id-filter="page.eqpIdFilter.value = $event"
            @update:layer-id-filter="page.layerIdFilter.value = $event"
            @update:device-filter="page.deviceFilter.value = $event"
            @search="page.searchInspections()"
            @row-click="openInspectionInNewTab"
          />
        </div>
      </div>
    </div>
  </FullScreenLayout>
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

.sc-preview-toolbar {
  display: flex;
  align-items: center;
  flex-shrink: 0;
  padding-left: 12px;
}

.sc-preview-title {
  min-width: 0;
  padding: 6px 8px;
  color: var(--cv-text, #fff);
  font-size: 13px;
  font-weight: 600;
}

.sc-preview-tab-content {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

</style>
