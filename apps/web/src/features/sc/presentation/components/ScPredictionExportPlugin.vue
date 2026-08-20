<script setup lang="ts">
import { computed, onUnmounted, ref } from "vue";
import { useMessage, useThemeVars } from "naive-ui";
import type {
  ScCollectionPredictionExportRequest,
  ScKlarfVersion,
  ScPredictionExportRequest,
} from "@/generated/orval/models";
import type { ExporterResult } from "@/shared/widgets/sdk";
import { buildExportDownloadUrl } from "@/shared/api/datasets";
import { streamApiSse } from "@/shared/api/sse";
import { toUserMessage } from "@/shared/api";
import type { ScSamplingCandidateScope } from "@/features/sc/application/inspectionFilterPolicy";
import { SqlWorkbenchDataSource } from "@/features/sc/api/sqlWorkbenchDataSource";
import { emptyScGlobalFilter } from "@/features/sc/domain/globalFilter";
import {
  createDefaultScSamplingProgram,
  SC_SAMPLING_RANDOM_SEED,
  type ScSamplingGroupPopulation,
  type ScSamplingProgram,
} from "@/features/sc/domain/samplingRules";
import ReviewSamplingModal from "./ReviewSamplingModal.vue";

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
const klarfVersion = ref<ScKlarfVersion>("1.2");
const includeImages = ref(false);
const loading = ref(false);
const statusMessage = ref("");
const samplingEnabled = ref(false);
const samplingVisible = ref(false);
const samplingLoading = ref(false);
const samplingAvailableCount = ref(0);
const samplingProgram = ref<ScSamplingProgram>(createDefaultScSamplingProgram());
const samplingScope = ref<ScSamplingCandidateScope>("all");
const samplingExtraFilter = ref(emptyScGlobalFilter());
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

const formatOptions = [
  {
    value: "parquet" as const,
    title: "Parquet",
    description: "Columnar current results for analytics and downstream processing.",
  },
  {
    value: "klarf" as const,
    title: "KLARF",
    description: "One complete numbered .000/.001 file per inspection, using Final Class.",
  },
  {
    value: "zip" as const,
    title: "ZIP package",
    description:
      "Combined Parquet, inspection-level KLARF files, and a manifest. Defect images are optional.",
  },
];
const samplingSummary = computed(() =>
  samplingEnabled.value
    ? `${samplingProgram.value.rules.length} rules · seed ${SC_SAMPLING_RANDOM_SEED}`
    : "All current Dataset rows",
);

async function prepareSampling(): Promise<void> {
  samplingLoading.value = true;
  try {
    const groups = await loadMergedGroups("wafer_key");
    samplingAvailableCount.value = Object.values(groups).reduce((sum, count) => sum + count, 0);
    samplingVisible.value = true;
  } catch (error) {
    message.error(toUserMessage(error, "Failed to prepare Annotation Sampling"));
  } finally {
    samplingLoading.value = false;
  }
}

async function loadSamplingGroups(field: string): Promise<ScSamplingGroupPopulation[]> {
  const groups = await loadMergedGroups(field);
  return Object.entries(groups).map(([value, count]) => ({ value, count }));
}

function sourceFor(datasetId: string): SqlWorkbenchDataSource {
  const existing = dataSources.get(datasetId);
  if (existing) return existing;
  const source = new SqlWorkbenchDataSource({ kind: "dataset", datasetId });
  dataSources.set(datasetId, source);
  return source;
}

async function loadMergedGroups(field: string): Promise<Record<string, number>> {
  if (targetDatasetIds.value.length === 0) {
    throw new Error("No Dataset records are selected for export");
  }
  const groupResults = await Promise.all(
    targetDatasetIds.value.map((datasetId) => sourceFor(datasetId).loadAggregates({ field })),
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
  statusMessage.value = "Preparing current prediction results...";
  const datasetBody: ScPredictionExportRequest = {
    format: format.value,
    ...(format.value === "parquet" ? {} : { klarf_version: klarfVersion.value }),
    include_images: format.value === "parquet" ? false : includeImages.value,
    sampling: samplingEnabled.value
      ? {
          seed: SC_SAMPLING_RANDOM_SEED,
          program: { rules: samplingProgram.value.rules },
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
          statusMessage.value = item.message || item.status || "Exporting...";
        }
      },
    });
    const payload = event?.payload ?? {};
    if (typeof payload.uri !== "string") throw new Error("Prediction export returned no URI");
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
    statusMessage.value = "Export complete";
    message.success(`Exported ${result.value.rows.toLocaleString()} rows`);
  } catch (error) {
    message.error(toUserMessage(error, "Prediction export failed"));
    statusMessage.value = "";
  } finally {
    loading.value = false;
  }
}

