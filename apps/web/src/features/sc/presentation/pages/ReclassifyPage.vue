<script setup lang="ts">
import { computed, onMounted, onBeforeUnmount, ref } from "vue";
import {
  NSpin,
  NEmpty,
  NResult,
  NSelect,
  NButton,
  NInput,
  NInputNumber,
  NTag,
  NImage,
  NText,
  NDivider,
  NRadioGroup,
  NRadioButton,
  NModal,
  NCheckbox,
  NTooltip,
  useThemeVars,
} from "naive-ui";
import { useRouter } from "vue-router";
import { FullScreenLayout } from "@/shared/components/full-screen-layout";
import { useReclassifyPage } from "../../application/useReclassifyPage";
import ScReclassifyBlinkVirtualTable from "../components/ScReclassifyBlinkVirtualTable.vue";
import ScMapPanel from "@/features/sc/presentation/components/ScMapPanel.vue";
import { create } from "@bufbuild/protobuf";
import type { ScBlinkImageUrls } from "@/features/sc/domain/models";
import {
  ScSampleItemSchema,
  ReviewImageSchema,
  type ScSampleItem,
} from "@/features/sc/generated/proto/sc/v1/sample_pb";
import type {
  ScBoxRegion,
  ScMapMode,
} from "@/features/sc/api/boxFilter";
import { fetchScDatasetBoxFilter } from "@/features/sc/api/boxFilter";

const page = useReclassifyPage();
const themeVars = useThemeVars();
const router = useRouter();

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

const newLabelInput = ref("");
const addLabelErrorMsg = computed(() => page.addLabelError.value);

function onAddLabelClick() {
  const val = newLabelInput.value.trim();
  if (!val) return;
  page.addLabel(val);
  newLabelInput.value = "";
}

function goBack() {
  router.back();
}

