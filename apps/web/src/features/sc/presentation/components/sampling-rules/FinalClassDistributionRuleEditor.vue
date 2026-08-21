<script setup lang="ts">
import type { ScSamplingFinalClassDistributionRule } from "@/features/sc/domain/samplingRules";
import SamplingFinalClassDistributionFields from "./SamplingFinalClassDistributionFields.vue";
import type { ScSamplingRuleEditorContext } from "./types";

const props = defineProps<{
  rule: ScSamplingFinalClassDistributionRule;
  context: ScSamplingRuleEditorContext;
  compact?: boolean;
}>();
const emit = defineEmits<{
  (e: "update:rule", rule: ScSamplingFinalClassDistributionRule): void;
}>();
</script>

<template>
  <div data-testid="rule-editor-final_class_distribution">
    <SamplingFinalClassDistributionFields
      :count="rule.count"
      :targets="rule.targets"
      :options="context.finalClassOptions"
      :distribution-label="context.distributionLabel"
      :loading="context.loading"
      @update:count="emit('update:rule', { ...props.rule, count: $event })"
      @update:targets="emit('update:rule', { ...props.rule, targets: $event })"
    />
  </div>
</template>
