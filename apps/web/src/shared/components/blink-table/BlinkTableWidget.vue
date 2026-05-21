<script setup lang="ts">
import { computed } from "vue";
import { BlinkTable } from "./";
import type { BlinkRow, BlinkColumnDef } from "../../types/blink-table";

const props = defineProps<{
  data?: Record<string, unknown> | null;
  config?: Record<string, unknown>;
  size?: "compact" | "normal" | "large";
}>();

interface BlinkTableInlineData {
  rows?: BlinkRow[];
  columns?: BlinkColumnDef[];
}

const inlineData = computed<BlinkTableInlineData>(() => {
  if (!props.data) return {};
  const raw = (props.data as Record<string, unknown>).inline ?? props.data;
  if (!raw || typeof raw !== "object") return {};
  const d = raw as Record<string, unknown>;
  return {
    rows: Array.isArray(d.rows) ? (d.rows as BlinkRow[]) : [],
    columns: Array.isArray(d.columns) ? (d.columns as BlinkColumnDef[]) : [],
  };
});

const blinkIntervalMs = computed(() =>
  Number(props.config?.blinkIntervalMs ?? 1000),
);

const initialBlinkEnabled = computed(() =>
  props.config?.initialBlinkEnabled !== false,
);
</script>

<template>
  <div class="btw">
    <BlinkTable
      v-if="inlineData.rows && inlineData.rows.length > 0"
      :rows="inlineData.rows"
      :columns="inlineData.columns ?? []"
      :blinkIntervalMs="blinkIntervalMs"
      :initialBlinkEnabled="initialBlinkEnabled"
    />
    <div v-else class="btw-empty">No multi-image samples to display.</div>
  </div>
</template>

<style scoped>
.btw {
  width: 100%;
  min-height: 0;
}

.btw-empty {
  font-size: 12px;
  color: rgba(255, 255, 255, 0.4);
  padding: 12px 0;
  text-align: center;
}
</style>
