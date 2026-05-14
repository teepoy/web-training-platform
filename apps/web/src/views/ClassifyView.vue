<template>
  <div class="classify-view" :style="page.themeStyleVars.value">
    <div class="classify-header">
      <n-button text @click="page.router.push(`/datasets/${page.datasetId.value}`)">
        <template #icon>
          <span>&#8592;</span>
        </template>
        Back
      </n-button>
      <n-divider vertical />
      <n-text tag="h2" style="margin: 0; font-size: 18px; font-weight: 600">
        {{ page.datasetQuery.data.value?.name ?? page.datasetId.value }}
      </n-text>
      <n-tag v-if="page.isReviewMode.value" type="warning" size="small">
        Prediction Review Mode
      </n-tag>
      <n-tag v-if="page.isSparse.value" type="info" size="small">
        Sparse Storage
      </n-tag>
      <div style="margin-left: auto; display: flex; align-items: center; gap: 12px">
        <n-text depth="3" style="white-space: nowrap">View</n-text>
        <n-radio-group v-model:value="page.prefs.layout" size="small">
          <n-radio-button value="grid">Grid</n-radio-button>
          <n-radio-button value="list">List</n-radio-button>
        </n-radio-group>
        <n-text depth="3" style="white-space: nowrap">Image size</n-text>
        <n-slider v-model:value="page.prefs.thumbSize" :min="64" :max="256" :step="8" style="width: 160px" />
        <n-text depth="3" style="white-space: nowrap">{{ page.prefs.thumbSize }}px</n-text>
      </div>
    </div>

    <n-alert
      v-if="page.isSparse.value"
      type="warning"
      :bordered="false"
      style="margin-bottom: 4px"
    >
      Sparse dataset — prediction / reclassify workflows only. Full annotation
      and LS sync are not available.
    </n-alert>

    <ClassifyWorkflowCards />

    <ClassifyPredictionJobs />

    <div class="classify-body">
      <ClassifyBrowserArea />
    </div>

    <ClassifyAddLabelModal />

    <component
      :is="page.TaskInsightModal"
      :show="page.showTaskModal.value"
      :task="page.activeTaskSummary.value"
      :handoff-enabled="page.taskHandoffEnabled.value"
      @update:show="page.showTaskModal.value = $event"
      @toggle-handoff="page.taskHandoffEnabled.value = $event"
    />
  </div>
</template>

<script setup lang="ts">
import {
  NButton,
  NDivider,
  NText,
  NTag,
  NSlider,
  NRadioGroup,
  NRadioButton,
  NAlert,
} from "naive-ui";
import { useClassifyPage } from "../features/classify/composables/useClassifyPage";
import ClassifyWorkflowCards from "../features/classify/components/ClassifyWorkflowCards.vue";
import ClassifyPredictionJobs from "../features/classify/components/ClassifyPredictionJobs.vue";
import ClassifyBrowserArea from "../features/classify/components/ClassifyBrowserArea.vue";
import ClassifyAddLabelModal from "../features/classify/components/ClassifyAddLabelModal.vue";

const page = useClassifyPage();
</script>

<style scoped>
.classify-view {
  display: flex;
  flex-direction: column;
  height: 100vh;
  padding: 12px;
  box-sizing: border-box;
  color: var(--cv-text);
  gap: 10px;
}

.classify-header {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-shrink: 0;
}

.classify-body {
  display: flex;
  flex: 1;
  min-height: 0;
  gap: 0;
}
</style>
