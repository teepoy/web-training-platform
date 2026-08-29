<script setup lang="ts">
import { computed, onUnmounted, ref, watch } from "vue";
import { useI18n } from "vue-i18n";
import { useMessage, useThemeVars } from "naive-ui";
import type {
  ScCollectionPredictionExportRequest,
  ScKlarfVersion,
  ScPredictionExportRequest,
  ScPredictionExportResultSource,
} from "@/generated/orval/models";
import type { ExporterResult } from "@/shared/widgets/sdk";
import { buildExportDownloadUrl } from "@/shared/api/datasets";
import { streamApiSse } from "@/shared/api/sse";
import { toUserMessage } from "@/shared/api";
import type { ScSamplingCandidateScope } from "@/features/sc/application/inspectionFilterPolicy";
import { SqlWorkbenchDataSource } from "@/features/sc/api/sqlWorkbenchDataSource";
import type { ScDataFilterExpression } from "@/features/sc/domain/workbenchDataSource";
import { emptyScGlobalFilter, toScWorkflowSampleFilter } from "@/features/sc/domain/globalFilter";
import { buildScGlobalDataFilters } from "@/features/sc/application/workbenchDataFilter";
import {
  SC_SAMPLING_RANDOM_SEED,
  type ScSamplingGroupPopulation,
  type ScSamplingProgram,
} from "@/features/sc/domain/samplingRules";
import {
  loadScSamplingPreference,
  saveScSamplingPreference,
} from "@/features/sc/application/samplingPreferences";
import ReviewSamplingModal from "./ReviewSamplingModal.vue";
import { formatNumber } from "@/shared/i18n/format";

const { t } = useI18n();

const props = withDefaults(
  defineProps<{
    datasetId?: string;
    collectionId?: string;
    memberIds?: string[];
    memberDatasetIds?: string[];
    onComplete: (result?: ExporterResult) => void;
    onCancel: () => void;
    embedded?: boolean;
  }>(),
  {
    datasetId: undefined,
    collectionId: undefined,
    memberIds: () => [],
    memberDatasetIds: () => [],
    embedded: false,
  },
);
const message = useMessage();
const themeVars = useThemeVars();
const exportSurfaceStyle = computed(() => ({
  "--prediction-export-surface": themeVars.value.cardColor,
  "--prediction-export-selected": themeVars.value.hoverColor,
  "--prediction-export-text": themeVars.value.textColor1,
  "--prediction-export-muted": themeVars.value.textColor3,
  "--prediction-export-border": themeVars.value.borderColor,
  "--prediction-export-primary": themeVars.value.primaryColor,
}));

const format = ref<ScPredictionExportRequest["format"]>("parquet");
const resultSource = ref<ScPredictionExportResultSource>("final_class");
const klarfVersion = ref<ScKlarfVersion>("1.2");
const includeImages = ref(false);
const loading = ref(false);
const statusMessage = ref("");
const samplingEnabled = ref(false);
const samplingVisible = ref(false);
const samplingLoading = ref(false);
const samplingAvailableCount = ref(0);
const samplingProgram = ref<ScSamplingProgram>(loadScSamplingPreference("review"));
const samplingScope = ref<ScSamplingCandidateScope>("all");
const samplingExtraFilter = ref(emptyScGlobalFilter());
const extraFilterDistinctValues = ref<Record<string, Array<string | number>>>({});
const extraFilterNumericRanges = ref<Record<string, { min: number; max: number } | null>>({});
const extraFilterNumericRangeLoading = ref<Record<string, boolean>>({});
const extraFilterNumericRangeErrors = ref<Record<string, boolean>>({});
const resultDistribution = ref<Record<string, number>>({});
const distributionLoading = ref(false);
let distributionVersion = 0;
const result = ref<{
  uri: string;
  rows: number;
  format: string;
  filename: string;
  sampled: boolean;
  klarfVersion: ScKlarfVersion | null;
} | null>(null);
const dataSources = new Map<string, SqlWorkbenchDataSource>();
const isCollectionExport = computed(() => !!props.collectionId);
const targetDatasetIds = computed(() =>
  isCollectionExport.value ? props.memberDatasetIds : props.datasetId ? [props.datasetId] : [],
);
const resultSourceOptions = computed<
  ReadonlyArray<{
    value: ScPredictionExportResultSource;
    label: string;
    description: string;
    field: string;
  }>
