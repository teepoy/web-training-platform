<script setup lang="ts">
import ModelsView from "../../../views/ModelsView.vue";

const props = defineProps<{ datasetId: string }>();
</script>

<template>
  <n-space vertical>
    <n-text depth="3" style="font-size: 13px">
      Models trained on this dataset — run a prediction
    </n-text>
    <ModelsView :datasetId="props.datasetId" />
  </n-space>
</template>
