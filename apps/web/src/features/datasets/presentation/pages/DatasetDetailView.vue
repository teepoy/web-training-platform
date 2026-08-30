<script setup lang="ts">
import { computed, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import { useI18n } from "vue-i18n";
import { useQueryClient } from "@tanstack/vue-query";
import { FlowModal, SampleDetailDrawer, type FlowCard } from "@/shared";
import { widgetRegistry } from "@/app/registrations";
import {
  getGetDatasetApiV1DatasetsDatasetIdGetQueryKey,
  getGetSparseSummaryApiV1DatasetsDatasetIdSparseSummaryGetQueryKey,
  useGetDatasetApiV1DatasetsDatasetIdGet,
  useGetSparseSummaryApiV1DatasetsDatasetIdSparseSummaryGet,
} from "@/generated/orval/endpoints/api";
import type { Dataset, SparseSummaryResponse } from "@/generated/orval/models";
import { useOrgStore } from "@/features/auth/application/org";
import { orgScopedQueryKey } from "@/shared/api";
import DatasetTrainTab from "@/features/datasets/presentation/components/DatasetTrainTab.vue";
import DatasetPredictTab from "@/features/datasets/presentation/components/DatasetPredictTab.vue";
import DatasetPredictionExportTab from "@/features/datasets/presentation/components/DatasetPredictionExportTab.vue";
import DatasetViewPage from "@/features/datasets/presentation/pages/DatasetViewPage.vue";
import GlobalFilterControl from "@/features/sc/presentation/components/GlobalFilterControl.vue";
import { supportsScPredictionExport } from "@/features/sc/domain/predictionExportCapability";
import { formatDateTime, formatNumber } from "@/shared/i18n/format";

const route = useRoute();
const router = useRouter();
const qc = useQueryClient();
const orgStore = useOrgStore();
const { t } = useI18n();

const id = computed(() => String(route.params.id));
function tabFromHash(hash: string): string {
  return hash.startsWith("#") && hash.length > 1 ? hash.slice(1) : "overview";
}

const activeTab = ref(tabFromHash(route.hash));
const selectedSampleId = ref<string | null>(null);
const showImportFlow = ref(false);
const showExportFlow = ref(false);
const showAnnotationImportFlow = ref(false);
const showAnnotationExportFlow = ref(false);

const datasetQuery = useGetDatasetApiV1DatasetsDatasetIdGet(id, {
  query: {
    queryKey: computed(() =>
      orgScopedQueryKey(
        orgStore.currentOrgId,
        getGetDatasetApiV1DatasetsDatasetIdGetQueryKey(id.value),
      ),
    ),
    enabled: computed(() => !!orgStore.currentOrgId && !!id.value),
    retry: false,
  },
});

const dataset = computed(
  () => datasetQuery.data.value as Dataset & { ls_project_url?: string | null },
);

const isSparse = computed(() => dataset.value?.storage_mode === "file_shard_sparse");
const isScDataset = computed(
  () => dataset.value?.dataset_type === "image_sc" && dataset.value?.task_spec?.task_type === "sc",
);
const supportsPredictionExport = computed(() => supportsScPredictionExport(dataset.value ?? null));
const labelSpace = computed(() => dataset.value?.task_spec?.label_space ?? []);
const hasSampleBrowser = computed(() =>
  (dataset.value?.view_types ?? []).includes("image_input_v1"),
);
const hasDetailSampleBrowser = computed(() => hasSampleBrowser.value && !isScDataset.value);
const sparseSummaryQuery = useGetSparseSummaryApiV1DatasetsDatasetIdSparseSummaryGet(id, {
  query: {
    queryKey: computed(() =>
      orgScopedQueryKey(
        orgStore.currentOrgId,
        getGetSparseSummaryApiV1DatasetsDatasetIdSparseSummaryGetQueryKey(id.value),
      ),
    ),
    enabled: computed(() => !!orgStore.currentOrgId && !!id.value && isSparse.value),
    retry: false,
  },
});
const sparseSummary = computed(
  () => (sparseSummaryQuery.data.value as SparseSummaryResponse | undefined) ?? null,
);
const sampleCount = computed<number | null>(() => {
  const sparseTotal = sparseSummary.value?.manifest.total_rows;
  if (typeof sparseTotal === "number") return sparseTotal;
  const metadataTotal = dataset.value?.dataset_meta?.total_samples;
  return typeof metadataTotal === "number" ? metadataTotal : null;
});
const datasetKindLabel = computed(() => {
  if (isScDataset.value) return t("datasetDetail.patchInspection");
  if (dataset.value?.dataset_type === "image_classification")
    return t("datasetDetail.imageClassification");
  const value = dataset.value?.dataset_type?.replace(/_/g, " ").trim();
  return value || t("datasetDetail.dataset");
});

const availableTabs = computed(() => {
  const value = dataset.value;
  if (!value) return [];
  return [
    "overview",
    ...(hasDetailSampleBrowser.value ? ["samples"] : []),
    "train",
    "predict",
    "export",
    ...(value.storage_mode !== "file_shard_sparse" ? ["annotate"] : []),
  ];
});

watch(
  [dataset, () => route.hash],
  ([value, hash]) => {
    if (!value) return;
    const requestedTab = tabFromHash(hash);
    if (isScDataset.value && (requestedTab === "classify" || requestedTab === "samples")) {
      openScClassify();
      return;
    }
    const nextTab = availableTabs.value.includes(requestedTab) ? requestedTab : "overview";
    if (activeTab.value !== nextTab) activeTab.value = nextTab;
    const canonicalHash = `#${nextTab}`;
    if (route.hash && route.hash !== canonicalHash) void router.replace({ hash: canonicalHash });
  },
  { immediate: true },
);

watch(activeTab, (tab) => {
  if (!availableTabs.value.includes(tab)) return;
  const hash = `#${tab}`;
  if (route.hash !== hash) void router.replace({ hash });
});

function localizedFlows(
  descriptors: Array<{
    id: string;
    label: string;
    labelKey?: string;
    description?: string;
    descriptionKey?: string;
    icon?: string;
    component: FlowCard["component"];
  }>,
): FlowCard[] {
  return descriptors.map((descriptor) => ({
    id: descriptor.id,
    label: descriptor.labelKey ? t(descriptor.labelKey) : descriptor.label,
    description: descriptor.descriptionKey ? t(descriptor.descriptionKey) : descriptor.description,
    icon: descriptor.icon,
    component: descriptor.component,
  }));
}

const importerFlows = computed(() => localizedFlows(widgetRegistry.getImporters("dataset")));
const exporterFlows = computed(() => localizedFlows(widgetRegistry.getExporters("dataset")));
const annotationImporterFlows = computed(() =>
  localizedFlows(widgetRegistry.getImporters("annotation")),
);
const annotationExporterFlows = computed(() =>
  localizedFlows(widgetRegistry.getExporters("annotation")),
);

function handleImporterComplete() {
  showImportFlow.value = false;
  activeTab.value = hasDetailSampleBrowser.value ? "samples" : "overview";
  qc.invalidateQueries({
    queryKey: orgScopedQueryKey(orgStore.currentOrgId, ["view-samples", id.value]),
  });
  qc.invalidateQueries({
    queryKey: orgScopedQueryKey(orgStore.currentOrgId, ["feature-samples", id.value]),
  });
}

function openScClassify() {
  void router.push({ name: "sc-reclassify", params: { id: id.value } });
}

function handleTabBeforeLeave(name: string | number): boolean {
  if (name !== "classify") return true;
  openScClassify();
  return false;
}
</script>

<template>
  <div class="dataset-detail-page">
    <n-spin
      v-if="datasetQuery.isLoading.value"
      style="display: flex; justify-content: center; padding: 48px"
    />
    <n-result
      v-else-if="datasetQuery.isError.value || !datasetQuery.data.value"
      status="404"
      :title="t('datasetDetail.notFound')"
      :description="t('datasetDetail.notFoundHelp')"
    >
      <template #footer
        ><n-button @click="router.push('/datasets')">{{
          t("datasetDetail.back")
        }}</n-button></template
      >
    </n-result>

    <template v-else>
      <header class="dataset-detail-header">
        <div class="dataset-heading">
          <n-button text class="back-button" @click="router.push('/datasets')">
            <template #icon><span aria-hidden="true">&#8592;</span></template>
            {{ t("datasetDetail.datasets") }}
          </n-button>
          <div class="dataset-title-block">
            <div class="dataset-title-line">
              <h1>{{ dataset.name }}</h1>
              <n-tag size="small" :bordered="false">{{ datasetKindLabel }}</n-tag>
            </div>
          </div>
        </div>
      </header>

      <GlobalFilterControl v-if="isScDataset" :dataset-id="id" />

      <n-tabs
        v-model:value="activeTab"
        type="line"
        animated
        class="dataset-tabs"
        :on-before-leave="handleTabBeforeLeave"
      >
        <n-tab-pane name="overview" :tab="t('datasetDetail.overview')">
          <n-card size="small" :title="t('datasetDetail.about')" class="dataset-overview-card">
            <div class="dataset-overview-grid">
              <div class="overview-field">
                <n-text depth="3">{{ t("datasetDetail.purpose") }}</n-text>
                <strong>{{ datasetKindLabel }}</strong>
              </div>
              <div class="overview-field">
                <n-text depth="3">{{ t("datasetDetail.samples") }}</n-text>
                <strong>{{ sampleCount === null ? "—" : formatNumber(sampleCount) }}</strong>
              </div>
              <div class="overview-field">
                <n-text depth="3">{{ t("datasetDetail.createdBy") }}</n-text>
                <strong>{{
                  dataset.creator_name || dataset.created_by || t("common.system")
                }}</strong>
              </div>
              <div class="overview-field">
                <n-text depth="3">{{ t("datasetDetail.created") }}</n-text>
                <strong>{{ dataset.created_at ? formatDateTime(dataset.created_at) : "—" }}</strong>
              </div>
              <div class="overview-field overview-field-wide">
                <n-text depth="3">{{ t("datasetDetail.labels") }}</n-text>
                <n-space v-if="labelSpace.length" size="small">
                  <n-tag v-for="label in labelSpace" :key="label" size="small">
                    {{ label }}
                  </n-tag>
                </n-space>
                <n-text v-else depth="3">{{ t("datasetDetail.noLabels") }}</n-text>
              </div>
            </div>
          </n-card>
        </n-tab-pane>
        <n-tab-pane v-if="isScDataset" name="classify">
          <template #tab>
            <span>{{ t("datasetDetail.classify") }}</span>
          </template>
        </n-tab-pane>
        <n-tab-pane v-else-if="hasSampleBrowser" name="samples" :tab="t('datasetDetail.samples')">
          <DatasetViewPage
            :dataset-id="id"
            view-type="image_input_v1"
            @select-sample="selectedSampleId = $event"
          />
        </n-tab-pane>
        <n-tab-pane name="train" :tab="t('datasetDetail.train')">
          <DatasetTrainTab :dataset-id="id" :dataset="dataset" />
        </n-tab-pane>
        <n-tab-pane name="predict" :tab="t('datasetDetail.predict')">
          <DatasetPredictTab :dataset-id="id" :compatible-view-types="dataset.view_types ?? []" />
        </n-tab-pane>
        <n-tab-pane name="export" :tab="t('datasetDetail.export')">
          <DatasetPredictionExportTab
            :dataset-id="id"
            :allow-sample-import="!isSparse"
            :show-prediction-export="supportsPredictionExport"
            @import-samples="showImportFlow = true"
            @export-dataset="showExportFlow = true"
            @import-annotations="showAnnotationImportFlow = true"
            @export-annotations="showAnnotationExportFlow = true"
          />
        </n-tab-pane>
        <n-tab-pane v-if="!isSparse" name="annotate" :tab="t('datasetDetail.annotate')">
          <template v-if="dataset?.ls_project_url"
            ><iframe
              :src="dataset.ls_project_url"
              class="annotation-frame"
              allow="clipboard-read; clipboard-write"
            />
            <div style="margin-top: 8px; display: flex; align-items: center; gap: 8px">
              <n-text depth="3" style="font-size: 12px">{{
                t("datasetDetail.labelStudioProject", { id: dataset.ls_project_id })
              }}</n-text
              ><n-button text size="small" tag="a" :href="dataset.ls_project_url" target="_blank">{{
                t("datasetDetail.openNewTab")
              }}</n-button>
            </div></template
          >
          <n-result
            v-else
            status="info"
            :title="t('datasetDetail.labelStudioMissing')"
            :description="t('datasetDetail.labelStudioMissingHelp')"
          />
        </n-tab-pane>
      </n-tabs>

      <SampleDetailDrawer
        :sampleId="selectedSampleId"
        :datasetId="id"
        :labelSpace="labelSpace"
        :sparse="isSparse"
        :show="selectedSampleId !== null"
        @close="selectedSampleId = null"
        @select-sample="
          (sid: string) => {
            selectedSampleId = sid;
          }
        "
      />
      <FlowModal
        v-model:show="showImportFlow"
        :flows="importerFlows"
        kind="import"
        :title="t('datasetDetail.importSamples')"
        :dataset-id="id"
        @complete="handleImporterComplete"
      />
      <FlowModal
        v-model:show="showExportFlow"
        :flows="exporterFlows"
        kind="export"
        :title="t('datasetDetail.exportDataset')"
        :dataset-id="id"
      />
      <FlowModal
        v-model:show="showAnnotationImportFlow"
        :flows="annotationImporterFlows"
        kind="import"
        :title="t('datasetDetail.importAnnotations')"
        :dataset-id="id"
        @complete="handleImporterComplete"
      />
      <FlowModal
        v-model:show="showAnnotationExportFlow"
        :flows="annotationExporterFlows"
        kind="export"
        :title="t('datasetDetail.exportAnnotations')"
        :dataset-id="id"
      />
    </template>
  </div>
</template>

<style scoped>
.dataset-detail-page {
  min-width: 0;
}

.dataset-detail-header {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: 20px;
  margin-bottom: 20px;
}

.dataset-heading {
  min-width: 0;
}

.back-button {
  margin-bottom: 8px;
}

.dataset-title-block {
  min-width: 0;
}

.dataset-title-line {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 10px;
}

.dataset-title-line h1 {
  min-width: 0;
  margin: 0;
  overflow-wrap: anywhere;
  font-size: 26px;
  line-height: 1.25;
}

.dataset-tabs {
  margin-top: 16px;
}

.dataset-overview-card {
  margin-top: 4px;
}

.dataset-overview-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 20px 28px;
}

.overview-field {
  display: flex;
  min-width: 0;
  flex-direction: column;
  gap: 5px;
}

.overview-field strong {
  overflow-wrap: anywhere;
  font-weight: 600;
}

.overview-field-wide {
  grid-column: 1 / -1;
}

.annotation-frame {
  width: 100%;
  height: calc(100vh - 240px);
  min-height: 520px;
  border: 1px solid var(--n-border-color, #e5e7eb);
  border-radius: 8px;
}

@media (max-width: 720px) {
  .dataset-detail-header {
    align-items: stretch;
    flex-direction: column;
    gap: 14px;
  }

  .dataset-overview-grid {
    grid-template-columns: 1fr;
  }

  .overview-field-wide {
    grid-column: auto;
  }

  .annotation-frame {
    height: calc(100vh - 280px);
    min-height: 420px;
  }
}
</style>
