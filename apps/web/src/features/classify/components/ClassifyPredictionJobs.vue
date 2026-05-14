<script setup lang="ts">
import { NCard, NDataTable } from "naive-ui";
import { injectClassifyPage } from "../composables/useClassifyPage";

const page = injectClassifyPage();
</script>

<template>
  <n-card
    v-if="page.predictionJobs.value.length > 0"
    title="Recent Prediction Jobs"
    size="small"
    class="jobs-card"
  >
    <n-data-table
      :columns="page.predictionJobColumns.value"
      :data="page.predictionJobs.value"
      :bordered="true"
      :max-height="220"
    />
  </n-card>
</template>

<style scoped>
.jobs-card {
  flex-shrink: 0;
}
</style>