>(() => [
  {
    value: "annotation" as const,
    label: t("sc.annotation"),
    description: t("sc.annotationExportHelp"),
    field: "annotation_label",
  },
  {
    value: "prediction" as const,
    label: t("sc.prediction"),
    description: t("sc.predictionExportHelp"),
    field: "prediction_label",
  },
  {
    value: "final_class" as const,
    label: t("sc.finalClass"),
    description: t("sc.finalClassExportHelp"),
    field: "final_class",
  },
]);
const activeResultSource = computed(
  () => resultSourceOptions.value.find((option) => option.value === resultSource.value)!,
);
const resultAvailabilityFilters = computed<readonly ScDataFilterExpression[]>(() => [
  [
    activeResultSource.value.field,
    "not in and not null",
    resultSource.value === "annotation" ? ["", "0"] : [""],
  ],
]);
const distributionEntries = computed(() => {
  const eligible = Object.entries(resultDistribution.value).filter(([value, count]) => {
    if (count <= 0 || value.startsWith("__") || value === "") return false;
    return resultSource.value !== "annotation" || value !== "0";
  });
  const total = eligible.reduce((sum, [, count]) => sum + count, 0);
  return eligible
    .sort((left, right) => right[1] - left[1])
    .map(([value, count]) => ({
      value,
      count,
      percentage: total > 0 ? Math.round((count / total) * 1000) / 10 : 0,
    }));
});

watch(samplingProgram, (program) => saveScSamplingPreference("review", program), { deep: true });

watch(
  [resultSource, targetDatasetIds],
  () => {
    void refreshResultDistribution();
  },
  { immediate: true },
);

const formatOptions = computed(() => [
  {
    value: "parquet" as const,
    title: "Parquet",
    description: t("sc.parquetExportHelp"),
  },
  {
    value: "klarf" as const,
    title: "KLARF",
    description: t("sc.klarfExportHelp"),
  },
  {
    value: "zip" as const,
    title: t("sc.zipPackage"),
    description: t("sc.zipExportHelp"),
  },
]);
const samplingSummary = computed(() =>
  samplingEnabled.value
    ? t("sc.samplingSeedSummary", {
        rules: samplingProgram.value.rules.length,
        seed: SC_SAMPLING_RANDOM_SEED,
      })
    : t("sc.allDatasetRows"),
);

async function prepareSampling(): Promise<void> {
  samplingLoading.value = true;
  try {
    const groups = await loadMergedGroups("wafer_key", true);
    samplingAvailableCount.value = Object.values(groups).reduce((sum, count) => sum + count, 0);
    samplingVisible.value = true;
  } catch (error) {
    message.error(toUserMessage(error, t("sc.samplingPrepareFailed")));
  } finally {
    samplingLoading.value = false;
  }
}

async function loadSamplingGroups(field: string): Promise<ScSamplingGroupPopulation[]> {
  const resolvedField = field === "final_class" ? activeResultSource.value.field : field;
  const groups = await loadMergedGroups(resolvedField, true);
  return Object.entries(groups).map(([value, count]) => ({ value, count }));
}

async function refreshResultDistribution(): Promise<void> {
  if (targetDatasetIds.value.length === 0) {
    resultDistribution.value = {};
    return;
  }
  const version = ++distributionVersion;
  distributionLoading.value = true;
  try {
    const groups = await loadMergedGroups(activeResultSource.value.field);
    if (version === distributionVersion) resultDistribution.value = groups;
  } catch {
    if (version === distributionVersion) resultDistribution.value = {};
  } finally {
    if (version === distributionVersion) distributionLoading.value = false;
  }
}

async function searchExtraFilterOptions(payload: { field: string; search: string }): Promise<void> {
  const values = await Promise.all(
    targetDatasetIds.value.map((datasetId) =>
      sourceFor(datasetId).loadDistinctValues({
        field: payload.field,
        search: payload.search,
        limit: 100,
        filters: resultAvailabilityFilters.value,
      }),
    ),
  );
  extraFilterDistinctValues.value = {
    ...extraFilterDistinctValues.value,
    [payload.field]: [...new Set(values.flat())],
  };
}

