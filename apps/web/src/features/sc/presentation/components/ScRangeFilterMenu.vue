<script setup lang="ts">
import { NButton, NInputNumber, NSpace, NText } from "naive-ui";

defineProps<{
  min: number | null;
  max: number | null;
  loading?: boolean;
  rangeUnavailable?: boolean;
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
    <NText v-if="loading" depth="3" class="sst-range-status">Querying field range…</NText>
    <NText v-else-if="rangeUnavailable" type="error" class="sst-range-status">
      Could not load field range. You can still enter values manually.
    </NText>
    <div class="sst-range-fields">
      <label class="sst-range-field">
        <NText depth="3" class="sst-range-label">Min</NText>
        <NInputNumber
          :value="min"
          placeholder="Min"
          size="small"
          class="sst-range-input"
          :disabled="loading"
          @update:value="emit('update:min', $event)"
        />
      </label>
      <label class="sst-range-field">
        <NText depth="3" class="sst-range-label">Max</NText>
        <NInputNumber
          :value="max"
          placeholder="Max"
          size="small"
          class="sst-range-input"
          :disabled="loading"
          @update:value="emit('update:max', $event)"
        />
      </label>
    </div>
    <NSpace :size="4">
      <NButton size="tiny" :disabled="loading" @click="apply">Apply</NButton>
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
  width: 128px;
}

.sst-range-fields {
  display: flex;
  gap: 8px;
}

.sst-range-field {
  display: grid;
  gap: 3px;
}

.sst-range-label {
  font-size: 11px;
}

.sst-range-status {
  max-width: 240px;
  font-size: 11px;
}
</style>
