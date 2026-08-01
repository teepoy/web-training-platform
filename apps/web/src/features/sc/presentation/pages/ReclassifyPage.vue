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
  NDescriptions,
  NDescriptionsItem,
  useThemeVars,
  useMessage,
} from "naive-ui";
import { useRouter } from "vue-router";
import { FullScreenLayout } from "@/shared/components/full-screen-layout";
import { useReclassifyPage } from "../../application/useReclassifyPage";
import { toUserMessage } from "@/shared/api";
import InspectionQuad from "@/features/sc/presentation/components/InspectionQuad.vue";
import ReclassifyAnnotationSidebar from "../components/ReclassifyAnnotationSidebar.vue";
import ReclassifyTaskProgressModal from "../components/ReclassifyTaskProgressModal.vue";
import type { ScSampleTableFilter } from "@/features/sc/domain/sampleTable";

const page = useReclassifyPage();
const themeVars = useThemeVars();
const message = useMessage();
const router = useRouter();
const taskInsightVisible = ref(false);
const inspectionQuad = ref<{
  getGlobalFilter: () => ScSampleTableFilter;
  queryGlobalFilterCount: () => Promise<number>;
  queryRandomGlobalFilteredDefectIds: (count: number) => Promise<number[]>;
} | null>(null);
const filterConfirmationVisible = ref(false);
const filteredWorkflowCount = ref(0);
const filteredWorkflowFilter = ref<ScSampleTableFilter | null>(null);
const isPreparingFilteredWorkflow = ref(false);
const samplingAvailableCount = ref(0);
const isPreparingSampling = ref(false);

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
  page.setAnnotationDrafts(page.selectedDefectIds.value, code);
}

async function handleTrainAndPredictClick(): Promise<void> {
  const quad = inspectionQuad.value;
  if (!quad) {
    message.error("Data is still loading. Try again in a moment.");
    return;
  }
  const globalFilter = quad.getGlobalFilter();
  if (Object.keys(globalFilter).length > 0) {
    isPreparingFilteredWorkflow.value = true;
    try {
      filteredWorkflowFilter.value = globalFilter;
      const count = await quad.queryGlobalFilterCount();
      filteredWorkflowCount.value = count;
      filterConfirmationVisible.value = true;
    } catch (error) {
      message.error(
        error instanceof Error ? error.message : "Failed to resolve filtered workflow samples",
      );
    } finally {
      isPreparingFilteredWorkflow.value = false;
    }
    return;
  }
  await submitTrainAndPredict(null);
}

async function submitTrainAndPredict(sampleFilter: ScSampleTableFilter | null): Promise<void> {
  filterConfirmationVisible.value = false;
  await page.trainAndPredict(sampleFilter);
  if (page.trainPredictTaskId.value) {
    taskInsightVisible.value = true;
  }
}

const globalFilterEntries = computed(() => Object.entries(filteredWorkflowFilter.value ?? {}));

async function openSamplingModal(): Promise<void> {
  isPreparingSampling.value = true;
  try {
    const count = await inspectionQuad.value?.queryGlobalFilterCount();
    if (count === undefined) throw new Error("Data is still loading. Try again in a moment.");
    samplingAvailableCount.value = count;
    page.samplingCount.value = Math.min(page.samplingCount.value, Math.max(count, 1));
    page.showSamplingModal.value = true;
  } catch (error) {
    message.error(toUserMessage(error, "Failed to prepare sampling"));
  } finally {
    isPreparingSampling.value = false;
  }
}