async function requestExtraFilterRange(payload: { field: string; itemId?: string }): Promise<void> {
  const key = payload.itemId ?? `draft:${payload.field}`;
  extraFilterNumericRangeLoading.value = {
    ...extraFilterNumericRangeLoading.value,
    [key]: true,
  };
  extraFilterNumericRangeErrors.value = {
    ...extraFilterNumericRangeErrors.value,
    [key]: false,
  };
  try {
    const filters = [
      ...resultAvailabilityFilters.value,
      ...buildScGlobalDataFilters(samplingExtraFilter.value, {
        omitItemId: payload.itemId,
      }),
    ];
    const ranges = await Promise.all(
      targetDatasetIds.value.map((datasetId) =>
        sourceFor(datasetId).loadNumericRange({ field: payload.field, filters }),
      ),
    );
    const valid = ranges.filter((range): range is { min: number; max: number } => range !== null);
    extraFilterNumericRanges.value = {
      ...extraFilterNumericRanges.value,
      [key]: valid.length
        ? {
            min: Math.min(...valid.map((range) => range.min)),
            max: Math.max(...valid.map((range) => range.max)),
          }
        : null,
    };
  } catch {
    extraFilterNumericRangeErrors.value = {
      ...extraFilterNumericRangeErrors.value,
      [key]: true,
    };
  } finally {
    extraFilterNumericRangeLoading.value = {
      ...extraFilterNumericRangeLoading.value,
      [key]: false,
    };
  }
}

function sourceFor(datasetId: string): SqlWorkbenchDataSource {
  const existing = dataSources.get(datasetId);
  if (existing) return existing;
  const source = new SqlWorkbenchDataSource({ kind: "dataset", datasetId });
  dataSources.set(datasetId, source);
  return source;
}

async function loadMergedGroups(
  field: string,
  restrictToResultSource = false,
): Promise<Record<string, number>> {
  if (targetDatasetIds.value.length === 0) {
    throw new Error(t("sc.noExportRecords"));
  }
  const groupResults = await Promise.all(
    targetDatasetIds.value.map((datasetId) =>
      sourceFor(datasetId).loadAggregates({
        field,
        ...(restrictToResultSource ? { filters: resultAvailabilityFilters.value } : {}),
      }),
    ),
  );
  const merged: Record<string, number> = {};
  for (const groups of groupResults) {
    for (const [value, count] of Object.entries(groups)) {
      merged[value] = (merged[value] ?? 0) + count;
    }
  }
  return merged;
}

function confirmSampling(): void {
  samplingEnabled.value = true;
  samplingVisible.value = false;
}

async function runExport(): Promise<void> {
  loading.value = true;
  result.value = null;
  statusMessage.value = t("sc.preparingExport");
  const datasetBody: ScPredictionExportRequest = {
    format: format.value,
    result_source: resultSource.value,
    ...(format.value === "parquet" ? {} : { klarf_version: klarfVersion.value }),
    include_images: format.value === "parquet" ? false : includeImages.value,
    sampling: samplingEnabled.value
      ? {
          seed: SC_SAMPLING_RANDOM_SEED,
          program: { rules: samplingProgram.value.rules },
          extra_filter: samplingProgram.value.extraFilterEnabled
            ? (toScWorkflowSampleFilter(samplingExtraFilter.value) ?? undefined)
            : undefined,
        }
      : null,
  };
  const body: ScPredictionExportRequest | ScCollectionPredictionExportRequest =
    isCollectionExport.value ? { ...datasetBody, member_ids: props.memberIds } : datasetBody;
  try {
    const path = isCollectionExport.value
      ? `/sc/dataset-collections/${encodeURIComponent(String(props.collectionId))}/prediction-exports/stream`
      : `/sc/datasets/${encodeURIComponent(String(props.datasetId))}/prediction-exports/stream`;
    const event = await streamApiSse(path, {
      method: "POST",
      body,
      onEvent: (item) => {
        if (item.event_type === "progress") {
          statusMessage.value = item.message || item.status || t("sc.exporting");
        }
      },
    });
    const payload = event?.payload ?? {};
    if (typeof payload.uri !== "string") throw new Error(t("sc.exportMissingUri"));
    result.value = {
      uri: payload.uri,
      rows: typeof payload.rows === "number" ? payload.rows : 0,
      format: typeof payload.format === "string" ? payload.format : format.value,
      filename: typeof payload.filename === "string" ? payload.filename : "prediction-export",
      sampled: payload.sampled === true,
      klarfVersion:
        payload.klarf_version === "1.2" || payload.klarf_version === "1.8"
          ? payload.klarf_version
          : null,
    };
    statusMessage.value = t("sc.exportComplete");
    message.success(t("sc.exportedRows", { count: formatNumber(result.value.rows) }));
  } catch (error) {
    message.error(toUserMessage(error, t("sc.exportFailed")));
    statusMessage.value = "";
  } finally {
    loading.value = false;
  }
}