/** Curried box-selection: bakes datasetId + reticleOptions, takes mode + region → defect IDs. */
async function queryBoxSelection(mode: ScMapMode, region: ScBoxRegion): Promise<number[]> {
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

function onBlinkTableSelect(
  defectIds: string[],
  modifiers: { shift: boolean; ctrl: boolean; meta: boolean },
): void {
  const mode: import("../../application/useReclassifyPage").SelectionMode = modifiers.shift
    ? "add"
    : modifiers.ctrl || modifiers.meta
      ? "toggle"
      : "replace";
  page.selectDefectIds(defectIds, mode);
}

// ── Keyboard shortcuts: digit 1-9 applies label by class index ──────

function handleKeydown(e: KeyboardEvent): void {
  if (e.key === "Escape") {
    if (page.selectedDefectIds.value.size > 0) {
      page.clearSelection();
      return;
    }
  }

  const digit = Number(e.key);
  if (!Number.isFinite(digit) || digit < 1 || digit > 9) return;

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

  const labelOpts = page.effectiveLabels.value;
  const idx = digit - 1;
  if (idx >= labelOpts.length) return;

  const label = labelOpts[idx];
  if (!label) return;

  if (page.selectedDefectIds.value.size === 0) return;

  for (const id of page.selectedDefectIds.value) {
    page.setAnnotationDraft(id, label);
  }
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
    if (s.currentLabel && s.currentLabel !== '__unlabeled__') map[s.defectId] = s.currentLabel;
  }
  return map;
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
      v-else-if="!page.isBlinkLoading.value && !page.isMapLoading.value && page.scSamples.value.length === 0"
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
                {{ page.dataset.value?.name ?? 'Reclassify' }}
              </NText>
            </template>
            {{ page.dataset.value?.name ?? 'Reclassify' }}
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
            :disabled="!page.selectedTrainerId.value || page.isTrainPredictRunning.value || page.annotatedCount.value === 0"
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
          <NButton size="small" type="primary" @click="page.showSamplingModal.value = true">
            Sampling
          </NButton>
          <NTooltip placement="bottom-end">
            <template #trigger>
              <NButton
                class="sc-header-meta-button"
                size="small"
                quaternary
                aria-label="Dataset map details"
              >
                &hellip;
              </NButton>
            </template>
            <div class="sc-header-meta-tooltip">
              <div>{{ page.plotPointTotal.value }} samples</div>
              <div v-if="page.inspectionContext.value">
                W{{ page.inspectionContext.value.waferKey }}
                @ {{ page.inspectionContext.value.inspectionTime }}
              </div>
            </div>
          </NTooltip>
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
            <span v-if="page.activeFilterCount.value > 0" class="sc-filter-hint">
              {{ page.activeFilterCount.value }} filter(s) active
              <NButton text size="tiny" type="primary" @click="page.clearMapFilter()">Clear</NButton>
            </span>
          </div>
          <NSpin :show="page.activeTab.value === 'blink' ? page.isBlinkLoading.value : page.isMapLoading.value" class="sc-blink-spin">
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
              @legend-group-change="page.handleLegendGroupByChange"
              @retry="() => {}"
            />
          </NSpin>
        </div>

        <!-- Right: Annotation sidebar -->
        <div class="classify-sidebar-container sc-sidebar">
          <div class="sc-annotate">
            <div class="sc-annotate-header">
              <NText strong>Annotation</NText>
              <NTag
                v-if="page.selectedCount.value > 0"
                size="tiny"
                :bordered="false"
                type="warning"
              >
                {{ page.selectedCount.value }} sample{{ page.selectedCount.value === 1 ? '' : 's' }}
              </NTag>
            </div>

            <NDivider style="margin: 8px 0" />

            <div class="sc-label-picker">
              <label class="sc-label-label">Label</label>
              <div class="sc-label-create-row">
                <NInput v-model:value="newLabelInput" placeholder="New label name..." size="small" :disabled="page.isAddingLabel.value" @keyup.enter="onAddLabelClick" />
                <NButton size="small" type="primary" :disabled="!newLabelInput.trim() || page.isAddingLabel.value" :loading="page.isAddingLabel.value" @click="onAddLabelClick">Add Label</NButton>
              </div>
              <NText v-if="addLabelErrorMsg" type="error" depth="3" style="font-size: 11px; margin-top: 2px;">{{ addLabelErrorMsg }}</NText>
            </div>

            <div class="sc-bulk-apply">
              <NText depth="3" class="sc-bulk-hint">
                Apply to all selected:
              </NText>
                <div class="sc-bulk-actions">
                  <NButton
                  v-for="(lbl, i) in page.effectiveLabels.value"
                  :key="lbl"
                  size="tiny"
                  :type="Object.values(page.annotationDraft.value).some((v) => v === lbl) ? 'primary' : 'default'"
                  :ghost="!Object.values(page.annotationDraft.value).some((v) => v === lbl)"
                  @click="() => {
                    for (const id of page.selectedDefectIds.value) {
                      page.setAnnotationDraft(id, lbl);
                    }
                  }"
                >
                  {{ i + 1 }}. {{ lbl }}
                </NButton>
              </div>
            </div>

            <div v-if="page.draftCount.value > 0" class="sc-draft-summary">
              <NText depth="3">
                {{ page.draftCount.value }} annotation{{ page.draftCount.value === 1 ? '' : 's' }} pending
              </NText>
            </div>

            <NDivider style="margin: 8px 0" />

            <div class="sc-actions">
              <NButton
                type="primary"
                size="small"
                :disabled="page.draftCount.value === 0"
                :loading="page.isSubmitting.value"
                @click="page.submitAnnotations()"
              >
                Submit {{ page.draftCount.value > 0 ? `(${page.draftCount.value})` : '' }}
              </NButton>
              <NButton
                v-if="page.draftCount.value > 0"
                size="small"
                @click="page.clearDrafts()"
              >
                Clear Drafts
              </NButton>
              <NButton
                v-if="page.selectedCount.value > 0"
                size="small"
                :disabled="selectedDraftCount === 0"
                @click="clearSelectedDrafts"
              >
                Clear Selected Draft{{ selectedDraftCount === 1 ? '' : 's' }}
              </NButton>
            </div>

            <NDivider style="margin: 8px 0" />

            <div class="sc-sample-detail">
              <NText depth="3" class="sc-detail-title">Sample Detail</NText>
              <div
                v-for="item in page.annotationGridItems.value"
                :key="item.id"
                class="sc-detail-row"
              >
                <div class="sc-detail-images">
                  <NImage
                    v-for="(src, i) in item.imageSrcs.slice(0, 3)"
                    :key="i"
                    :src="src"
                    width="80"
                    height="80"
                    object-fit="cover"
                    class="sc-detail-img"
                    lazy
                  />
                </div>
                <div class="sc-detail-meta">
                  <div class="sc-meta-item">
                    <span class="sc-meta-key">ID</span>
                    <span class="sc-meta-val">{{ item.id.slice(0, 12) }}</span>
                  </div>
                  <div class="sc-meta-item">
                    <span class="sc-meta-key">Defect</span>
                    <span class="sc-meta-val">{{ item.metadata.defectId ?? '\u2014' }}</span>
                  </div>
                  <div class="sc-meta-item">
                    <span class="sc-meta-key">Class</span>
                    <span class="sc-meta-val">{{ item.metadata.classNumber ?? '\u2014' }}</span>
                  </div>
                  <div class="sc-meta-item">
                    <span class="sc-meta-key">Current Label</span>
                    <NTag
                      v-if="item.currentLabel"
                      size="tiny"
                      :bordered="false"
                      type="success"
                    >
                      {{ item.currentLabel }}
                    </NTag>
                    <span v-else class="sc-meta-val">\u2014</span>
                  </div>
                </div>
              </div>
            </div>


          </div>
        </div>
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
          <NText depth="2" style="font-size: 13px;">Sample Count</NText>
          <NInputNumber
            v-model:value="page.samplingCount.value"
            :min="1"
            :max="page.plotPointTotal.value"
            style="width: 100%;"
          />
          <NText depth="3" style="font-size: 11px; margin-top: 4px;">
            Total available: {{ page.plotPointTotal.value }} samples
          </NText>
        </div>
        <NCheckbox v-model:checked="page.assignDefaultDraftLabel.value" style="margin-top: 12px;">
          Assign default draft label (label 1) to all sampled data
        </NCheckbox>
      </div>
      <template #footer>
        <NButton @click="page.showSamplingModal.value = false">Cancel</NButton>
        <NButton type="primary" @click="page.applySampling()">Confirm</NButton>
      </template>
    </NModal>
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

