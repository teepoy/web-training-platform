<script setup lang="ts">
import { computed, onMounted, onBeforeUnmount, ref } from "vue";
import { useQuery } from "@tanstack/vue-query";
import {
  NSpin,
  NEmpty,
  NResult,
  NSelect,
  NButton,
  NText,
  NModal,
  NTooltip,
  NDescriptions,
  NDescriptionsItem,
  NTag,
  useThemeVars,
  useMessage,
} from "naive-ui";
import { useRoute, useRouter } from "vue-router";
import { FullScreenLayout } from "@/shared/components/full-screen-layout";
import { useReclassifyPage } from "../../application/useReclassifyPage";
import { toUserMessage } from "@/shared/api";
import InspectionQuad from "@/features/sc/presentation/components/InspectionQuad.vue";
import ReviewSamplingModal from "@/features/sc/presentation/components/ReviewSamplingModal.vue";
import ReclassifyAnnotationSidebar from "../components/ReclassifyAnnotationSidebar.vue";
import ReclassifyTaskProgressModal from "../components/ReclassifyTaskProgressModal.vue";
import {
  cloneScGlobalFilter,
  emptyScGlobalFilter,
  scGlobalFilterConditions,
  type ScFilterCondition,
  type ScGlobalFilter,
} from "@/features/sc/domain/globalFilter";
import type {
  ScSamplingGroupPopulation,
  ScSamplingProgram,
} from "@/features/sc/domain/samplingRules";
import { SC_SAMPLING_RANDOM_SEED } from "@/features/sc/domain/samplingRules";
import type { ScSamplingCandidateScope } from "@/features/sc/application/inspectionFilterPolicy";
import {
  getCollectionApiV1DatasetCollectionsCollectionIdGet,
  getDatasetApiV1DatasetsDatasetIdGet,
  getRevisionApiV1DatasetCollectionsCollectionIdRevisionsRevisionIdGet,
} from "@/generated/orval/endpoints/api";

const page = useReclassifyPage();
const themeVars = useThemeVars();
const message = useMessage();
const router = useRouter();
const route = useRoute();
const collectionId = computed(() => {
  const value = route.params.collectionId;
  return typeof value === "string" && value.length > 0 ? value : null;
});
const collectionRevisionId = computed(() => {
  const value = route.query.revisionId;
  return typeof value === "string" && value.length > 0 ? value : null;
});
const collectionStackQuery = useQuery({
  queryKey: computed(() => [
    "dataset-collections",
    collectionId.value,
    "classify-stack",
    collectionRevisionId.value,
  ]),
  enabled: computed(() => !!collectionId.value && !!collectionRevisionId.value),
  queryFn: async () => {
    const id = collectionId.value;
    const revisionId = collectionRevisionId.value;
    if (!id || !revisionId) throw new Error("Collection revision is required");
    const [collection, revision] = await Promise.all([
      getCollectionApiV1DatasetCollectionsCollectionIdGet(id),
      getRevisionApiV1DatasetCollectionsCollectionIdRevisionsRevisionIdGet(id, revisionId),
    ]);
    const datasets = await Promise.all(
      revision.source_snapshot.map((source) =>
        getDatasetApiV1DatasetsDatasetIdGet(String(source.source_dataset_id)),
      ),
    );
    return { collection, revision, datasets };
  },
});
const globalFilterTriggerTarget = ref<HTMLElement | null>(null);
const taskInsightVisible = ref(false);
const inspectionQuad = ref<{
  getSamplingContext: () => {
    mapSelectionCount: number;
    tableSelectionAvailable: boolean;
  };
  querySamplingCandidateCount: (options: {
    scope: ScSamplingCandidateScope;
    extraFilterEnabled: boolean;
    extraFilter: ScGlobalFilter;
  }) => Promise<number>;
  querySamplingDefectIds: (
    program: ScSamplingProgram,
    seed: number,
    options: {
      scope: ScSamplingCandidateScope;
      extraFilterEnabled: boolean;
      extraFilter: ScGlobalFilter;
    },
  ) => Promise<number[]>;
  querySamplingGroups: (
    field: string,
    options: {
      scope: ScSamplingCandidateScope;
      extraFilterEnabled: boolean;
      extraFilter: ScGlobalFilter;
    },
  ) => Promise<ScSamplingGroupPopulation[]>;
  filterDistinctValues: Record<string, Array<string | number>>;
  filterNumericRanges: Record<string, { min: number; max: number } | null>;
  filterNumericRangeLoading: Record<string, boolean>;
  filterNumericRangeErrors: Record<string, boolean>;
  filterResetKey: string;
  searchFilterOptions: (payload: { field: string; search: string }) => Promise<void>;
  requestSamplingExtraFilterRange: (
    filter: ScGlobalFilter,
    payload: { field: string; itemId?: string },
  ) => Promise<void>;
  openGlobalFilterModal: () => void;
} | null>(null);
const filterConfirmationVisible = ref(false);
const filteredWorkflowCount = ref(0);
const filteredWorkflowFilter = ref<ScGlobalFilter | null>(null);
const isPreparingFilteredWorkflow = ref(false);
const samplingAvailableCount = ref(0);
const samplingMapSelectionCount = ref(0);
const samplingTableSelectionAvailable = ref(false);
const samplingExtraFilter = ref<ScGlobalFilter>(emptyScGlobalFilter());
const isPreparingSampling = ref(false);

