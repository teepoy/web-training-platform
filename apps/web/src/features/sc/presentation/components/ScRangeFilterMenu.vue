<script setup lang="ts">
import { computed } from "vue";
import { NInputNumber, NText } from "naive-ui";
import ScFilterPopover from "./ScFilterPopover.vue";

const props = defineProps<{
  min: number | null;
  max: number | null;
  loading?: boolean;
  rangeUnavailable?: boolean;
}>();

const canApply = computed(
  () =>
    (props.min === null && props.max === null) ||
    (props.min !== null && props.max !== null && props.min <= props.max),
);

const emit = defineEmits<{
  (e: "update:min", value: number | null): void;
  (e: "update:max", value: number | null): void;
  (e: "apply"): void;
  (e: "close"): void;
}>();

function apply(): void {
  if (!canApply.value) return;
  emit("apply");
  emit("close");
}

function clear(): void {
  emit("update:min", null);
  emit("update:max", null);
}

function cancel(): void {
  emit("close");
}
</script>

<template>
  <ScFilterPopover
    variant="range"
    :apply-disabled="loading || !canApply"
    @clear="clear"
    @cancel="cancel"
    @apply="apply"
  >
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
  </ScFilterPopover>
</template>

<style scoped>
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
