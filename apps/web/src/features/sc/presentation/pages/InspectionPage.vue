<script setup lang="ts">
import { computed, ref } from "vue";
import { useRoute, useRouter } from "vue-router";
import { NButton, NResult, NSpin, useMessage, useThemeVars } from "naive-ui";
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
import type {
  InspectionSummaryItem,
  ScImportPayload,
  ScImportResponse,
} from "@/features/sc/domain/models";
import { streamApiSse } from "@/shared/api/sse";

function isInspectionSummaryItem(payload: unknown): payload is InspectionSummaryItem {
  return (
    !!payload &&
    typeof payload === "object" &&
    "inspection_time" in payload &&
    "wafer_key" in payload
  );
}

const route = useRoute();
const router = useRouter();
const themeVars = useThemeVars();
const message = useMessage();

const inspectionTime = computed(() => String(route.params.inspectionTime ?? ""));
const waferKey = computed(() => Number(route.params.waferKey));
const activeMapTab = ref<"wafer" | "die" | "reticle">("wafer");
const zoom = ref<{ x: number; y: number; w: number; h: number } | null>(null);
const selectedGalleryDefectIds = ref<number[]>([]);
const tableFilter = ref<ScSampleTableFilter>({});
const tableSort = ref<ScSampleTableSort | null>(null);
const legendGroupBy = ref<ScLegendSource | null>(null);
const reticleOptions = ref<ReticleMapOptions>(
  normalizeReticleMapOptions(DEFAULT_RETICLE_MAP_OPTIONS),
);
const isImporting = ref(false);
const importedDatasetId = ref<string | null>(null);

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
  return isInspectionSummaryItem(payload) ? payload : null;
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

function sanitizeInspectionTime(value: string): string {
  return value.replace(/[\s:]/g, "-");
}

function importDatasetName(item: InspectionSummaryItem): string {
  return `Patch_${item.lot_id}_${item.wafer_id}_${sanitizeInspectionTime(item.inspection_time)}`;
}

async function startReclassifyImport(): Promise<void> {
  const item = inspectionItem.value;
  if (!item || isImporting.value) return;
  isImporting.value = true;
  try {
    const req: ScImportPayload = {
      source_inspection_time: item.inspection_time,
      source_wafer_key: item.wafer_key,
      dataset_name: importDatasetName(item),
      storage_mode: "file_shard_sparse",
    };
    const dataEvent = await streamApiSse("/sc/import/stream", {
      method: "POST",
      body: req,
    });
    const payload = dataEvent?.payload ?? {};
    const resp: ScImportResponse = {
      status: typeof payload.status === "string" ? payload.status : "failed",
      dataset_id: typeof payload.dataset_id === "string" ? payload.dataset_id : undefined,
      imported_count: typeof payload.imported_count === "number" ? payload.imported_count : 0,
      error: typeof payload.error === "string" ? payload.error : null,
    };
    if (resp.status === "completed" && resp.dataset_id) {
      importedDatasetId.value = resp.dataset_id;
      message.success(`Import complete: ${resp.imported_count ?? 0} samples imported`);
      return;
    }
    message.error(resp.error || "Import failed");
  } catch (err) {
    message.error(err instanceof Error ? err.message : "Import failed");
  } finally {
    isImporting.value = false;
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
          <NButton
            v-if="!importedDatasetId"
            size="small"
            type="primary"
            :loading="isImporting"
            :disabled="!inspectionItem"
            @click="startReclassifyImport"
          >
            Reclassify
          </NButton>
          <NButton
            v-else
            tag="a"
            size="small"
            type="primary"
            target="_blank"
            :href="`/datasets/${importedDatasetId}/sc/classify`"
          >
            Open Dataset
          </NButton>
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
        :selected-gallery-defect-ids="selectedGalleryDefectIds"
        :table-filter="tableFilter"
        :table-sort="tableSort"
        :legend-group-by="legendGroupBy"
        @update:active-map-tab="setActiveMapTab"
        @update:reticle-options="reticleOptions = $event"
        @zoom-in="zoom = $event"
        @table-filter-change="tableFilter = $event"
        @table-sort-change="tableSort = $event"
        @table-selection-change="selectedGalleryDefectIds = $event"
        @legend-group-change="setLegendGroupBy"
        @retry="inspectionQuery.refetch()"
        @select-samples="(ids) => (selectedGalleryDefectIds = ids.map(Number))"
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
