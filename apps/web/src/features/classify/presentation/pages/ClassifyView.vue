<script setup lang="ts">
import { NModal } from "naive-ui";
import { useClassifyPage } from "../../application/useClassifyPage";
import ClassifyAddLabelModal from "../components/ClassifyAddLabelModal.vue";
import ClassifyBrowserArea from "../components/ClassifyBrowserArea.vue";
import ClassifyPredictionJobs from "../components/ClassifyPredictionJobs.vue";
import ClassifyWorkflowCards from "../components/ClassifyWorkflowCards.vue";

const page = useClassifyPage();
</script>

<template>
  <div class="classify-page">
    <div class="classify-main">
      <ClassifyWorkflowCards />
      <ClassifyPredictionJobs />
      <ClassifyBrowserArea />
    </div>

    <component
      :is="page.ClassifySidebar"
      :panels="page.mergedPanels.value"
      :context="page.pageDashboard"
    />

    <ClassifyAddLabelModal />

    <NModal
      v-model:show="page.showTaskModal.value"
      preset="card"
      title="Task Insight"
      style="max-width: 760px"
    >
      <component
        :is="page.TaskInsightModal"
        v-if="page.activeTaskSummary.value"
        :show="page.showTaskModal.value"
        :task="page.activeTaskSummary.value"
        :handoff-enabled="page.taskHandoffEnabled.value"
        @update:show="page.showTaskModal.value = $event"
        @toggle-handoff="page.taskHandoffEnabled.value = $event"
      />
    </NModal>
  </div>
</template>

<style scoped>
.classify-page {
  display: flex;
  min-height: calc(100vh - 96px);
  gap: 12px;
}

.classify-main {
  display: flex;
  flex: 1;
  min-width: 0;
  flex-direction: column;
  gap: 12px;
}
</style>