const samplingOptions = computed(() => ({
  scope: page.samplingScope.value,
  extraFilterEnabled: page.samplingProgram.value.extraFilterEnabled,
  extraFilter: samplingExtraFilter.value,
}));
const samplingFilterDistinctValues = computed(
  () => inspectionQuad.value?.filterDistinctValues ?? {},
);
const samplingFilterNumericRanges = computed(() => inspectionQuad.value?.filterNumericRanges ?? {});
const samplingFilterNumericRangeLoading = computed(
  () => inspectionQuad.value?.filterNumericRangeLoading ?? {},
);
const samplingFilterNumericRangeErrors = computed(
  () => inspectionQuad.value?.filterNumericRangeErrors ?? {},
);
const samplingFilterResetKey = computed(() => inspectionQuad.value?.filterResetKey);

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
  if (collectionId.value) {
    void router.push(`/dataset-collections/${collectionId.value}`);
    return;
  }
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
  const workflowFilter = page.resolveTrainSampleFilter();
  if (workflowFilter) {
    isPreparingFilteredWorkflow.value = true;
    try {
      filteredWorkflowFilter.value = workflowFilter;
      filteredWorkflowCount.value = await quad.querySamplingCandidateCount({
        scope: "all",
        extraFilterEnabled: false,
        extraFilter: emptyScGlobalFilter(),
      });
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
  await submitTrainAndPredict();
}

async function submitTrainAndPredict(): Promise<void> {
  filterConfirmationVisible.value = false;
  await page.trainAndPredict();
  if (page.trainPredictTaskId.value) {
    taskInsightVisible.value = true;
  }
}

const globalFilterEntries = computed(() =>
  filteredWorkflowFilter.value ? scGlobalFilterConditions(filteredWorkflowFilter.value) : [],
);

function formatWorkflowCondition(field: string, condition: ScFilterCondition): string {
  if (field === "defect_id" && condition.filterType === "set") {
    return condition.exclude
      ? `excludes ${condition.values.length} defects`
      : `includes ${condition.values.length} defects`;
  }
  return JSON.stringify(condition);
}

async function openSamplingModal(): Promise<void> {
  isPreparingSampling.value = true;
  try {
    const quad = inspectionQuad.value;
    if (!quad) throw new Error("Data is still loading. Try again in a moment.");
    const context = quad.getSamplingContext();
    samplingMapSelectionCount.value = context.mapSelectionCount;
    samplingTableSelectionAvailable.value = context.tableSelectionAvailable;
    if (
      (page.samplingScope.value === "map" && context.mapSelectionCount === 0) ||
      (page.samplingScope.value === "table" && !context.tableSelectionAvailable)
    ) {
      page.samplingScope.value = "all";
    }
    page.showSamplingModal.value = true;
    await refreshSamplingAvailableCount();
  } catch (error) {
    message.error(toUserMessage(error, "Failed to prepare sampling"));
  } finally {
    isPreparingSampling.value = false;
  }
}

async function refreshSamplingAvailableCount(): Promise<void> {
  const quad = inspectionQuad.value;
  if (!quad) throw new Error("Data is still loading. Try again in a moment.");
  const count = await quad.querySamplingCandidateCount(samplingOptions.value);
  samplingAvailableCount.value = count;
}

async function loadSamplingGroups(field: string): Promise<ScSamplingGroupPopulation[]> {
  const quad = inspectionQuad.value;
  if (!quad) throw new Error("Data is still loading. Try again in a moment.");
  return quad.querySamplingGroups(field, samplingOptions.value);
}

function updateSamplingExtraFilter(filter: ScGlobalFilter): void {
  samplingExtraFilter.value = cloneScGlobalFilter(filter);
}

function searchSamplingExtraFilterOptions(payload: { field: string; search: string }): void {
  void inspectionQuad.value?.searchFilterOptions(payload);
}

function requestSamplingExtraFilterRange(payload: { field: string; itemId?: string }): void {
  void inspectionQuad.value?.requestSamplingExtraFilterRange(samplingExtraFilter.value, payload);
}

async function handleSamplingScopeChange(): Promise<void> {
  isPreparingSampling.value = true;
  try {
    await refreshSamplingAvailableCount();
  } catch (error) {
    message.error(toUserMessage(error, "Failed to update sampling candidates"));
  } finally {
    isPreparingSampling.value = false;
  }
}

async function applyRandomSampling(): Promise<void> {
  isPreparingSampling.value = true;
  try {
    const ids = await inspectionQuad.value?.querySamplingDefectIds(
      page.samplingProgram.value,
      SC_SAMPLING_RANDOM_SEED,
      samplingOptions.value,
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
            <NTag v-if="collectionId" size="small" type="info">
              {{ collectionStackQuery.data.value?.collection.name ?? "Collection" }}
            </NTag>
            <NTag v-if="collectionId" size="small" :bordered="false">
              {{ collectionStackQuery.data.value?.datasets.length ?? 0 }} datasets combined
            </NTag>
            <div class="sc-dataset-title" data-testid="sc-dataset-name">
              <NTooltip>
                <template #trigger>
                  <NText depth="2" class="sc-dataset-name">
                    {{ page.dataset.value?.name ?? "Reclassify" }}
                  </NText>
                </template>
                {{ page.dataset.value?.name ?? "Reclassify" }}
              </NTooltip>
            </div>
            <div class="sc-reclassify-filter-actions" data-testid="sc-filter-actions">
              <div
                ref="globalFilterTriggerTarget"
                id="sc-reclassify-global-filter-action"
                class="sc-reclassify-global-filter-action"
              />
              <div class="sc-reclassify-random-filter-action">
                <NButton
                  data-testid="sc-random-filter-trigger"
                  size="small"
                  :type="page.galleryRandomSamplingDefectIds.value.size ? 'primary' : 'default'"
                  :loading="isPreparingSampling"
                  @click="openSamplingModal"
                >
                  Random Filter{{
                    page.galleryRandomSamplingDefectIds.value.size
                      ? ` (${page.galleryRandomSamplingDefectIds.value.size})`
                      : ""
                  }}
                </NButton>
                <NButton
                  v-if="page.galleryRandomSamplingDefectIds.value.size"
                  data-testid="sc-random-filter-clear"
                  size="small"
                  quaternary
                  @click="page.clearGalleryRandomSamplingDefectIds"
                >
                  Clear
                </NButton>
              </div>
            </div>
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
            :collection-id="collectionId ?? undefined"
            :collection-revision-id="collectionRevisionId ?? undefined"
            :inspection-time="page.inspectionContext.value.inspectionTime"
            :wafer-key="Number(page.inspectionContext.value.waferKey)"
            :wafer-geometry="page.waferGeometry.value"
            :selected-defect-ids="Array.from(page.selectedDefectIds.value)"
            :gallery-random-sampling-defect-ids="page.galleryRandomSamplingDefectIds.value"
            :annotation-drafts="page.annotationDraft.value"
            v-model:global-filter="page.globalFilter.value"
            :global-filter-trigger-target="globalFilterTriggerTarget ?? undefined"
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

    <ReviewSamplingModal
      v-model:show="page.showSamplingModal.value"
      v-model:program="page.samplingProgram.value"
      v-model:scope="page.samplingScope.value"
      :loading="isPreparingSampling"
      :available-count="samplingAvailableCount"
      :map-selection-count="samplingMapSelectionCount"
      :table-selection-available="samplingTableSelectionAvailable"
      :extra-filter="samplingExtraFilter"
      :extra-filter-distinct-values="samplingFilterDistinctValues"
      :extra-filter-numeric-ranges="samplingFilterNumericRanges"
      :extra-filter-numeric-range-loading="samplingFilterNumericRangeLoading"
      :extra-filter-numeric-range-errors="samplingFilterNumericRangeErrors"
      :extra-filter-reset-key="samplingFilterResetKey"
      :load-groups="loadSamplingGroups"
      @update:extra-filter="updateSamplingExtraFilter"
      @scope-change="handleSamplingScopeChange"
      @search-extra-filter-options="searchSamplingExtraFilterOptions"
      @request-extra-filter-range="requestSamplingExtraFilterRange"
      @confirm="applyRandomSampling"
    />
    <NModal
      v-model:show="filterConfirmationVisible"
      preset="card"
      title="Filtered Train & Predict"
      :style="{ width: '560px' }"
    >
      <NText>
        The current workbench scope will limit both training and prediction to
        {{ filteredWorkflowCount }} defects.
      </NText>
      <NDescriptions bordered :column="1" size="small" style="margin-top: 16px">
        <NDescriptionsItem v-for="item in globalFilterEntries" :key="item.id" :label="item.field">
          {{ formatWorkflowCondition(item.field, item.condition) }}
        </NDescriptionsItem>
      </NDescriptions>
      <template #footer>
        <div class="sc-sampling-footer">
          <NButton @click="filterConfirmationVisible = false">Cancel</NButton>
          <NButton
            type="primary"
            :disabled="filteredWorkflowCount === 0"
            @click="submitTrainAndPredict"
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
  flex: 1 1 auto;
  align-items: center;
  gap: 12px;
  min-width: 0;
}

.sc-dataset-title {
  min-width: 0;
}

.sc-reclassify-filter-actions {
  display: flex;
  align-items: center;
  gap: 8px;
  flex: 0 0 auto;
}

.sc-reclassify-global-filter-action {
  display: flex;
  align-items: center;
}

.sc-reclassify-random-filter-action {
  display: flex;
  align-items: center;
  gap: 4px;
  flex: 0 0 auto;
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

@media (max-width: 960px) {
  .sc-header {
    flex-wrap: wrap;
    gap: 8px;
  }

  .sc-header-left,
  .sc-header-right {
    width: 100%;
  }

  .sc-header-left {
    flex-basis: 100%;
  }

  .sc-header-right {
    flex-wrap: wrap;
    justify-content: flex-end;
  }

  .sc-dataset-title {
    flex: 1 1 auto;
  }

  .sc-dataset-name {
    max-width: none;
  }
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

.sc-sampling-footer {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
}
</style>
