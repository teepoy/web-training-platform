<script setup lang="ts">
import { computed, onMounted, onBeforeUnmount, provide, ref } from "vue";
import {
  NSpin,
  NEmpty,
  NResult,
  NSelect,
  NButton,
  NInputNumber,
  NText,
  NRadioGroup,
  NRadioButton,
  NModal,
  NCheckbox,
  NTooltip,
  NProgress,
  useThemeVars,
} from "naive-ui";
import { useRouter } from "vue-router";
import { FullScreenLayout } from "@/shared/components/full-screen-layout";
import TaskInsightModal, {
  TASK_INSIGHT_ORG_ID_KEY,
  TASK_INSIGHT_STREAM_KEY,
} from "@/shared/components/task-insight-modal";
import { useTaskStream } from "@/shared/composables/useTaskHandoff";
import { useOrgStore } from "@/features/auth/application/org";
import { useReclassifyPage } from "../../application/useReclassifyPage";
import ScReclassifyBlinkVirtualTable from "../components/ScReclassifyBlinkVirtualTable.vue";
import ScMapPanel from "@/features/sc/presentation/components/ScMapPanel.vue";
import ReclassifyAnnotationSidebar from "../components/ReclassifyAnnotationSidebar.vue";
import { create } from "@bufbuild/protobuf";
import type { ScBlinkImageUrls } from "@/features/sc/domain/models";
import {
  ScSampleItemSchema,
  ReviewImageSchema,
  type ScSampleItem,
} from "@/features/sc/generated/proto/sc/v1/sample_pb";
import type { ScBoxRegion, ScMapMode } from "@/features/sc/api/boxFilter";
import type { TaskTrackerSummaryResponse } from "@/generated/orval/models";
import { fetchScDatasetBoxFilter } from "@/features/sc/api/boxFilter";

const page = useReclassifyPage();
const themeVars = useThemeVars();
const router = useRouter();
const orgStore = useOrgStore();
const taskInsightVisible = ref(false);

provide(
  TASK_INSIGHT_ORG_ID_KEY,
  computed(() => orgStore.currentOrgId),
);
provide(TASK_INSIGHT_STREAM_KEY, useTaskStream);

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

/** Curried box-selection: bakes datasetId + reticleOptions, takes mode + region → defect IDs. */
async function queryBoxSelection(
  mode: ScMapMode,
  region: ScBoxRegion,
): Promise<number[]> {
  const result = await fetchScDatasetBoxFilter(
    page.datasetId.value,
    mode,
    region,
    page.reticleOptions.value,
  );
  return result.defect_ids.map(Number);
}

