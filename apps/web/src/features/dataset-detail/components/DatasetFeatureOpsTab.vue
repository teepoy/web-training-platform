<script setup lang="ts">
import { computed } from "vue";
import { NAlert, NButton, NCard, NDataTable, NFormItem, NSelect, NSpace, NStatistic, NTag, NText } from "naive-ui";
import { useFeatureOps } from "../composables/useFeatureOps";

const props = defineProps<{
  datasetId: string;
  isSparse: boolean;
}>();

const datasetIdRef = computed(() => props.datasetId);
const featureOps = useFeatureOps({ datasetId: datasetIdRef });
</script>

<template>
  <n-space vertical size="large">
    <n-card title="Embedding Config" size="small">
      <n-space vertical size="medium">
        <n-form-item label="Embedding Model">
          <n-select
            v-model:value="featureOps.embedConfigModel.value"
            :options="[{ label: 'CLIP ViT-B/32 (512-dim)', value: 'openai/clip-vit-base-patch32' }]"
            style="width: 320px"
          />
        </n-form-item>
        <n-button type="primary" :loading="featureOps.embedConfigLoading.value" @click="featureOps.doApplyEmbedConfig">
          Apply &amp; Re-embed
        </n-button>
        <n-alert v-if="featureOps.embedConfigSaved.value" type="success" :show-icon="false" style="margin-top: 8px">
          Config saved. Re-embedding started in background.
        </n-alert>
      </n-space>
    </n-card>

    <n-card title="Extract Features" size="small">
      <n-button type="primary" :loading="featureOps.extractFeaturesLoading.value" :disabled="isSparse" @click="featureOps.doExtractFeatures">
        Extract Features
      </n-button>
      <n-text v-if="isSparse" depth="3" style="display: block; margin-top: 4px; font-size: 12px">
        Not available for sparse datasets.
      </n-text>
      <template v-if="featureOps.extractFeaturesResult.value">
        <n-space style="margin-top: 16px">
          <n-statistic label="Job" :value="featureOps.extractFeaturesResult.value.id" />
          <n-statistic label="Status" :value="featureOps.extractFeaturesResult.value.status" />
          <n-statistic label="Processed" :value="Number(featureOps.extractFeaturesResult.value.summary.processed || 0)" />
        </n-space>
        <n-text depth="3" style="display: block; margin-top: 8px">
          Embedding model: {{ String(featureOps.extractFeaturesResult.value.summary.embedding_model || featureOps.embedConfigModel.value) }}
        </n-text>
      </template>
    </n-card>

    <n-card title="Similarity Search" size="small">
      <template #header-extra>
        <n-tag type="warning">Mock Data</n-tag>
      </template>
      <n-space align="center">
        <n-select
          v-model:value="featureOps.similaritySampleId.value"
          :options="featureOps.sampleSelectOptions.value"
          placeholder="Select a sample"
          style="width: 280px"
          clearable
        />
        <n-button
          type="primary"
          :loading="featureOps.similarityLoading.value"
          :disabled="!featureOps.similaritySampleId.value"
          @click="featureOps.doSimilaritySearch"
        >
          Search
        </n-button>
      </n-space>
      <n-data-table
        v-if="featureOps.similarityResult.value"
        :columns="featureOps.neighborColumns"
        :data="featureOps.similarityResult.value.neighbors"
        :bordered="true"
        :single-line="false"
        style="margin-top: 16px"
      />
    </n-card>

    <n-card title="Selection Metrics" size="small">
      <template #header-extra>
        <n-tag type="warning">Mock Data</n-tag>
      </template>
      <n-button type="primary" :loading="featureOps.selectionMetricsLoading.value" :disabled="isSparse" @click="featureOps.doSelectionMetrics">
        Load Selection Metrics
      </n-button>
      <n-text v-if="isSparse" depth="3" style="display: block; margin-top: 4px; font-size: 12px">
        Not available for sparse datasets.
      </n-text>
      <n-data-table
        v-if="featureOps.selectionMetricsRows.value.length > 0"
        :columns="featureOps.selectionMetricsColumns"
        :data="featureOps.selectionMetricsRows.value"
        :bordered="true"
        :single-line="false"
        style="margin-top: 16px"
      />
    </n-card>

    <n-card title="Uncovered Clusters" size="small">
      <template #header-extra>
        <n-tag type="warning">Mock Data</n-tag>
      </template>
      <n-button type="primary" :loading="featureOps.uncoveredClustersLoading.value" @click="featureOps.doUncoveredClusters">
        Load Uncovered Clusters
      </n-button>
      <n-data-table
        v-if="featureOps.uncoveredClustersResult.value"
        :columns="featureOps.clusterColumns"
        :data="featureOps.uncoveredClustersResult.value.clusters"
        :bordered="true"
        :single-line="false"
        style="margin-top: 16px"
      />
    </n-card>
  </n-space>
</template>
