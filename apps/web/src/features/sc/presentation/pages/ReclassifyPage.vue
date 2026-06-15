<script setup lang="ts">
import { computed, onMounted, onBeforeUnmount, ref } from "vue";
import {
  NSpin,
  NEmpty,
  NResult,
  NSelect,
  NButton,
  NInputNumber,
  NText,
  NModal,
  NCheckbox,
  NTooltip,
  useThemeVars,
} from "naive-ui";
import { useRouter } from "vue-router";
import { FullScreenLayout } from "@/shared/components/full-screen-layout";
import { useReclassifyPage } from "../../application/useReclassifyPage";
import ScReclassifyBlinkVirtualTable from "../components/ScReclassifyBlinkVirtualTable.vue";
import InspectionQuad from "@/features/sc/presentation/components/InspectionQuad.vue";
import ReclassifyAnnotationSidebar from "../components/ReclassifyAnnotationSidebar.vue";
import ReclassifyTaskProgressModal from "../components/ReclassifyTaskProgressModal.vue";
import { create } from "@bufbuild/protobuf";
import type { ScBlinkImageUrls } from "@/features/sc/domain/models";
import {
  ScSampleItemSchema,
  ReviewImageSchema,
  type ScSampleItem,
} from "@/features/sc/generated/proto/sc/v1/sample_pb";
import type { ScSampleTableFilter } from "@/features/sc/domain/sampleTable";

const page = useReclassifyPage();
const themeVars = useThemeVars();
const router = useRouter();
const taskInsightVisible = ref(false);

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

function goBack() {
  router.back();
}

const selectedDraftCount = computed(() => {
  let count = 0;
  for (const id of page.selectedDefectIds.value) {
    if (page.annotationDraft.value[id]) count += 1;
  }
  return count;
});
const hasGlobalSampleTableFilter = computed(() => Object.keys(page.globalFilter.value).length > 0);

function clearSelectedDrafts(): void {
  if (selectedDraftCount.value === 0) return;
  const next = { ...page.annotationDraft.value };
  for (const id of page.selectedDefectIds.value) {
    delete next[id];
  }
  page.annotationDraft.value = next;
}

function applyAnnotationCode(code: string): void {
  if (page.selectedDefectIds.value.size === 0) return;
  for (const id of page.selectedDefectIds.value) {
    page.setAnnotationDraft(id, code);
  }
}

async function handleTrainAndPredictClick(): Promise<void> {
  await page.trainAndPredict();
  if (page.trainPredictTaskId.value) {
    taskInsightVisible.value = true;
  }
}

function onBlinkTableSelect(
  defectIds: string[],
  modifiers: {
    shift: boolean;
    ctrl: boolean;
    meta: boolean;
    selectionMode?: import("../../application/useReclassifyPage").SelectionMode;
  },
): void {
  const mode: import("../../application/useReclassifyPage").SelectionMode =
    modifiers.selectionMode ?? (modifiers.ctrl || modifiers.meta ? "toggle" : "replace");
  page.selectDefectIds(defectIds, mode);
}

// ── Keyboard shortcuts: user-configured single keys apply annotation codes ─

function handleKeydown(e: KeyboardEvent): void {
  if (e.key === "Escape") {
    if (page.selectedDefectIds.value.size > 0) {
      page.clearSelection();
      return;
    }
  }

  const target = e.target as HTMLElement | null;
  if (target) {
    const tag = target.tagName.toLowerCase();
    if (tag === "input" || tag === "textarea" || tag === "select" || target.isContentEditable) {
      return;
    }
  }

  if (e.ctrlKey || e.metaKey || e.altKey || e.key.length !== 1) return;
  const code = page.shortcutCodeByKey.value[e.key.toLowerCase()];
  if (!code) return;
  if (page.selectedDefectIds.value.size === 0) return;
  e.preventDefault();
  applyAnnotationCode(code);
}

onMounted(() => document.addEventListener("keydown", handleKeydown));
onBeforeUnmount(() => document.removeEventListener("keydown", handleKeydown));

const blinkSamples = computed<ScSampleItem[]>(() =>
  page.filteredScSamples.value.map((s) => {
    const epochMs = Date.parse(s.inspectionTime);
    const inspectionTime = Number.isFinite(epochMs) ? BigInt(epochMs) : 0n;
    return create(ScSampleItemSchema, {
      inspectionTime,
      waferKey: s.waferKey,
      defectId: Number(s.defectId),
      reviewImages: s.reviewImageIds.map((imageId) =>
        create(ReviewImageSchema, {
          imageId,
          imageName: "",
          imageType: "",
        }),
      ),
      waferX: s.waferX,
      waferY: s.waferY,
      roughBin: s.roughBin,
      classNumber: s.classNumber,
    });
  }),
);

