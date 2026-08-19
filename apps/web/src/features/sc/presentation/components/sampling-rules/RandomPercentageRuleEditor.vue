<script setup lang="ts">
import type { ScSamplingPercentageRule } from "@/features/sc/domain/samplingRules";
import SamplingPercentageFields from "./SamplingPercentageFields.vue";
import type { ScSamplingRuleEditorContext } from "./types";

type Rule = ScSamplingPercentageRule<"random_percentage">;
const props = withDefaults(
  defineProps<{ rule: Rule; context: ScSamplingRuleEditorContext; compact?: boolean }>(),
  { compact: false },
);
const emit = defineEmits<{ (e: "update:rule", rule: Rule): void }>();
</script>

<template>
  <div data-testid="rule-editor-random_percentage">
    <SamplingPercentageFields
      :percentage="rule.percentage"
      :compact="compact"
      @update:percentage="
        emit('update:rule', { ...props.rule, percentage: $event, rounding: 'floor' })
      "
    />
  </div>
</template>