async function applyRandomSampling(): Promise<void> {
  isPreparingSampling.value = true;
  try {
    const ids = await inspectionQuad.value?.queryRandomGlobalFilteredDefectIds(
      page.samplingCount.value,
    );
    if (!ids) throw new Error("Data is still loading. Try again in a moment.");
    page.applySampling(ids.map(String));
  } catch (error) {
    message.error(toUserMessage(error, "Failed to sample defects"));
  } finally {
    isPreparingSampling.value = false;
  }
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
              data-testid="sc-trainer-select"
              :options="page.trainerOptions.value"
              placeholder="Select trainer"
              size="small"
              :style="{ width: '160px' }"
            />
            <NButton
              data-testid="sc-train-predict"
              size="small"
              type="primary"
              :disabled="!page.canTrainAndPredict.value"
              :loading="page.isTrainPredictRunning.value || isPreparingFilteredWorkflow"
              @click="handleTrainAndPredictClick"
            >
              Train &amp; Predict
            </NButton>
            <NText
              v-if="page.trainPredictStatusMessage.value"
              data-testid="sc-train-predict-status"
              depth="3"
              style="font-size: 11px"
            >
              {{ page.trainPredictStatusMessage.value }}
            </NText>
            <NTooltip v-if="page.trainingSampleLimitNotice.value" trigger="hover">
              <template #trigger>
                <NText type="warning" style="font-size: 11px">1,000/class limit</NText>
              </template>
              {{ page.trainingSampleLimitNotice.value }}
            </NTooltip>
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
              :loading="isPreparingSampling"
              @click="openSamplingModal"
            >
              Sampling
            </NButton>
            <NButton size="small" quaternary @click="router.push('/sc/handbook')">
              Handbook
            </NButton>
          </div>
        </div>

        <!-- Main area -->
        <div class="classify-layout">
          <NEmpty
            v-if="!page.inspectionContext.value"
            description="Inspection metadata not available for this dataset"
          />
          <InspectionQuad
            ref="inspectionQuad"
            v-else
            variant="reclassify"
            :dataset-id="page.datasetId.value"
            :inspection-time="page.inspectionContext.value.inspectionTime"
            :wafer-key="Number(page.inspectionContext.value.waferKey)"
            :wafer-geometry="page.waferGeometry.value"
            :selected-defect-ids="Array.from(page.selectedDefectIds.value)"
            :gallery-random-sampling-defect-ids="page.galleryRandomSamplingDefectIds.value"
            :annotation-drafts="page.annotationDraft.value"
            @clear-gallery-random-sampling="page.clearGalleryRandomSamplingDefectIds"
            @selection-change="page.applySelectionAction"
          >
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
            :max="samplingAvailableCount"
            style="width: 100%"
          />
          <NText depth="3" style="font-size: 11px; margin-top: 4px">
            Total available: {{ samplingAvailableCount }} samples
          </NText>
        </div>
        <NCheckbox v-model:checked="page.assignDefaultDraftLabel.value" style="margin-top: 12px">
          Assign draft label to sampled
        </NCheckbox>
      </div>
      <template #footer>
        <div class="sc-sampling-footer">
          <NButton @click="page.showSamplingModal.value = false">Cancel</NButton>
          <NButton
            type="primary"
            :loading="isPreparingSampling"
            :disabled="samplingAvailableCount === 0"
            @click="applyRandomSampling"
          >
            Confirm
          </NButton>
        </div>
      </template>
    </NModal>
    <NModal
      v-model:show="filterConfirmationVisible"
      preset="card"
      title="Filtered Train & Predict"
      :style="{ width: '560px' }"
    >
      <NText>
        The current global filter will limit both training and prediction to
        {{ filteredWorkflowCount }} defects.
      </NText>
      <NDescriptions bordered :column="1" size="small" style="margin-top: 16px">
        <NDescriptionsItem
          v-for="[field, condition] in globalFilterEntries"
          :key="field"
          :label="field"
        >
          {{ JSON.stringify(condition) }}
        </NDescriptionsItem>
      </NDescriptions>
      <template #footer>
        <div class="sc-sampling-footer">
          <NButton @click="filterConfirmationVisible = false">Cancel</NButton>
          <NButton
            type="primary"
            :disabled="filteredWorkflowCount === 0"
            @click="submitTrainAndPredict(filteredWorkflowFilter)"
          >
            Continue with {{ filteredWorkflowCount }} defects
          </NButton>
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
