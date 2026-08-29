<!-- Development-only component showcase. -->
<template>
  <div class="classify-sandbox">
    <n-space vertical size="large">
      <n-h2>Classify Sandbox</n-h2>
      <n-text depth="3">
        Sandbox environment for the classify workflow. Mounted inside the main App.vue shell.
      </n-text>
      <n-card title="Placeholder">
        <n-text>This is a minimal sandbox shell. Extend with real classify components here.</n-text>
      </n-card>
    </n-space>
  </div>
</template>

<script setup lang="ts">
import { NH2, NCard, NSpace, NText } from "naive-ui";
</script>

<style scoped>
.classify-sandbox {
  padding: 24px;
  max-width: 960px;
}
</style>