const selectedDraftCount = computed(() => {
  let count = 0;
  for (const id of page.selectedDefectIds.value) {
    if (page.annotationDraft.value[id]) count += 1;
  }
  return count;
});

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
    modifiers.selectionMode ??
    (modifiers.ctrl || modifiers.meta ? "toggle" : "replace");
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
    if (
      tag === "input" ||
      tag === "textarea" ||
      tag === "select" ||
      target.isContentEditable
    ) {
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

const blinkImageUrlsByDefectId = computed<Record<string, ScBlinkImageUrls>>(
  () => {
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
  },
);

/** Saved annotation labels keyed by defectId (matches BlinkTable lookup). */
const annotationLabelsByDefectId = computed<Record<string, string>>(() => {
  const map: Record<string, string> = {};
  for (const s of page.scSamples.value) {
    if (s.currentLabel && s.currentLabel !== "__unlabeled__")
      map[s.defectId] = s.currentLabel;
  }
  return map;
});

const activeTaskSummary = computed<TaskTrackerSummaryResponse | null>(() => {
  const taskId = page.trainPredictTaskId.value;
  if (!taskId) return null;
  const now = new Date().toISOString();
  return {
    id: taskId,
    task_kind: "training",
    execution_kind: "prefect",
    display_name: `Train & Predict ${taskId.slice(0, 8)}`,
    display_status: page.isTrainPredictRunning.value ? "running" : "pending",
    stage: "execution_flow",
    dataset_id: page.datasetId.value,
    model_id: null,
    trainer_id: page.selectedTrainerId.value,
    created_by: "",
    created_at: now,
    updated_at: now,
    prefect_state: null,
    work_pool_name: null,
    work_queue_name: null,
    queue_priority: null,
    queue_priority_label: "",
    queue_depth_ahead: null,
    capacity_status: "",
    pool_concurrency_limit: null,
    pool_slots_used: null,
  };
});

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
          page.scSamples.value.length === 0
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
              @click="page.trainAndPredict()"
            >
              Train &amp; Predict
            </NButton>
            <NText
              v-if="page.trainPredictStatusMessage.value"
              depth="3"
              style="font-size: 11px"
            >
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
            <NButton
              size="small"
              type="primary"
              @click="page.showSamplingModal.value = true"
            >
              Sampling
            </NButton>
            <NButton
              size="small"
              quaternary
              @click="router.push('/sc/handbook')"
            >
              Handbook
            </NButton>
          </div>
        </div>

        <!-- Main area: tabs left, annotation sidebar right -->
        <div class="classify-layout">
          <!-- Left: Tab container -->
          <div class="classify-browser-shell">
            <!-- Tab bar -->
            <div class="sc-tab-bar">
              <NRadioGroup v-model:value="page.activeTab.value" size="small">
                <NRadioButton value="blink">Blink Table</NRadioButton>
                <NRadioButton value="map">Map</NRadioButton>
              </NRadioGroup>
              <span
                v-if="page.activeFilterCount.value > 0"
                class="sc-filter-hint"
              >
                {{ page.activeFilterCount.value }} filter(s) active
                <NButton
                  text
                  size="tiny"
                  type="primary"
                  @click="page.clearMapFilter()"
                  >Clear</NButton
                >
              </span>
              <NText
                v-if="
                  page.activeTab.value === 'map' && page.mapStreamMessage.value
                "
                depth="3"
                class="sc-stream-hint"
              >
                {{ page.mapStreamMessage.value }}
              </NText>
            </div>
            <div
              v-if="page.activeTab.value === 'map' && page.isMapLoading.value"
              class="sc-map-progress"
            >
              <NProgress
                type="line"
                :percentage="100"
                :show-indicator="false"
                processing
              />
              <NText depth="3" class="sc-map-progress-text">
                {{ page.mapStreamMessage.value || "Loading map data..." }}
              </NText>
            </div>
            <NSpin
              :show="
                page.activeTab.value === 'blink'
                  ? page.isBlinkLoading.value
                  : page.isMapLoading.value
              "
              class="sc-blink-spin"
            >
              <!-- Blink table tab (default) -->
              <ScReclassifyBlinkVirtualTable
                v-if="page.activeTab.value === 'blink'"
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
                :inspection-time="
                  page.inspectionContext.value?.inspectionTime ?? ''
                "
                :review-samples="page.reviewSamples.value"
                :review-loading="page.reviewLoading.value"
                :review-error="page.reviewError.value"
                @select-samples="onBlinkTableSelect"
                :on-load-more="page.fetchMoreSamples"
              />
              <!-- Map panel (handles wafer/die/reticle internally) -->
              <ScMapPanel
                v-if="page.activeTab.value === 'map'"
                :active-map-tab="page.activeMapTab.value"
                :wafer-points="page.waferDisplay.value"
                :wafer-geometry="page.waferGeometry.value"
                :wafer-radius-nm="page.waferGeometry.value?.waferRadiusNm"
                :die-points="page.dieDisplay.value"
                :reticle-points="page.reticleDisplay.value"
                :reticle-x-die-count="page.reticleXDieCount.value"
                :reticle-y-die-count="page.reticleYDieCount.value"
                :reticle-die-size-x="page.reticleDieSizeX.value"
                :reticle-die-size-y="page.reticleDieSizeY.value"
                :reticle-options="page.reticleOptions.value"
                :legend-group-by="page.legendGroupBy.value ?? 'class'"
                :legend-groups="page.classList.value"
                :legend-sources="['class', 'bin', 'annotation', 'prediction']"
                :selected-ids="page.mapSelectedDefectIds.value"
                :highlight-defects="page.highlightDefects.value"
                :zoom="page.mapZoom.value"
                :query-box-selection="queryBoxSelection"
                @update:active-map-tab="page.setActiveMapTab"
                @update:reticle-options="page.updateReticleOptions"
                @select-points="({ ids }) => page.handleBoxSelectionChange(ids)"
                @zoom-in="page.setMapZoom"
                @filter-change="page.handleMapFilterChange"
                @selection-change="page.handleBoxSelectionChange"
                @update:legend-group-by="page.handleLegendGroupByChange"
                @retry="() => {}"
              />
            </NSpin>
          </div>

          <ReclassifyAnnotationSidebar
            :selected-count="page.selectedCount.value"
            :code-labels="page.codeLabels.value"
            :annotation-draft="page.annotationDraft.value"
            :draft-count="page.draftCount.value"
            :selected-draft-count="selectedDraftCount"
            :is-submitting="page.isSubmitting.value"
            :annotation-grid-items="page.annotationGridItems.value"
            :add-label-error="page.addLabelError.value"
            :is-adding-label="page.isAddingLabel.value"
            @add-label="page.addLabel"
            @apply-code="applyAnnotationCode"
            @set-shortcut="page.setLabelShortcut"
            @submit="page.submitAnnotations"
            @clear-drafts="page.clearDrafts"
            @clear-selected-drafts="clearSelectedDrafts"
          />
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
        <NCheckbox
          v-model:checked="page.assignDefaultDraftLabel.value"
          style="margin-top: 12px"
        >
          Assign default draft label (label 1) to all sampled data
        </NCheckbox>
      </div>
      <template #footer>
        <NButton @click="page.showSamplingModal.value = false">Cancel</NButton>
        <NButton type="primary" @click="page.applySampling()">Confirm</NButton>
      </template>
    </NModal>
    <TaskInsightModal
      v-model:show="taskInsightVisible"
      :task="activeTaskSummary"
      :handoff-enabled="false"
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
</style>
