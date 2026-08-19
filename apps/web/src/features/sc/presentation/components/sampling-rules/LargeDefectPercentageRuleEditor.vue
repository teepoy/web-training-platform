<script setup lang="ts">
import type { ScSamplingLargeDefectPercentageRule } from "@/features/sc/domain/samplingRules";
import SamplingNumericField from "./SamplingNumericField.vue";
import SamplingPercentageFields from "./SamplingPercentageFields.vue";
import SamplingSizeMetricField from "./SamplingSizeMetricField.vue";
import type { ScSamplingRuleEditorContext } from "./types";

const props = defineProps<{
  rule: ScSamplingLargeDefectPercentageRule;
  context: ScSamplingRuleEditorContext;
  compact?: boolean;
}>();
const emit = defineEmits<{
  (e: "update:rule", rule: ScSamplingLargeDefectPercentageRule): void;
}>();
</script>

<template>
  <div class="rule-fields" data-testid="rule-editor-large_defect_percentage">
    <SamplingSizeMetricField
      :value="rule.sizeField"
      @update:value="emit('update:rule', { ...props.rule, sizeField: $event, rounding: 'floor' })"
    />
    <div class="two-columns">
      <div>
        <SamplingNumericField
          label="Minimum Size"
          :value="rule.minimum"
          :minimum="0"
          :precision="3"
          @update:value="emit('update:rule', { ...props.rule, minimum: $event, rounding: 'floor' })"
        />
      </div>
      <div>
        <SamplingPercentageFields
          :percentage="rule.percentage"
          @update:percentage="
            emit('update:rule', { ...props.rule, percentage: $event, rounding: 'floor' })
          "
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
