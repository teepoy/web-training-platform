<script setup lang="ts">
import { useI18n } from "vue-i18n";
import type { ScSamplingLimitRule } from "@/features/sc/domain/samplingRules";
import SamplingNumericField from "./SamplingNumericField.vue";
import type { ScSamplingRuleEditorContext } from "./types";

type Rule = ScSamplingLimitRule<"per_wafer_limit">;
const props = withDefaults(
  defineProps<{ rule: Rule; context: ScSamplingRuleEditorContext; compact?: boolean }>(),
  { compact: false },
);
const emit = defineEmits<{ (e: "update:rule", rule: Rule): void }>();
const { t } = useI18n();
</script>

<template>
  <div data-testid="rule-editor-per_wafer_limit">
    <SamplingNumericField
      :label="t('sc.maximumPerWafer')"
      :value="rule.limit"
      :minimum="1"
      :compact="compact"
      @update:value="emit('update:rule', { ...props.rule, limit: $event })"
    />
  </div>
</template>
