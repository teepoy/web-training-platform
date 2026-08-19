<script setup lang="ts">
import type { ScSamplingSizeRangeRule } from "@/features/sc/domain/samplingRules";
import SamplingNumericField from "./SamplingNumericField.vue";
import SamplingSizeMetricField from "./SamplingSizeMetricField.vue";
import type { ScSamplingRuleEditorContext } from "./types";

const props = defineProps<{
  rule: ScSamplingSizeRangeRule;
  context: ScSamplingRuleEditorContext;
  compact?: boolean;
}>();
const emit = defineEmits<{ (e: "update:rule", rule: ScSamplingSizeRangeRule): void }>();
</script>

<template>
  <div class="rule-fields" data-testid="rule-editor-size_range">
    <SamplingSizeMetricField
      :value="rule.sizeField"
      @update:value="emit('update:rule', { ...props.rule, sizeField: $event })"
    />
    <div class="two-columns">
      <div>
        <SamplingNumericField
          label="Minimum"
          :value="rule.minimum"
          :minimum="0"
          :precision="3"
          @update:value="emit('update:rule', { ...props.rule, minimum: $event })"
        />
      </div>
      <div>
        <SamplingNumericField
          label="Maximum"
          :value="rule.maximum"
          :minimum="0"
          :precision="3"
          @update:value="emit('update:rule', { ...props.rule, maximum: $event })"
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
