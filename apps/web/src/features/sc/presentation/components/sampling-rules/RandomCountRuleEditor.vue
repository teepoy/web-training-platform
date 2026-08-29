<script setup lang="ts">
import { useI18n } from "vue-i18n";
import type { ScSamplingCountRule } from "@/features/sc/domain/samplingRules";
import SamplingNumericField from "./SamplingNumericField.vue";
import type { ScSamplingRuleEditorContext } from "./types";

type Rule = ScSamplingCountRule<"random_count">;
const props = withDefaults(
  defineProps<{ rule: Rule; context: ScSamplingRuleEditorContext; compact?: boolean }>(),
  { compact: false },
);
const emit = defineEmits<{ (e: "update:rule", rule: Rule): void }>();
const { t } = useI18n();
</script>

<template>
  <div data-testid="rule-editor-random_count">
    <SamplingNumericField
      :label="t('sc.sampleCountLabel')"
      :value="rule.count"
      :minimum="1"
      :compact="compact"
      test-id="sampling-random-count"
      @update:value="emit('update:rule', { ...props.rule, count: $event })"
    />
  </div>
</template>