.sc-header-meta-button {
  min-width: 28px;
  padding: 0 6px;
  font-weight: 700;
  letter-spacing: 1px;
}

.sc-header-meta-tooltip {
  display: flex;
  flex-direction: column;
  gap: 2px;
  max-width: 320px;
  font-size: 12px;
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

.classify-sidebar-container {
  display: flex;
  flex-direction: column;
  border-left: 1px solid var(--cv-border, rgba(255, 255, 255, 0.12));
  background: var(--cv-card-bg, #1e1e2e);
  transition: width 0.2s, min-width 0.2s;
  width: 340px;
  flex-shrink: 0;
  overflow-y: auto;
}

/* ── Annotation panel inside sidebar ───────────────── */
.sc-annotate {
  padding: 12px 16px 16px;
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.sc-annotate-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.sc-label-picker {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.sc-label-label {
  font-size: 12px;
  font-weight: 500;
  color: var(--cv-text-secondary, rgba(255, 255, 255, 0.5));
}

.sc-label-create-row {
  display: flex;
  gap: 6px;
  align-items: center;
}

.sc-bulk-hint {
  font-size: 12px;
  margin-bottom: 6px;
}

.sc-bulk-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.sc-draft-summary {
  margin-top: 4px;
}

.sc-detail-title {
  font-size: 12px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.4px;
}

.sc-detail-images {
  display: flex;
  gap: 6px;
  margin-top: 8px;
}

.sc-detail-img {
  border-radius: 4px;
  border: 1px solid var(--cv-border, rgba(255, 255, 255, 0.1));
  flex-shrink: 0;
}

.sc-detail-meta {
  margin-top: 10px;
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.sc-meta-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  font-size: 12px;
  padding: 2px 0;
}

.sc-meta-key {
  color: var(--cv-text-secondary, rgba(255, 255, 255, 0.45));
  min-width: 80px;
}

.sc-meta-val {
  color: var(--cv-text, #fff);
  text-align: right;
  font-variant-numeric: tabular-nums;
}

.sc-multi-hint,
.sc-no-select {
  margin-top: 8px;
  padding: 16px 0;
}

.sc-actions {
  display: flex;
  gap: 8px;
  margin-top: 4px;
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
