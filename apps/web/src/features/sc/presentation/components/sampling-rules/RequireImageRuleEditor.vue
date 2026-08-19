<script setup lang="ts">
import { NText } from "naive-ui";
import type { ScSamplingRequireImageRule } from "@/features/sc/domain/samplingRules";
import type { ScSamplingRuleEditorContext } from "./types";

withDefaults(
  defineProps<{
    rule: ScSamplingRequireImageRule;
    context: ScSamplingRuleEditorContext;
    compact?: boolean;
  }>(),
  { compact: false },
);
</script>

<template>
  <div data-testid="rule-editor-require_image">
    <NText depth="3">Images &gt; 0</NText>
  </div>
</template>
