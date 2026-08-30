<script setup lang="ts">
import { widgetRegistry } from "@/app/registrations";
import { useI18n } from "vue-i18n";

const props = withDefaults(
  defineProps<{
    datasetId: string;
    allowSampleImport?: boolean;
    showPredictionExport?: boolean;
  }>(),
  {
    allowSampleImport: false,
    showPredictionExport: true,
  },
);
const emit = defineEmits<{
  importSamples: [];
  exportDataset: [];
  importAnnotations: [];
  exportAnnotations: [];
}>();
const { t } = useI18n();
const exporter =
  widgetRegistry
    .getExporters("prediction")
    .find((candidate) => candidate.id === "sc-prediction-results-v1") ?? null;

function ignoreExportCompletion(): void {}
</script>

<template>
  <section class="prediction-export-tab" data-testid="dataset-prediction-export-tab">
    <n-space :wrap="true">
      <n-button v-if="props.allowSampleImport" @click="emit('importSamples')">
        {{ t("datasetDetail.addSamples") }}
      </n-button>
      <n-button @click="emit('exportDataset')">
        {{ t("datasetDetail.exportDataset") }}
      </n-button>
      <n-button @click="emit('importAnnotations')">
        {{ t("datasetDetail.importAnnotations") }}
      </n-button>
      <n-button @click="emit('exportAnnotations')">
        {{ t("datasetDetail.exportAnnotations") }}
      </n-button>
    </n-space>

    <header v-if="props.showPredictionExport && exporter" class="export-heading">
      <div>
        <n-text depth="3" class="eyebrow">{{ t("common.export") }}</n-text>
        <n-h3>{{ t("datasetFlows.exportResults") }}</n-h3>
        <n-text depth="3">
          {{ t("datasetFlows.predictionExportHelp") }}
        </n-text>
      </div>
    </header>

    <component
      :is="exporter.component"
      v-if="props.showPredictionExport && exporter"
      :dataset-id="props.datasetId"
      :on-complete="ignoreExportCompletion"
      :on-cancel="ignoreExportCompletion"
      embedded
    />
  </section>
</template>

<style scoped>
.prediction-export-tab {
  display: grid;
  gap: 18px;
  box-sizing: border-box;
  max-width: 1064px;
  padding: 20px 84px 96px 0;
}

.export-heading h3 {
  margin: 4px 0;
}

.eyebrow {
  font-size: 12px;
  font-weight: 700;
  letter-spacing: 0.12em;
  text-transform: uppercase;
}

@media (max-width: 720px) {
  .prediction-export-tab {
    padding-right: 0;
  }
}
</style>
