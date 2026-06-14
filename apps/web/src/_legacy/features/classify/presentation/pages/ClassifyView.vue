<script setup lang="ts">
import { NModal } from "naive-ui";
import { FullScreenLayout } from "@/shared/components/full-screen-layout";
import { useClassifyPage } from "../../application/useClassifyPage";
import ClassifyAddLabelModal from "../components/ClassifyAddLabelModal.vue";
import ClassifyBrowserArea from "../components/ClassifyBrowserArea.vue";
import ClassifyPredictionJobs from "../components/ClassifyPredictionJobs.vue";
import ClassifyWorkflowCards from "../components/ClassifyWorkflowCards.vue";

const page = useClassifyPage();
</script>

<template>
  <FullScreenLayout>
  <div class="classify-page">
    <ClassifyWorkflowCards />
    <ClassifyPredictionJobs />
    <ClassifyBrowserArea />

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
  </FullScreenLayout>
</template>

<style scoped>
.classify-page {
  display: flex;
  flex-direction: column;
  flex: 1;
  min-height: 0;
  gap: 12px;
}
</style>
