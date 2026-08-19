<script setup lang="ts">
import type { ScSamplingLimitRule } from "@/features/sc/domain/samplingRules";
import SamplingNumericField from "./SamplingNumericField.vue";
import type { ScSamplingRuleEditorContext } from "./types";

type Rule = ScSamplingLimitRule<"per_repeater_limit">;
const props = withDefaults(
  defineProps<{ rule: Rule; context: ScSamplingRuleEditorContext; compact?: boolean }>(),
  { compact: false },
);
const emit = defineEmits<{ (e: "update:rule", rule: Rule): void }>();
</script>

<template>
  <div data-testid="rule-editor-per_repeater_limit">
    <SamplingNumericField
      label="Maximum selected defects per Repeater ID"
      :value="rule.limit"
      :minimum="1"
      :compact="compact"
      @update:value="emit('update:rule', { ...props.rule, limit: $event })"
    />
  </div>
</template>
