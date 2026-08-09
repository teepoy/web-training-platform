<script setup lang="ts">
import { computed, ref } from "vue";
import { useRoute, useRouter } from "vue-router";
import { NButton, NResult, NSpin, useMessage, useThemeVars } from "naive-ui";
import InspectionQuad from "@/features/sc/presentation/components/InspectionQuad.vue";
import { FullScreenLayout } from "@/shared/components/full-screen-layout";
import { useGetInspectionApiV1ScInspectionsInspectionTimeWaferKeyGet } from "@/generated/orval/endpoints/api";
import type {
  InspectionSummaryItem,
  ScImportPayload,
  ScImportResponse,
} from "@/features/sc/domain/models";
import { streamApiSse } from "@/shared/api/sse";
import { toUserMessage } from "@/shared/api";

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
const isImporting = ref(false);
const importedDatasetId = ref<string | null>(null);
const globalFilterTriggerTarget = ref<HTMLElement | null>(null);

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
  const payload = inspectionQuery.data.value;
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
  } catch (error) {
    message.error(toUserMessage(error, "Import failed"));
  } finally {
    isImporting.value = false;
  }
}
</script>

<template>
  <FullScreenLayout>
    <div class="sc-inspection-page" :style="containerStyle">
      <div class="sc-inspection-toolbar">
        <div class="sc-inspection-heading">
          <div class="sc-inspection-title">{{ pageTitle }}</div>
          <div
            ref="globalFilterTriggerTarget"
            id="sc-inspection-global-filter-action"
            class="sc-inspection-global-filter-action"
          />
        </div>
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
        :inspection-time="inspectionTime"
        :wafer-key="waferKey"
        :wafer-geometry="waferGeometry"
        :global-filter-trigger-target="globalFilterTriggerTarget ?? undefined"
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

.sc-inspection-heading {
  display: flex;
  min-width: 0;
  align-items: center;
  gap: 6px;
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

.sc-inspection-global-filter-action {
  display: flex;
  flex: none;
  align-items: center;
}

.sc-inspection-state {
  display: flex;
  flex: 1;
  min-height: 0;
  align-items: center;
  justify-content: center;
}
</style>