function done(): void {
  props.onComplete({
    format: result.value?.format,
    url: result.value?.uri,
    message: result.value
      ? t("sc.exportedRows", { count: formatNumber(result.value.rows) })
      : undefined,
  });
}

onUnmounted(() => {
  for (const dataSource of dataSources.values()) dataSource.close();
});
</script>

<template>
  <div class="prediction-export" data-testid="sc-prediction-export" :style="exportSurfaceStyle">
    <n-card size="small" class="result-source-card">
      <div class="result-source-row">
        <div>
          <strong>{{ t("sc.exportedClass") }}</strong>
          <n-text depth="3">{{ activeResultSource.description }}</n-text>
        </div>
        <n-radio-group v-model:value="resultSource" :disabled="loading" size="small">
          <n-radio-button
            v-for="option in resultSourceOptions"
            :key="option.value"
            :value="option.value"
            :aria-label="t('sc.exportResultAria', { source: option.label })"
          >
            {{ option.label }}
          </n-radio-button>
        </n-radio-group>
      </div>
      <n-divider />
      <div class="distribution-row">
        <strong>{{ activeResultSource.label }} {{ t("sc.distribution") }}</strong>
        <n-spin v-if="distributionLoading" size="small" />
        <n-space v-else-if="distributionEntries.length" size="small">
          <n-tag v-for="entry in distributionEntries" :key="entry.value" size="small">
            {{ entry.value }} · {{ entry.count.toLocaleString() }} · {{ entry.percentage }}%
          </n-tag>
        </n-space>
        <n-text v-else depth="3">{{ t("sc.noClassifiedRows") }}</n-text>
      </div>
    </n-card>

    <div class="format-grid" role="radiogroup" :aria-label="t('sc.exportFormat')">
      <button
        v-for="option in formatOptions"
        :key="option.value"
        type="button"
        class="format-option"
        :class="{ selected: format === option.value }"
        :aria-checked="format === option.value"
        :disabled="loading"
        role="radio"
        @click="format = option.value"
      >
        <strong>{{ option.title }}</strong>
        <span>{{ option.description }}</span>
      </button>
    </div>

    <n-card v-if="format !== 'parquet'" size="small" class="klarf-version-card">
      <div class="klarf-version-row">
        <div>
          <strong>{{ t("sc.klarfVersion") }}</strong>
          <n-text depth="3">{{ t("sc.klarfVersionHelp") }}</n-text>
        </div>
        <n-radio-group v-model:value="klarfVersion" :disabled="loading" size="small">
          <n-radio-button value="1.2" :aria-label="t('sc.klarfVersionAria', { version: '1.2' })"
            >1.2</n-radio-button
          >
          <n-radio-button value="1.8" :aria-label="t('sc.klarfVersionAria', { version: '1.8' })"
            >1.8</n-radio-button
          >
        </n-radio-group>
      </div>
    </n-card>

    <n-card v-if="format !== 'parquet'" size="small" class="image-export-card">
      <div class="image-export-row">
        <div>
          <strong>{{ t("sc.includeDefectImages") }}</strong>
          <n-text depth="3">{{ t("sc.includeDefectImagesHelp") }}</n-text>
        </div>
        <n-switch
          v-model:value="includeImages"
          :disabled="loading"
          :aria-label="t('sc.includeDefectImages')"
        />
      </div>
    </n-card>

    <n-card size="small" class="sampling-card">
      <div class="sampling-row">
        <div>
          <strong>{{ t("sc.reviewSampling") }}</strong>
          <n-text depth="3">{{ samplingSummary }}</n-text>
        </div>
        <n-space align="center">
          <n-switch
            v-model:value="samplingEnabled"
            :disabled="loading"
            :aria-label="t('sc.applyReviewSampling')"
          />
          <n-button :loading="samplingLoading" :disabled="loading" @click="prepareSampling">
            {{ t("sc.configure") }}
          </n-button>
        </n-space>
      </div>
    </n-card>

    <n-text depth="3" class="export-note">
      <template v-if="isCollectionExport">
        {{ t("sc.collectionExportHelp") }}
      </template>
      <template v-else>{{ t("sc.largeExportHelp") }}</template>
    </n-text>

    <n-text v-if="statusMessage" depth="3">{{ statusMessage }}</n-text>

    <n-alert v-if="result" type="success" :title="t('sc.exportReady')">
      <div class="result-row">
        <span>
          {{ result.filename }} · {{ t("sc.resultRows", { count: formatNumber(result.rows) })
          }}<span v-if="result.klarfVersion"> · KLARF {{ result.klarfVersion }}</span>
        </span>
        <n-button
          tag="a"
          :href="buildExportDownloadUrl(result.uri)"
          download
          type="primary"
          size="small"
        >
          {{ t("jobDetail.download") }}
        </n-button>
      </div>
    </n-alert>

    <div class="actions">
      <n-button v-if="!props.embedded" @click="props.onCancel()">{{ t("widgets.close") }}</n-button>
      <n-button v-if="result && !props.embedded" type="success" @click="done">{{
        t("common.done")
      }}</n-button>
      <n-button v-else type="primary" :loading="loading" @click="runExport">
        {{ result ? t("sc.createAnotherExport") : t("sc.createExport") }}
      </n-button>
    </div>

    <ReviewSamplingModal
      v-model:show="samplingVisible"
      v-model:program="samplingProgram"
      v-model:scope="samplingScope"
      v-model:extra-filter="samplingExtraFilter"
      :title="t('sc.reviewSamplingExport')"
      :distribution-label="activeResultSource.label"
      :loading="samplingLoading"
      :available-count="samplingAvailableCount"
      :map-selection-count="0"
      :table-selection-available="false"
      :show-candidate-scope="false"
      :show-extra-filter="true"
      :extra-filter-distinct-values="extraFilterDistinctValues"
      :extra-filter-numeric-ranges="extraFilterNumericRanges"
      :extra-filter-numeric-range-loading="extraFilterNumericRangeLoading"
      :extra-filter-numeric-range-errors="extraFilterNumericRangeErrors"
      :load-groups="loadSamplingGroups"
      @search-extra-filter-options="searchExtraFilterOptions"
      @request-extra-filter-range="requestExtraFilterRange"
      @confirm="confirmSampling"
    />
  </div>
