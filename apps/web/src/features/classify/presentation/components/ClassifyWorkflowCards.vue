<script setup lang="ts">
import {
  NButton,
  NCard,
  NDivider,
  NGrid,
  NGi,
  NInput,
  NSelect,
  NSpace,
  NTag,
  NText,
} from "naive-ui";
import { injectClassifyPage } from "../../application/useClassifyPage";

const page = injectClassifyPage();
</script>

<template>
  <n-grid :cols="2" :x-gap="12" class="workflow-grid">
    <n-gi>
      <n-card title="Training" size="small">
        <n-space vertical>
          <n-select
            v-model:value="page.selectedPresetId.value"
            :options="page.presetOptions.value"
            placeholder="Select training preset"
            filterable
          />
          <n-space>
            <n-button
              type="primary"
              :disabled="!page.selectedPresetId.value"
              :loading="page.startTrainingMutation.isPending.value"
              @click="page.startTraining"
            >
              Start Training
            </n-button>
            <n-button @click="page.router.push('/tasks')">
              Open Task Explorer
            </n-button>
          </n-space>
          <n-text
            v-if="page.activeTrainingJob.value"
            depth="3"
          >
            Active training: {{ page.activeTrainingJob.value.id }}
            ({{ page.activeTrainingJob.value.status }})
          </n-text>
        </n-space>
      </n-card>
    </n-gi>
    <n-gi>
      <n-card title="Prediction Review" size="small">
        <n-text
          v-if="page.isSparse.value"
          depth="3"
          style="font-size: 12px; display: block; margin-bottom: 8px"
        >
          Prediction jobs are supported. Per-sample review and LS sync are
          not available for sparse datasets.
        </n-text>
        <n-space vertical>
          <n-select
            v-model:value="page.selectedModelId.value"
            :options="page.modelOptions.value"
            placeholder="Select model"
            filterable
          />
          <n-input
            v-model:value="page.modelVersionTag.value"
            placeholder="Optional model version"
          />
          <n-space>
            <n-button
              type="primary"
              :disabled="!page.selectedModelId.value"
              :loading="page.runPredictionsMutation.isPending.value"
              @click="page.runPredictions"
            >
              Run Predictions
            </n-button>
            <n-button
              v-if="
                page.activePredictionJob.value &&
                ['queued', 'running'].includes(
                  page.activePredictionJob.value.status.toLowerCase(),
                )
              "
              type="warning"
              :loading="page.cancelPredictionMutation.isPending.value"
              @click="page.cancelPrediction"
            >
              Cancel
            </n-button>
          </n-space>
          <n-text
            v-if="page.activePredictionJob.value"
            depth="3"
          >
            Active prediction: {{ page.activePredictionJob.value.id }}
            ({{ page.activePredictionJob.value.status }})
            <template
              v-if="
                page.formatPredictionJobProgress(
                  page.activePredictionJob.value,
                )
              "
            >
              &middot;
              {{
                page.formatPredictionJobProgress(
                  page.activePredictionJob.value,
                )
              }}
              processed
            </template>
          </n-text>
        </n-space>
      </n-card>
    </n-gi>
  </n-grid>
</template>

<style scoped>
.workflow-grid {
  flex-shrink: 0;
}

@media (max-width: 1100px) {
  .workflow-grid {
    display: block;
  }
}
</style>
