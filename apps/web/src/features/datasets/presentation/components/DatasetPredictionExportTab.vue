<script setup lang="ts">
import { widgetRegistry } from "@/app/registrations";
import { useI18n } from "vue-i18n";

const props = defineProps<{ datasetId: string }>();
const { t } = useI18n();
const exporter =
  widgetRegistry
    .getExporters("prediction")
    .find((candidate) => candidate.id === "sc-prediction-results-v1") ?? null;

function ignoreExportCompletion(): void {}
</script>

<template>
  <section class="prediction-export-tab" data-testid="dataset-prediction-export-tab">
    <header class="export-heading">
      <div>
        <n-text depth="3" class="eyebrow">{{ t("common.export") }}</n-text>
        <n-h3>{{ t("datasetFlows.exportResults") }}</n-h3>
        <n-text depth="3">
          Choose the class result, optional Review Sampling, and file format.
        </n-text>
      </div>
    </header>

    <n-empty v-if="!exporter" :description="t('datasetFlows.noExporter')" />
    <component
      :is="exporter.component"
      v-else
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
