<script setup lang="ts">
import { NButton, NSpace } from "naive-ui";

withDefaults(
  defineProps<{
    variant?: "set" | "text" | "range";
    applyDisabled?: boolean;
  }>(),
  { variant: "range", applyDisabled: false },
);

const emit = defineEmits<{
  (event: "clear"): void;
  (event: "cancel"): void;
  (event: "apply"): void;
}>();
</script>

<template>
  <div class="sst-filter-popover" :class="`sst-filter-popover--${variant}`">
    <slot />
    <NSpace :size="4">
      <NButton size="tiny" quaternary @click="emit('clear')">Clear</NButton>
      <NButton size="tiny" quaternary @click="emit('cancel')">Cancel</NButton>
      <NButton size="tiny" type="primary" :disabled="applyDisabled" @click="emit('apply')">
        Apply
      </NButton>
    </NSpace>
  </div>
</template>

<style scoped>
.sst-filter-popover {
  display: flex;
  flex-direction: column;
  gap: 8px;
  max-width: min(320px, calc(100vw - 48px));
  min-width: 0;
  padding: 8px;
}

.sst-filter-popover--set,
.sst-filter-popover--text {
  width: 260px;
}
</style>
