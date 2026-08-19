<script setup lang="ts">
import type { ScSamplingCountRule } from "@/features/sc/domain/samplingRules";
import SamplingNumericField from "./SamplingNumericField.vue";
import type { ScSamplingRuleEditorContext } from "./types";

type Rule = ScSamplingCountRule<"repeater_count">;
const props = withDefaults(
  defineProps<{ rule: Rule; context: ScSamplingRuleEditorContext; compact?: boolean }>(),
  { compact: false },
);
const emit = defineEmits<{ (e: "update:rule", rule: Rule): void }>();
</script>

<template>
  <div data-testid="rule-editor-repeater_count">
    <SamplingNumericField
      label="Sample count"
      :value="rule.count"
      :minimum="1"
      :compact="compact"
      @update:value="emit('update:rule', { ...props.rule, count: $event })"
    />
  </div>
</template>
