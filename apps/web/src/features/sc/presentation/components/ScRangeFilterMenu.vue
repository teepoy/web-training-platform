<script setup lang="ts">
import { NButton, NInputNumber, NSpace } from "naive-ui";

defineProps<{
  min: number | null;
  max: number | null;
}>();

const emit = defineEmits<{
  (e: "update:min", value: number | null): void;
  (e: "update:max", value: number | null): void;
  (e: "apply"): void;
  (e: "clear"): void;
  (e: "close"): void;
}>();

function apply(): void {
  emit("apply");
  emit("close");
}

function clear(): void {
  emit("clear");
  emit("close");
}
</script>

<template>
  <div class="sst-filter-popover">
    <NSpace :wrap="false">
      <NInputNumber
        :value="min"
        placeholder="Min"
        size="small"
        class="sst-range-input"
        @update:value="emit('update:min', $event)"
      />
      <NInputNumber
        :value="max"
        placeholder="Max"
        size="small"
        class="sst-range-input"
        @update:value="emit('update:max', $event)"
      />
    </NSpace>
    <NSpace :size="4">
      <NButton size="tiny" @click="apply">Apply</NButton>
      <NButton size="tiny" quaternary @click="clear">Clear</NButton>
    </NSpace>
  </div>
</template>

<style scoped>
.sst-filter-popover {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 8px;
  max-width: min(320px, calc(100vw - 48px));
  min-width: 0;
}

.sst-range-input {
  width: 100px;
}
</style>