const blinkImageUrlsByDefectId = computed<Record<string, ScBlinkImageUrls>>(() => {
  const urlsByDefectId: Record<string, ScBlinkImageUrls> = {};
  for (const sample of page.scSamples.value) {
    const urls: ScBlinkImageUrls = {
      template: "",
      defective: "",
      difference: "",
      review: [],
    };
    for (const image of sample.images) {
      const role = image.role.toLowerCase();
      if (role.includes("template")) urls.template = image.url;
      else if (role.includes("defective")) urls.defective = image.url;
      else if (role.includes("difference")) urls.difference = image.url;
      else if (role === "review") urls.review.push(image.url);
    }
    urlsByDefectId[sample.defectId] = urls;
  }
  return urlsByDefectId;
});

/** Saved annotation labels keyed by defectId (matches BlinkTable lookup). */
const annotationLabelsByDefectId = computed<Record<string, string>>(() => {
  const map: Record<string, string> = {};
  for (const s of page.scSamples.value) {
    if (s.currentLabel && s.currentLabel !== "__unlabeled__") map[s.defectId] = s.currentLabel;
  }
  return map;
});

const hasLocalSampleTableFilter = computed(
  () => Object.keys(page.sampleTableFilter.value).length > 0,
);

function onSampleTableFilterChange(filter: ScSampleTableFilter): void {
  const local: ScSampleTableFilter = {};
  for (const [field, value] of Object.entries(filter)) {
    const globalValue = page.globalFilter.value[field];
    if (JSON.stringify(value) !== JSON.stringify(globalValue)) {
      local[field] = value;
    }
  }
  page.sampleTableFilter.value = local;
}
</script>

