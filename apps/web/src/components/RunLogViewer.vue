<template>
  <n-card title="Logs" :content-style="{ padding: 0 }">
    <n-spin :show="isLoading">
      <div class="log-container">
        <template v-if="!isLoading && (!logs || logs.length === 0)">
          <n-text depth="3" style="padding: 16px; display: block;">No logs available</n-text>
        </template>
        <template v-else>
          <div
            v-for="(log, idx) in logs"
            :key="log.id ?? idx"
            class="log-line"
          >
            <n-text depth="3" class="log-ts">
              {{ formatTimestamp(log.timestamp) }}
            </n-text>
            <n-tag
              :type="levelInfo(log.level).type"
              size="small"
              class="log-badge"
            >
              {{ levelInfo(log.level).label }}
            </n-tag>
            <n-text class="log-msg">{{ log.message }}</n-text>
          </div>
        </template>
      </div>
    </n-spin>
  </n-card>
</template>

<script setup lang="ts">
import { computed } from "vue";
import { useQuery } from "@tanstack/vue-query";
import { NCard, NSpin, NTag, NText } from "naive-ui";
import { api } from "../api";
import type { RunLog } from "../types";

// ---------------------------------------------------------------------------
// Props
// ---------------------------------------------------------------------------

const props = defineProps<{ runId: string }>();

// ---------------------------------------------------------------------------
// Log level mapping
// ---------------------------------------------------------------------------

const LOG_LEVELS: Record<number, { label: string; type: "default" | "info" | "warning" | "error" }> = {
  10: { label: "DEBUG", type: "default" },
  20: { label: "INFO", type: "info" },
  30: { label: "WARNING", type: "warning" },
  40: { label: "ERROR", type: "error" },
};

function levelInfo(level: number): { label: string; type: "default" | "info" | "warning" | "error" } {
  // Find the closest known level (largest key <= level)
  const known = Object.keys(LOG_LEVELS)
    .map(Number)
    .filter((k) => k <= level)
    .sort((a, b) => b - a);
  if (known.length > 0) return LOG_LEVELS[known[0]];
  return { label: String(level), type: "default" };
}

function formatTimestamp(ts: string): string {
  return new Date(ts).toLocaleString();
}

// ---------------------------------------------------------------------------
// Query
// ---------------------------------------------------------------------------

const { data: logs, isLoading } = useQuery<RunLog[]>({
  queryKey: computed(() => ["run-logs", props.runId]),
  queryFn: () => api.getRunLogs(props.runId),
  enabled: computed(() => !!props.runId),
  refetchOnWindowFocus: false,
});
</script>

<style scoped>
.log-container {
  font-family: "Menlo", "Consolas", "Monaco", "Liberation Mono", "Courier New", monospace;
  font-size: 12px;
  max-height: 400px;
  overflow-y: auto;
  padding: 8px 0;
}

.log-line {
  display: flex;
  align-items: baseline;
  gap: 8px;
  padding: 2px 16px;
  line-height: 1.6;
}

.log-line:hover {
  background-color: rgba(128, 128, 128, 0.06);
}

.log-ts {
  flex-shrink: 0;
  font-size: 11px;
}

.log-badge {
  flex-shrink: 0;
}

.log-msg {
  white-space: pre-wrap;
  word-break: break-all;
}
</style>
