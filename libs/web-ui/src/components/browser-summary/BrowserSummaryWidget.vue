<script setup lang="ts">
import { computed, inject } from "vue";
import { BROWSER_DASHBOARD_KEY } from "@platform/widget-sdk";
import { DATA_PIPELINE_KEY } from "../../composables/useDataPipeline";

const props = withDefaults(
  defineProps<{
    totalLoaded?: number;
    filteredCount?: number;
  }>(),
  {},
);

const browserDashboard = inject(BROWSER_DASHBOARD_KEY, null);
const pipeline = inject(DATA_PIPELINE_KEY)!;
const summaryNode = pipeline.register("browser-summary");

const resolvedTotal = computed<number | null>(() => {
  if (props.totalLoaded !== undefined) return props.totalLoaded;
  const v = browserDashboard?.["totalLoaded"];
  return typeof v === "number" ? v : null;
});

const resolvedFiltered = computed<number | null>(() => {
  if (props.filteredCount !== undefined) return props.filteredCount;
  const v = browserDashboard?.["filteredCount"];
  return typeof v === "number" ? v : null;
});

const activeLabelFilter = computed<string | null>(() => {
  const annotations = summaryNode.visibleAnnotations.value;
  const labelFilter = annotations.find((a) => a.kind === "labelFilter");
  if (!labelFilter || labelFilter.ids.size === 0) return null;
  return [...labelFilter.ids][0];
});

const summaryText = computed<string>(() => {
  const total = resolvedTotal.value;
  const filtered = resolvedFiltered.value;
  if (total === null) return "—";
  if (filtered === null || filtered === total) return `${total} items loaded`;
  return `Showing ${filtered} of ${total} items`;
});
</script>

<template>
  <div class="browser-summary">
    <span class="browser-summary__count">{{ summaryText }}</span>
    <span v-if="activeLabelFilter" class="browser-summary__filter">
      Filtered: <em>{{ activeLabelFilter }}</em>
    </span>
  </div>
</template>

<style scoped>
.browser-summary {
  display: flex;
  flex-direction: column;
  gap: 4px;
  padding: 8px 0;
  font-size: 12px;
  color: var(--cv-text-secondary, #888);
}

.browser-summary__count {
  color: var(--cv-text, inherit);
  font-variant-numeric: tabular-nums;
}

.browser-summary__filter {
  color: var(--cv-text-secondary, #888);
}

.browser-summary__filter em {
  font-style: normal;
  color: var(--cv-text, inherit);
}
</style>