<template>
  <FullScreenLayout>
    <div class="sc-classify-page" :style="containerStyle">
      <!-- Error state -->
      <NResult
        v-if="page.isError.value"
        status="error"
        :title="page.errorMessage.value"
        class="sc-state"
      >
        <template #footer>
          <NButton @click="goBack">Go Back</NButton>
        </template>
      </NResult>

      <!-- Loading state -->
      <div v-else-if="page.isLoading.value" class="sc-state">
        <NSpin size="large" />
      </div>

      <!-- Empty state -->
      <div
        v-else-if="
          !page.isBlinkLoading.value &&
          !page.isMapLoading.value &&
          page.scSamples.value.length === 0 &&
          Object.keys(page.globalFilter.value).length === 0
        "
        class="sc-state"
      >
        <NEmpty description="No samples available" />
      </div>

      <!-- Main content -->
      <template v-else>
        <!-- Header -->
        <div class="sc-header">
          <div class="sc-header-left">
            <NButton text size="small" @click="goBack">← Back</NButton>
            <NTooltip>
              <template #trigger>
                <NText depth="2" class="sc-dataset-name">
                  {{ page.dataset.value?.name ?? "Reclassify" }}
                </NText>
              </template>
              {{ page.dataset.value?.name ?? "Reclassify" }}
            </NTooltip>
          </div>
          <div class="sc-header-right">
            <NSelect
              v-model:value="page.selectedTrainerId.value"
              :options="page.trainerOptions.value"
              placeholder="Select trainer"
              size="small"
              :style="{ width: '160px' }"
            />
            <NButton
              size="small"
              type="primary"
              :disabled="
                !page.selectedTrainerId.value ||
                page.isTrainPredictRunning.value ||
                page.annotatedCount.value === 0
              "
              :loading="page.isTrainPredictRunning.value"
              @click="handleTrainAndPredictClick"
            >
              Train &amp; Predict
            </NButton>
            <NText v-if="page.trainPredictStatusMessage.value" depth="3" style="font-size: 11px">
              {{ page.trainPredictStatusMessage.value }}
            </NText>
            <NButton
              v-if="page.trainPredictTaskId.value"
              size="small"
              quaternary
              @click="taskInsightVisible = true"
            >
              View Task
            </NButton>
            <NButton size="small" type="primary" @click="page.showSamplingModal.value = true">
              Sampling
            </NButton>
            <NButton
              v-if="hasGlobalSampleTableFilter"
              size="small"
              quaternary
              @click="page.clearGlobalFilter"
            >
              Clear Global Filter
            </NButton>
            <NButton size="small" quaternary @click="router.push('/sc/handbook')">
              Handbook
            </NButton>
          </div>
        </div>

        <!-- Main area -->
        <div class="classify-layout">
          <InspectionQuad
            variant="reclassify"
            :dataset-id="page.datasetId.value"
            :samples="blinkSamples"
            :samples-total="page.plotPointTotal.value"
            :samples-loading="page.isBlinkLoading.value"
            :samples-error="page.samplesError.value"
            :inspection-time="page.inspectionContext.value?.inspectionTime ?? undefined"
            :wafer-key="
              page.inspectionContext.value?.waferKey
                ? Number(page.inspectionContext.value.waferKey)
                : undefined
            "
            :review-samples="page.reviewSamples.value"
            :review-loading="page.reviewLoading.value"
            :review-error="page.reviewError.value"
            :map-loading="page.isMapLoading.value"
            :map-error="page.reticleMapError.value"
            :map-stream-message="page.mapStreamMessage.value"
            :active-map-tab="page.activeMapTab.value"
            :wafer-geometry="page.waferGeometry.value"
            :wafer-display="page.waferDisplay.value"
            :die-display="page.dieDisplay.value"
            :reticle-display="page.reticleDisplay.value"
            :legend-groups="page.classList.value"
            :reticle-x-die-count="page.reticleXDieCount.value"
            :reticle-y-die-count="page.reticleYDieCount.value"
            :reticle-die-size-x="page.reticleDieSizeX.value"
            :reticle-die-size-y="page.reticleDieSizeY.value"
            :reticle-options="page.reticleOptions.value"
            :zoom="page.mapZoom.value"
            :selected-defect-ids="Array.from(page.sampleTableSelectedIds.value)"
            :table-filter="page.effectiveSampleTableFilter.value"
            :map-sample-filter="page.globalFilter.value"
            :global-filter-action-enabled="hasLocalSampleTableFilter"
            :legend-group-by="page.legendGroupBy.value"
            :legend-sources="['class', 'bin', 'annotation', 'prediction']"
            @update:active-map-tab="page.setActiveMapTab"
            @update:reticle-options="page.updateReticleOptions"
            @select-points="({ ids }) => page.handleBoxSelectionChange(ids)"
            @zoom-in="page.setMapZoom"
            @table-filter-change="onSampleTableFilterChange"
            @table-apply-filter-as-global="page.applySampleTableFilterAsGlobal"
            @table-sort-change="() => {}"
            @table-selection-change="page.setSampleTableSelectedIds"
            @table-apply-selection="page.filterBlinkTableSamples"
            @legend-group-change="page.handleLegendGroupByChange"
            @retry="() => {}"
          >
            <template #blink>
              <ScReclassifyBlinkVirtualTable
                :samples="blinkSamples"
                :image-urls-by-defect-id="blinkImageUrlsByDefectId"
                :initial-blink-enabled="true"
                :selected-defect-ids="page.selectedDefectIds.value"
                :prediction-labels="page.predictionLabels.value"
                :prediction-confidences="page.predictionConfidences.value"
                :annotation-labels="annotationLabelsByDefectId"
                :annotation-drafts="page.annotationDraft.value"
                :has-next-page="page.hasMoreSamples.value"
                :is-fetching-next-page="page.isFetchingMoreSamples.value"
                :inspection-time="page.inspectionContext.value?.inspectionTime ?? ''"
                :review-samples="page.reviewSamples.value"
                :review-loading="page.reviewLoading.value"
                :review-error="page.reviewError.value"
                @select-samples="onBlinkTableSelect"
                :on-load-more="page.fetchMoreSamples"
              />
            </template>
            <template #annotation>
              <ReclassifyAnnotationSidebar
                :selected-count="page.selectedCount.value"
                :code-labels="page.codeLabels.value"
                :annotation-draft="page.annotationDraft.value"
                :draft-count="page.draftCount.value"
                :selected-draft-count="selectedDraftCount"
                :is-submitting="page.isSubmitting.value"
                @apply-code="applyAnnotationCode"
                @set-shortcut="page.setLabelShortcut"
                @submit="page.submitAnnotations"
                @clear-drafts="page.clearDrafts"
                @clear-selected-drafts="clearSelectedDrafts"
              />
            </template>
          </InspectionQuad>
        </div>
      </template>
    </div>

    <!-- Sampling modal -->
    <NModal
      v-model:show="page.showSamplingModal.value"
      preset="card"
      title="Random Sampling"
      :style="{ width: '380px' }"
    >
      <div class="sc-sampling-form">
        <div class="sc-sampling-field">
          <NText depth="2" style="font-size: 13px">Sample Count</NText>
          <NInputNumber
            v-model:value="page.samplingCount.value"
            :min="1"
            :max="page.samplingAvailableCount.value"
            style="width: 100%"
          />
          <NText depth="3" style="font-size: 11px; margin-top: 4px">
            Total available: {{ page.samplingAvailableCount.value }} samples
          </NText>
        </div>
        <NCheckbox v-model:checked="page.assignDefaultDraftLabel.value" style="margin-top: 12px">
          Assign draft label to sampled
        </NCheckbox>
      </div>
      <template #footer>
        <div class="sc-sampling-footer">
          <NButton @click="page.showSamplingModal.value = false">Cancel</NButton>
          <NButton type="primary" @click="page.applySampling()">Confirm</NButton>
        </div>
      </template>
    </NModal>
    <ReclassifyTaskProgressModal
      v-model:show="taskInsightVisible"
      :training-job-id="page.trainPredictTaskId.value"
      :training-status="page.trainPredictTrainingStatus.value"
      :prediction-job-id="page.trainPredictPredictionJob.value?.id ?? null"
      :prediction-status="page.trainPredictPredictionStatus.value"
      :prediction-percent="page.trainPredictPredictionPercent.value"
      :prediction-progress-label="page.trainPredictPredictionProgressLabel.value"
      :prediction-processing="page.trainPredictPredictionProcessing.value"
    />
  </FullScreenLayout>
