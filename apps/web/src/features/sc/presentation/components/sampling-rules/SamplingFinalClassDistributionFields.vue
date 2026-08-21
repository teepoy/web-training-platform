<script setup lang="ts">
import { NInputNumber } from "naive-ui";
import type { ScSamplingFinalClassTarget } from "@/features/sc/domain/samplingRules";
import SamplingNumericField from "./SamplingNumericField.vue";

const props = defineProps<{
  count: number;
  targets: ScSamplingFinalClassTarget[];
  options: Array<{ label: string; value: string }>;
  distributionLabel: string;
  loading: boolean;
}>();

const emit = defineEmits<{
  (e: "update:count", value: number): void;
  (e: "update:targets", value: ScSamplingFinalClassTarget[]): void;
}>();

function updateTarget(index: number, percentage: number | null): void {
  if (percentage === null) return;
  emit(
    "update:targets",
    props.targets.map((target, targetIndex) =>
      targetIndex === index ? { ...target, percentage } : target,
    ),
  );
}
</script>

<template>
  <div class="distribution-fields">
    <SamplingNumericField
      label="Total sample count"
      :value="count"
      :minimum="1"
      @update:value="emit('update:count', $event)"
    />
    <div class="distribution-list">
      <div v-for="(target, index) in targets" :key="target.value" class="distribution-row">
        <strong>{{
          options.find((option) => option.value === target.value)?.label ?? target.value
        }}</strong>
        <NInputNumber
          :value="target.percentage"
          :min="0.01"
          :max="100"
          :precision="2"
          @update:value="updateTarget(index, $event)"
        >
          <template #suffix>%</template>
        </NInputNumber>
      </div>
      <div v-if="targets.length === 0" class="empty-state">
        {{
          loading
            ? `Loading ${distributionLabel} values…`
            : `No ${distributionLabel} values are available.`
        }}
      </div>
    </div>
  </div>
</template>

<style scoped>
.distribution-fields {
  display: grid;
  gap: 14px;
}

.distribution-list {
  overflow: hidden;
  border: 1px solid var(--cv-border, #e2e2e2);
  border-radius: 10px;
}

.distribution-row {
  display: grid;
  grid-template-columns: minmax(180px, 1fr) 180px;
  gap: 12px;
  align-items: center;
  padding: 10px 12px;
  border-bottom: 1px solid var(--cv-divider, #ededed);
}

.distribution-row:last-child {
  border-bottom: 0;
}

.empty-state {
  padding: 20px;
  color: var(--cv-text-secondary, #737373);
  text-align: center;
}
</style>
