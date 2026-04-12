<!--
  WidgetErrorBoundary — catches rendering errors in child widgets and shows
  a friendly error message instead of crashing the entire sidebar.
-->
<script setup lang="ts">
import { ref, onErrorCaptured } from 'vue'

const props = defineProps<{
  widgetId: string
  widgetComponent: string
}>()

const error = ref<string | null>(null)

onErrorCaptured((err) => {
  error.value = err instanceof Error ? err.message : String(err)
  // Prevent propagation
  return false
})

function retry() {
  error.value = null
}
</script>

<template>
  <div v-if="error" class="web-error">
    <div class="web-error__icon">!</div>
    <div class="web-error__msg">
      Widget "{{ widgetComponent }}" failed: {{ error }}
    </div>
    <button class="web-error__retry" @click="retry">Retry</button>
  </div>
  <slot v-else />
</template>

<style scoped>
.web-error {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 6px;
  padding: 12px 8px;
  background: rgba(244, 67, 54, 0.08);
  border-radius: 6px;
  border: 1px solid rgba(244, 67, 54, 0.2);
}
.web-error__icon {
  width: 24px;
  height: 24px;
  border-radius: 50%;
  background: rgba(244, 67, 54, 0.2);
  color: #ef9a9a;
  display: flex;
  align-items: center;
  justify-content: center;
  font-weight: 700;
  font-size: 14px;
}
.web-error__msg {
  font-size: 11px;
  color: rgba(255, 255, 255, 0.6);
  text-align: center;
  word-break: break-word;
}
.web-error__retry {
  background: rgba(255, 255, 255, 0.08);
  border: 1px solid rgba(255, 255, 255, 0.15);
  border-radius: 4px;
  color: rgba(255, 255, 255, 0.7);
  font-size: 11px;
  padding: 3px 10px;
  cursor: pointer;
}
.web-error__retry:hover {
  background: rgba(255, 255, 255, 0.12);
}
</style>
