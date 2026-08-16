<script setup lang="ts">
import { computed, ref } from "vue";
import {
  NButton,
  NInput,
  NModal,
  NProgress,
  NSpace,
  NText,
  useMessage,
  useThemeVars,
} from "naive-ui";
import ScSummaryTab from "@/features/sc/presentation/components/ScSummaryTab.vue";
import { useRouter } from "vue-router";
import { FullScreenLayout } from "@/shared/components/full-screen-layout";
import { usePreviewPage } from "@/features/sc/application/usePreviewPage";
import type { InspectionSummaryItem } from "@/features/sc/domain/models";
import {
  createCollectionApiV1DatasetCollectionsPost,
  linkMembersApiV1DatasetCollectionsCollectionIdMembersPost,
} from "@/generated/orval/endpoints/api";
import { toUserMessage } from "@/shared/api";

const page = usePreviewPage();
const router = useRouter();
const themeVars = useThemeVars();
const message = useMessage();
const selectedInspectionKeys = ref<string[]>([]);
const collectionModalVisible = ref(false);
const collectionName = ref("");
const isBuildingCollection = ref(false);
const completedImports = ref(0);

const selectedInspections = computed(() => {
  const selected = new Set(selectedInspectionKeys.value);
  return page.summaries.value.filter((item) => selected.has(page.rowKey(item)));
});
const collectionProgress = computed(() =>
  selectedInspections.value.length === 0
    ? 0
    : Math.round((completedImports.value / selectedInspections.value.length) * 100),
);

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

function openInspectionInNewTab(row: InspectionSummaryItem): void {
  page.lastOpenedSummaryKey.value = page.rowKey(row);
  const target = router.resolve({
    name: "sc-inspection",
    params: {
      inspectionTime: row.inspection_time,
      waferKey: String(row.wafer_key),
    },
  });
  window.open(target.href, "_blank", "noopener");
}

function openDataset(datasetId: string): void {
  const target = router.resolve(`/datasets/${datasetId}`);
  window.open(target.href, "_blank", "noopener");
}

async function createDataset(row: InspectionSummaryItem): Promise<void> {
  try {
    await page.importInspection(row);
  } catch {
    // importInspection already records and surfaces the transport error.
  }
}

function openCollectionModal(): void {
  if (selectedInspections.value.length === 0) return;
  const first = selectedInspections.value[0];
  collectionName.value = first
    ? `Patch collection ${first.lot_id} (${selectedInspections.value.length})`
    : "";
  completedImports.value = 0;
  collectionModalVisible.value = true;
}

async function buildCollection(): Promise<void> {
  const name = collectionName.value.trim();
  if (!name || selectedInspections.value.length === 0 || isBuildingCollection.value) return;
  isBuildingCollection.value = true;
  completedImports.value = 0;
  try {
    const datasetIds: string[] = [];
    for (const inspection of selectedInspections.value) {
      datasetIds.push(await page.importInspection(inspection, false));
      completedImports.value += 1;
    }
    const collection = await createCollectionApiV1DatasetCollectionsPost({
      name,
      description: `Imported from ${selectedInspections.value.length} SC inspections`,
      target_view_id: "patch_image_v1",
      duplicate_policy: "keep_all",
      missing_data_policy: "fail",
    });
    await linkMembersApiV1DatasetCollectionsCollectionIdMembersPost(collection.id, {
      expected_definition_version: collection.definition_version,
      members: datasetIds.map((sourceDatasetId, position) => ({
        source_dataset_id: sourceDatasetId,
        position,
        filter_spec: {},
        label_mapping: {},
        sampling_spec: {},
      })),
    });
    message.success(`Collection created with ${datasetIds.length} datasets`);
    collectionModalVisible.value = false;
    selectedInspectionKeys.value = [];
    await router.push(`/dataset-collections/${collection.id}`);
  } catch (error) {
    message.error(toUserMessage(error, "Failed to build dataset collection"));
  } finally {
    isBuildingCollection.value = false;
  }
}
</script>

