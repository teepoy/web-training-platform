<script setup lang="ts">
import type { ScSamplingLargeDefectCountRule } from "@/features/sc/domain/samplingRules";
import SamplingNumericField from "./SamplingNumericField.vue";
import SamplingSizeMetricField from "./SamplingSizeMetricField.vue";
import type { ScSamplingRuleEditorContext } from "./types";

const props = defineProps<{
  rule: ScSamplingLargeDefectCountRule;
  context: ScSamplingRuleEditorContext;
  compact?: boolean;
}>();
const emit = defineEmits<{
  (e: "update:rule", rule: ScSamplingLargeDefectCountRule): void;
}>();
</script>

<template>
  <div class="rule-fields" data-testid="rule-editor-large_defect_count">
    <SamplingSizeMetricField
      :value="rule.sizeField"
      @update:value="emit('update:rule', { ...props.rule, sizeField: $event })"
    />
    <div class="two-columns">
      <div>
        <SamplingNumericField
          label="Minimum Size"
          :value="rule.minimum"
          :minimum="0"
          :precision="3"
          @update:value="emit('update:rule', { ...props.rule, minimum: $event })"
        />
      </div>
      <div>
        <SamplingNumericField
          label="Sample count"
          :value="rule.count"
          :minimum="1"
          @update:value="emit('update:rule', { ...props.rule, count: $event })"
        />
      </div>
    </div>
  </div>
</template>

<style scoped>
.rule-fields {
  display: grid;
  gap: 14px;
}

.two-columns {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
}
</style>