</template>

<style scoped>
/* ── Page skeleton (mirrors ClassifyView.vue) ──────── */
.sc-classify-page {
  display: flex;
  flex-direction: column;
  flex: 1;
  min-height: 0;
  gap: 12px;
  padding: 12px 16px;
  background: var(--cv-bg, #0f0f1a);
  color: var(--cv-text, #fff);
}

/* ── State overlays ────────────────────────────────── */
.sc-state {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 320px;
}

/* ── Header ────────────────────────────────────────── */
.sc-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 6px 0 10px;
  border-bottom: 1px solid var(--cv-border, rgba(255, 255, 255, 0.1));
  flex-shrink: 0;
}

.sc-header-left {
  display: flex;
  align-items: center;
  gap: 12px;
  min-width: 0;
}

.sc-header-right {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-shrink: 0;
}

.sc-dataset-name {
  display: block;
  max-width: min(36vw, 420px);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 15px;
  font-weight: 600;
}

/* ── Main layout (mirrors ClassifyBrowserArea.vue) ─── */
.classify-layout {
  display: flex;
  flex: 1;
  min-height: 0;
  overflow: hidden;
}

.classify-browser-shell {
  flex: 1;
  min-width: 0;
  min-height: 0;
  display: flex;
  flex-direction: column;
  outline: none;
}

.sc-tab-bar {
  display: flex;
  align-items: center;
  padding: 0 0 8px;
  flex-shrink: 0;
  gap: 10px;
}

.sc-filter-hint {
  font-size: 11px;
  color: var(--cv-text-secondary, rgba(255, 255, 255, 0.5));
  display: inline-flex;
  align-items: center;
  gap: 4px;
}

.sc-stream-hint {
  margin-left: auto;
  font-size: 11px;
}

.sc-map-progress {
  display: flex;
  align-items: center;
  gap: 10px;
  min-height: 24px;
  padding: 0 0 8px;
}

.sc-map-progress :deep(.n-progress) {
  width: 180px;
  flex: 0 0 180px;
}

.sc-map-progress-text {
  font-size: 11px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.sc-blink-spin {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-height: 0;
}

.sc-blink-spin :deep(.n-spin-container),
.sc-blink-spin :deep(.n-spin-content) {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-height: 0;
}

.sc-reticle-options {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
  padding: 0 0 8px;
  font-size: 11px;
  color: var(--cv-text-secondary, rgba(255, 255, 255, 0.55));
  flex-shrink: 0;
}

.sc-sampling-form {
  display: flex;
  flex-direction: column;
}

.sc-sampling-field {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.sc-sampling-footer {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
}
</style>