<template>
  <FullScreenLayout>
    <div class="sc-preview" :style="containerStyle">
      <div class="sc-preview-body">
        <div class="sc-preview-tab-bar">
          <div class="sc-preview-title">Summary</div>
          <div class="sc-preview-toolbar">
            <NButton size="small" quaternary @click="router.push('/sc/handbook')">
              Handbook
            </NButton>
          </div>
        </div>

        <div class="sc-preview-tab-content">
          <ScSummaryTab
            :date-range="page.dateRange.value"
            :summaries-loading="page.summariesLoading.value"
            :summaries-error="page.summariesError.value"
            :summaries-empty="page.summariesEmpty.value"
            :summaries="page.summaries.value"
            :inspection-columns="page.inspectionColumns.value"
            :last-opened-summary-key="page.lastOpenedSummaryKey.value"
            :last-opened-summary-label="page.lastOpenedSummaryLabel.value"
            :lot-id-filter="page.lotIdFilter.value"
            :eqp-id-filter="page.eqpIdFilter.value"
            :layer-id-filter="page.layerIdFilter.value"
            :device-filter="page.deviceFilter.value"
            :selected-row-keys="selectedInspectionKeys"
            :importing-inspection-key="page.importingInspectionKey.value"
            @update:date-range="page.dateRange.value = $event"
            @update:lot-id-filter="page.lotIdFilter.value = $event"
            @update:eqp-id-filter="page.eqpIdFilter.value = $event"
            @update:layer-id-filter="page.layerIdFilter.value = $event"
            @update:device-filter="page.deviceFilter.value = $event"
            @update:selected-row-keys="selectedInspectionKeys = $event"
            @search="page.searchInspections()"
            @row-click="openInspectionInNewTab"
            @open-dataset="openDataset"
            @create-dataset="createDataset"
            @build-collection="openCollectionModal"
          />
        </div>
      </div>
    </div>

    <NModal
      v-model:show="collectionModalVisible"
      preset="card"
      title="Import inspections as a collection"
      :style="{ width: '520px' }"
      :mask-closable="!isBuildingCollection"
    >
      <NInput
        v-model:value="collectionName"
        placeholder="Collection name"
        :disabled="isBuildingCollection"
      />
      <NText depth="3" class="collection-modal-copy">
        Each selected inspection is imported as a standalone dataset, then dynamically linked to the
        collection.
      </NText>
      <NProgress
        v-if="isBuildingCollection"
        type="line"
        :percentage="collectionProgress"
        :indicator-placement="'inside'"
        processing
      />
      <template #footer>
        <NSpace justify="end">
          <NButton :disabled="isBuildingCollection" @click="collectionModalVisible = false">
            Cancel
          </NButton>
          <NButton
            type="primary"
            :disabled="!collectionName.trim()"
            :loading="isBuildingCollection"
            @click="buildCollection"
          >
            Import &amp; create
          </NButton>
        </NSpace>
      </template>
    </NModal>
  </FullScreenLayout>
</template>

<style scoped>
.sc-preview {
  display: flex;
  flex-direction: column;
  flex: 1;
  min-height: 0;
  overflow: hidden;
  padding: 12px 16px;
  background: var(--cv-bg, #0f0f1a);
  color: var(--cv-text, #fff);
}

.sc-preview-body {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.sc-preview-tab-bar {
  display: flex;
  flex-shrink: 0;
  align-items: center;
  justify-content: space-between;
  gap: 2px;
  background: var(--cv-card-bg, #1a1a2e);
  border-bottom: 1px solid var(--cv-border, rgba(255, 255, 255, 0.1));
  padding: 0 4px;
}

.sc-preview-toolbar {
  display: flex;
  align-items: center;
  flex-shrink: 0;
  padding-left: 12px;
  gap: 8px;
}

.collection-modal-copy {
  display: block;
  margin: 12px 0;
}

.sc-preview-title {
  min-width: 0;
  padding: 6px 8px;
  color: var(--cv-text, #fff);
  font-size: 13px;
  font-weight: 600;
}

.sc-preview-tab-content {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}
</style>
