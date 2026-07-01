<script setup lang="ts">
import { computed, ref } from "vue";
import { useRoute, useRouter } from "vue-router";
import { NButton, NResult, NSpin, useThemeVars } from "naive-ui";
import InspectionQuad from "@/features/sc/presentation/components/PerspectiveInspectionQuad.vue";
import { FullScreenLayout } from "@/shared/components/full-screen-layout";
import type { ScSampleTableFilter, ScSampleTableSort } from "@/features/sc/domain/sampleTable";
import type { ScLegendSource } from "@/features/sc/domain/workbenchInteraction";
import type { ReticleMapOptions } from "@/features/sc/application/reticleMapOptions";
import {
  DEFAULT_RETICLE_MAP_OPTIONS,
  normalizeReticleMapOptions,
} from "@/features/sc/application/reticleMapOptions";
import { useGetInspectionApiV1ScInspectionsInspectionTimeWaferKeyGet } from "@/generated/orval/endpoints/api";
import type { InspectionSummaryItem } from "@/features/sc/domain/models";

const route = useRoute();
const router = useRouter();
const themeVars = useThemeVars();

const inspectionTime = computed(() => String(route.params.inspectionTime ?? ""));
const waferKey = computed(() => Number(route.params.waferKey));
const activeMapTab = ref<"wafer" | "die" | "reticle">("wafer");
const zoom = ref<{ x: number; y: number; w: number; h: number } | null>(null);
const selectedDefectIds = ref<number[]>([]);
const tableFilter = ref<ScSampleTableFilter>({});
const tableSort = ref<ScSampleTableSort | null>(null);
const legendGroupBy = ref<ScLegendSource | null>(null);
const reticleOptions = ref<ReticleMapOptions>(normalizeReticleMapOptions(DEFAULT_RETICLE_MAP_OPTIONS));

const inspectionQuery = useGetInspectionApiV1ScInspectionsInspectionTimeWaferKeyGet(
  inspectionTime,
  waferKey,
  {
    query: {
      enabled: computed(() => inspectionTime.value.length > 0 && Number.isFinite(waferKey.value)),
    },
  },
);
const inspectionFetching = computed(() => inspectionQuery.isFetching.value);

const inspectionItem = computed<InspectionSummaryItem | null>(() => {
  const payload = inspectionQuery.data.value?.data;
  if (!payload || "detail" in payload) return null;
  return payload;
});
const samplesError = computed(() => {
  if (!Number.isFinite(waferKey.value)) return "Invalid wafer key";
  if (inspectionQuery.error.value) return "Failed to load inspection";
  if (!inspectionFetching.value && !inspectionItem.value) return "Inspection not found";
  return null;
});
const waferGeometry = computed(() => {
  const row = inspectionItem.value;
  if (!row) return null;
  return {
    waferRadiusNm: 150_000_000,
    centerX: row.center_x ?? 0,
    centerY: row.center_y ?? 0,
    originX: row.origin_x ?? 0,
    originY: row.origin_y ?? 0,
    dieSizeX: row.die_size_x ?? 24000,
    dieSizeY: row.die_size_y ?? 24000,
  };
});
const pageTitle = computed(() => {
  const row = inspectionItem.value;
  if (!row) return "Inspection";
  return row.lot_id ? `${row.lot_id}#${row.wafer_id}` : `W${row.wafer_key}`;
});
const containerStyle = computed(() => ({
  "--cv-bg": themeVars.value.bodyColor,
  "--cv-card-bg": themeVars.value.cardColor,
  "--cv-text": themeVars.value.textColor1,
  "--cv-text-secondary": themeVars.value.textColor3,
  "--cv-border": themeVars.value.borderColor,
  "--cv-primary": themeVars.value.primaryColor,
}));

function setActiveMapTab(tab: "wafer" | "die" | "reticle"): void {
  activeMapTab.value = tab;
  zoom.value = null;
}

function setLegendGroupBy(groupBy: string | null): void {
  if (
    groupBy === "class" ||
    groupBy === "bin" ||
    groupBy === "annotation" ||
    groupBy === "prediction" ||
    groupBy === "final_class" ||
    groupBy === null
  ) {
    legendGroupBy.value = groupBy;
  }
}
</script>

<template>
  <FullScreenLayout>
    <div class="sc-inspection-page" :style="containerStyle">
      <div class="sc-inspection-toolbar">
        <div class="sc-inspection-title">{{ pageTitle }}</div>
        <div class="sc-inspection-actions">
          <NButton size="small" quaternary @click="router.push('/sc/preview')">Summary</NButton>
          <NButton size="small" quaternary @click="router.push('/sc/handbook')">Handbook</NButton>
        </div>
      </div>

      <div v-if="inspectionFetching && !inspectionItem" class="sc-inspection-state">
        <NSpin size="large" />
      </div>
      <div v-else-if="samplesError" class="sc-inspection-state">
        <NResult status="error" :title="samplesError" />
      </div>
      <InspectionQuad
        v-else
        :samples-error="null"
        :inspection-item="inspectionItem ?? undefined"
        :inspection-time="inspectionTime"
        :wafer-key="waferKey"
        :active-map-tab="activeMapTab"
        :wafer-geometry="waferGeometry"
        :reticle-x-die-count="reticleOptions.xDieCount"
        :reticle-y-die-count="reticleOptions.yDieCount"
        :reticle-die-size-x="inspectionItem?.die_size_x ?? 100000"
        :reticle-die-size-y="inspectionItem?.die_size_y ?? 100000"
        :reticle-options="reticleOptions"
        :zoom="zoom"
        :gallery-selected-defect-ids="selectedDefectIds"
        :table-filter="tableFilter"
        :table-sort="tableSort"
        :legend-group-by="legendGroupBy"
        @update:active-map-tab="setActiveMapTab"
        @update:reticle-options="reticleOptions = $event"
        @select-points="({ ids }) => (selectedDefectIds = ids)"
        @zoom-in="zoom = $event"
        @table-filter-change="tableFilter = $event"
        @table-sort-change="tableSort = $event"
        @table-selection-change="selectedDefectIds = $event"
        @legend-group-change="setLegendGroupBy"
        @retry="inspectionQuery.refetch()"
        @select-samples="(ids) => (selectedDefectIds = ids.map(Number))"
      />
    </div>
  </FullScreenLayout>
</template>

<style scoped>
.sc-inspection-page {
  display: flex;
  flex-direction: column;
  flex: 1;
  min-height: 0;
  overflow: hidden;
  padding: 12px 16px;
  background: var(--cv-bg, #0f0f1a);
  color: var(--cv-text, #fff);
}

.sc-inspection-toolbar {
  display: flex;
  flex: none;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  min-height: 34px;
  padding: 0 4px 8px;
  border-bottom: 1px solid var(--cv-border, rgba(255, 255, 255, 0.1));
}

.sc-inspection-title {
  min-width: 0;
  overflow: hidden;
  color: var(--cv-text, #fff);
  font-size: 14px;
  font-weight: 600;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.sc-inspection-actions {
  display: flex;
  flex: none;
  align-items: center;
  gap: 6px;
}

.sc-inspection-state {
  display: flex;
  flex: 1;
  min-height: 0;
  align-items: center;
  justify-content: center;
}
</style>
