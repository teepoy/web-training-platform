<script setup lang="ts">
import { NText } from "naive-ui";
import { useI18n } from "vue-i18n";
import type { ScSamplingRequireImageRule } from "@/features/sc/domain/samplingRules";
import type { ScSamplingRuleEditorContext } from "./types";

const { t } = useI18n();

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
    <NText depth="3">{{ t("sc.imagesRequired") }}</NText>
  </div>
</template>
