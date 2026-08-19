<script setup lang="ts">
import type { ScSamplingClassCodesRule } from "@/features/sc/domain/samplingRules";
import SamplingClassCodesField from "./SamplingClassCodesField.vue";
import type { ScSamplingRuleEditorContext } from "./types";

type Rule = ScSamplingClassCodesRule<"exclude_class_codes">;
const props = defineProps<{
  rule: Rule;
  context: ScSamplingRuleEditorContext;
  compact?: boolean;
}>();
const emit = defineEmits<{ (e: "update:rule", rule: Rule): void }>();
</script>

<template>
  <div data-testid="rule-editor-exclude_class_codes">
    <SamplingClassCodesField
      :value="rule.classCodes"
      :options="context.classCodeOptions"
      :loading="context.loading"
      @update:value="emit('update:rule', { ...props.rule, classCodes: $event })"
    />
  </div>
</template>