function done(): void {
  props.onComplete({
    format: result.value?.format,
    url: result.value?.uri,
    message: result.value ? `Exported ${result.value.rows.toLocaleString()} rows` : undefined,
  });
}

onUnmounted(() => {
  for (const dataSource of dataSources.values()) dataSource.close();
});
</script>

<template>
  <div class="prediction-export" data-testid="sc-prediction-export" :style="exportSurfaceStyle">
    <div class="format-grid" role="radiogroup" aria-label="Export format">
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
          <strong>KLARF version</strong>
          <n-text depth="3">Applies to every numbered KLARF file in this export.</n-text>
        </div>
        <n-radio-group v-model:value="klarfVersion" :disabled="loading" size="small">
          <n-radio-button value="1.2" aria-label="KLARF version 1.2">1.2</n-radio-button>
          <n-radio-button value="1.8" aria-label="KLARF version 1.8">1.8</n-radio-button>
        </n-radio-group>
      </div>
    </n-card>

    <n-card v-if="format !== 'parquet'" size="small" class="image-export-card">
      <div class="image-export-row">
        <div>
          <strong>Include defect images</strong>
          <n-text depth="3">
            Adds one defective patch for every row retained after Annotation Sampling. The result is
            packaged as ZIP.
          </n-text>
        </div>
        <n-switch
          v-model:value="includeImages"
          :disabled="loading"
          aria-label="Include defect images"
        />
      </div>
    </n-card>

    <n-card size="small" class="sampling-card">
      <div class="sampling-row">
        <div>
          <strong>Annotation Sampling</strong>
          <n-text depth="3">{{ samplingSummary }}</n-text>
        </div>
        <n-space align="center">
          <n-switch
            v-model:value="samplingEnabled"
            :disabled="loading"
            aria-label="Apply Annotation Sampling"
          />
          <n-button :loading="samplingLoading" :disabled="loading" @click="prepareSampling">
            Configure
          </n-button>
        </n-space>
      </div>
    </n-card>

    <n-alert type="info" :show-icon="false">
      <template v-if="isCollectionExport">
        Parquet combines the selected Collection records. KLARF groups their rows by inspection and
        creates complete numbered files; it does not split files by byte size.
      </template>
      <template v-else>
        Exports use the Dataset's current accumulated prediction state. A newer run can replace the
        current result for individual samples.
      </template>
    </n-alert>

    <n-alert type="warning" title="Large exports may take several minutes">
      Packages can exceed 100 MB. Keep this tab open until the download link appears. Generation
      sends periodic progress, uploads use multipart object storage, and downloads are streamed in
      bounded chunks with byte-range resume support.
    </n-alert>

    <n-text v-if="statusMessage" depth="3">{{ statusMessage }}</n-text>

    <n-alert v-if="result" type="success" title="Export ready">
      <div class="result-row">
        <span>
          {{ result.filename }} · {{ result.rows.toLocaleString() }} rows<span
            v-if="result.klarfVersion"
          >
            · KLARF {{ result.klarfVersion }}</span
          >
        </span>
        <n-button
          tag="a"
          :href="buildExportDownloadUrl(result.uri)"
          download
          type="primary"
          size="small"
        >
          Download
        </n-button>
      </div>
    </n-alert>

    <div class="actions">
      <n-button v-if="!props.embedded" @click="props.onCancel()">Close</n-button>
      <n-button v-if="result && !props.embedded" type="success" @click="done">Done</n-button>
      <n-button v-else type="primary" :loading="loading" @click="runExport">
        {{ result ? "Create another export" : "Create export" }}
      </n-button>
    </div>

    <ReviewSamplingModal
      v-model:show="samplingVisible"
      v-model:program="samplingProgram"
      v-model:scope="samplingScope"
      v-model:extra-filter="samplingExtraFilter"
      title="Annotation Sampling for export"
      :loading="samplingLoading"
      :available-count="samplingAvailableCount"
      :map-selection-count="0"
      :table-selection-available="false"
      :show-candidate-scope="false"
      :show-extra-filter="false"
      :load-groups="loadSamplingGroups"
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
  .result-row {
    align-items: stretch;
    flex-direction: column;
  }
}
</style>