</template>

<style scoped>
.prediction-export {
  display: grid;
  gap: 16px;
}

.format-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 10px;
}

.result-source-row,
.distribution-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.result-source-row strong,
.result-source-row .n-text {
  display: block;
}

.result-source-row .n-text {
  margin-top: 4px;
}

.distribution-row > strong {
  flex: 0 0 auto;
}

.export-note {
  line-height: 1.5;
}

.format-option {
  min-height: 116px;
  padding: 14px;
  color: var(--prediction-export-text, #262626);
  text-align: left;
  background: var(--prediction-export-surface, #fff);
  border: 1px solid var(--prediction-export-border, #dedede);
  border-radius: 9px;
  cursor: pointer;
}

.format-option:hover,
.format-option.selected {
  border-color: var(--prediction-export-primary, #18a058);
}

.format-option:disabled {
  cursor: wait;
  opacity: 0.65;
}

.format-option.selected {
  background: var(--prediction-export-selected, #f0faf5);
  box-shadow: inset 0 0 0 1px var(--prediction-export-primary, #18a058);
}

.format-option strong,
.format-option span,
.klarf-version-row strong,
.klarf-version-row .n-text,
.image-export-row strong,
.image-export-row .n-text,
.sampling-row strong,
.sampling-row .n-text {
  display: block;
}

.format-option span,
.klarf-version-row .n-text,
.image-export-row .n-text,
.sampling-row .n-text {
  margin-top: 6px;
  color: var(--prediction-export-muted, #767676);
  font-size: 12px;
  line-height: 1.45;
}

.klarf-version-row,
.image-export-row,
.sampling-row,
.result-row,
.actions {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.actions {
  justify-content: flex-end;
}

@media (max-width: 720px) {
  .format-grid {
    grid-template-columns: 1fr;
  }

  .klarf-version-row,
  .image-export-row,
  .sampling-row,
  .result-source-row,
  .distribution-row,
  .result-row {
    align-items: stretch;
    flex-direction: column;
  }
}
</style>
