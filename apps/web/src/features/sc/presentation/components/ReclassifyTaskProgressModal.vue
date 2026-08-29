<script setup lang="ts">
import { computed, ref, watch } from "vue";
import { useI18n } from "vue-i18n";
import {
  NCollapse,
  NCollapseItem,
  NEmpty,
  NGi,
  NGrid,
  NModal,
  NProgress,
  NSpace,
  NSpin,
  NStatistic,
  NStep,
  NSteps,
  NTag,
  NText,
} from "naive-ui";
import { useTrackedTaskQuery } from "@/shared/api/hooks";
import { useTaskStream } from "@/shared/composables/useTaskHandoff";
import type { TaskTrackerNode } from "@/generated/orval/models";

const { t } = useI18n();

const props = defineProps<{
  show: boolean;
  trainingJobId: string | null;
  trainingStatus: string;
  predictionJobId: string | null;
  predictionStatus: string;
  predictionPercent: number | null;
  predictionProgressLabel: string;
  predictionProcessing: boolean;
}>();

const emit = defineEmits<{
  "update:show": [value: boolean];
}>();

const { data: detail, isLoading } = useTrackedTaskQuery(() =>
  props.show && props.trainingJobId ? props.trainingJobId : null,
);

const streamedDetail = ref<typeof detail.value | null>(null);

watch(
  detail,
  (value) => {
    if (value) {
      streamedDetail.value = value;
    }
  },
  { immediate: true },
);

useTaskStream(
  computed(() => (props.show && props.trainingJobId ? props.trainingJobId : null)),
  (payload) => {
    streamedDetail.value = payload;
  },
);

const activeDetail = computed(() => streamedDetail.value ?? detail.value ?? null);
const insightStages = computed(() => (activeDetail.value?.derived.stages ?? []).slice(0, 2));
const defaultExpanded = computed(() => {
  const activeStage = activeDetail.value?.derived.stage;
  if (activeStage && insightStages.value.some((stage) => stage.key === activeStage)) {
    return [activeStage];
  }
  return insightStages.value.map((stage) => stage.key);
});

const displayStatus = computed(
  () => activeDetail.value?.derived.display_status || props.trainingStatus || "pending",
);
const workerSlotsLabel = computed(() => {
  const used = activeDetail.value?.derived.pool_slots_used;
  const limit = activeDetail.value?.derived.pool_concurrency_limit;
  if (used !== null && used !== undefined && limit !== null && limit !== undefined) {
    return `${used} / ${limit}`;
  }
  if (used !== null && used !== undefined) return String(used);
  return "unknown";
});
const flowRun = computed(() => activeDetail.value?.raw.flow_run ?? null);
const workQueueName = computed(() => {
  const queueName = flowRun.value?.work_queue_name;
  return typeof queueName === "string" && queueName ? queueName : "-";
});

function currentStep(nodes: Array<{ status: string }>): number {
  const activeIndex = nodes.findIndex((node) => node.status === "active");
  if (activeIndex >= 0) return activeIndex + 1;
  const completed = nodes.filter((node) => node.status === "completed").length;
  return Math.max(1, completed);
}

function statusType(status?: string): "default" | "success" | "error" | "warning" | "info" {
  if (status === "completed") return "success";
  if (status === "failed") return "error";
  if (status === "cancelled") return "warning";
  if (status === "running" || status === "waiting") return "info";
  return "default";
}

function capacityType(status?: string): "default" | "success" | "error" | "warning" | "info" {
  if (status === "at_capacity") return "error";
  if (status === "busy") return "warning";
  if (status === "normal") return "success";
  return "default";
}

const waterfallWidth = 920;
const waterfallLabelWidth = 180;
const waterfallRightPadding = 24;
const waterfallTopOffset = 36;
const waterfallRowHeight = 34;

function waterfallRows(nodes: TaskTrackerNode[]) {
  const rows = nodes
    .map((node) => {
      const start = node.started_at || node.expected_start_at;
      const end = node.ended_at || node.started_at || node.expected_start_at;
      if (!start || !end) return null;
      const startMs = Date.parse(start);
      const endMs = Date.parse(end);
      if (Number.isNaN(startMs) || Number.isNaN(endMs)) return null;
      return {
        key: node.key,
        label: node.label,
        status: node.status,
        startMs,
        endMs: Math.max(endMs, startMs + 1000),
      };
    })
    .filter(
      (
        row,
      ): row is {
        key: string;
        label: string;
        status: string;
        startMs: number;
        endMs: number;
      } => row !== null,
    );

  if (rows.length === 0) return [];

  const minMs = Math.min(...rows.map((row) => row.startMs));
  const maxMs = Math.max(...rows.map((row) => row.endMs));
  const domain = Math.max(1000, maxMs - minMs);
  const plotWidth = waterfallWidth - waterfallLabelWidth - waterfallRightPadding;

  return rows.map((row, index) => {
    const barX = waterfallLabelWidth + ((row.startMs - minMs) / domain) * plotWidth;
    const barWidth = Math.max(10, ((row.endMs - row.startMs) / domain) * plotWidth);
    return {
      ...row,
      y: waterfallTopOffset + index * waterfallRowHeight,
      barX,
      barWidth,
      color: waterfallColor(row.status),
      caption: formatDuration(row.endMs - row.startMs),
    };
  });
}

function waterfallTicks(nodes: TaskTrackerNode[]) {
  const rows = waterfallRows(nodes);
  if (rows.length === 0) return [];
  const minMs = Math.min(...rows.map((row) => row.startMs));
  const maxMs = Math.max(...rows.map((row) => row.endMs));
  const plotWidth = waterfallWidth - waterfallLabelWidth - waterfallRightPadding;
  const tickCount = Math.min(8, Math.max(3, rows.length + 1));
  const step = Math.max(1, tickCount - 1);
  const domain = Math.max(1000, maxMs - minMs);

  return Array.from({ length: tickCount }, (_, index) => {
    const ratio = index / step;
    const ts = minMs + domain * ratio;
    return {
      x: waterfallLabelWidth + plotWidth * ratio,
      label: new Date(ts).toLocaleTimeString([], {
        hour: "numeric",
        minute: "2-digit",
        second: "2-digit",
      }),
    };
  });
}

function waterfallHeight(nodes: TaskTrackerNode[]) {
  return Math.max(120, waterfallTopOffset + waterfallRows(nodes).length * waterfallRowHeight + 18);
}

function waterfallColor(status: string) {
  if (status === "completed") return "#22c55e";
  if (status === "failed") return "#ef4444";
  if (status === "active") return "#3b82f6";
  return "#a78bfa";
}

function formatDuration(durationMs: number) {
  const seconds = Math.max(1, Math.round(durationMs / 1000));
  if (seconds < 60) return `${seconds}s`;
  const minutes = Math.floor(seconds / 60);
  const remSeconds = seconds % 60;
  return remSeconds === 0 ? `${minutes}m` : `${minutes}m ${remSeconds}s`;
}
</script>

<template>
  <NModal
    :show="show"
    preset="card"
    :style="{ width: 'min(960px, 96vw)' }"
    @update:show="emit('update:show', $event)"
  >
    <template #header>
      <NSpace justify="space-between" align="center" style="width: 100%">
        <NSpace vertical :size="2">
          <NText strong>{{ t("sc.trainPredict") }}</NText>
          <NSpace size="small" align="center">
            <NTag size="small" :type="statusType(displayStatus)">
              {{ displayStatus }}
            </NTag>
            <NTag size="small" :type="capacityType(activeDetail?.derived.capacity_status)">
              {{ t("sc.slots") }} {{ workerSlotsLabel }}
            </NTag>
          </NSpace>
        </NSpace>
      </NSpace>
    </template>

    <NSpin :show="isLoading">
      <NSpace vertical size="large">
        <NGrid :cols="4" :x-gap="12">
          <NGi>
            <NStatistic :label="t('widgets.queue')" :value="workQueueName" />
          </NGi>
          <NGi>
            <NStatistic
              :label="t('widgets.queuePriority')"
              :value="activeDetail?.derived.queue_priority_label || 'none'"
            />
          </NGi>
          <NGi>
            <NStatistic
              :label="t('widgets.aheadInQueue')"
              :value="
                activeDetail?.derived.queue_depth_ahead !== null &&
                activeDetail?.derived.queue_depth_ahead !== undefined
                  ? String(activeDetail.derived.queue_depth_ahead)
                  : '-'
              "
            />
          </NGi>
          <NGi>
            <NStatistic :label="t('sc.workerSlots')" :value="workerSlotsLabel" />
          </NGi>
        </NGrid>

        <NCollapse v-if="insightStages.length > 0" :default-expanded-names="defaultExpanded">
          <NCollapseItem
            v-for="stage in insightStages"
            :key="stage.key"
            :name="stage.key"
            :title="stage.label"
          >
            <NSpace vertical>
              <NText depth="3">{{ stage.summary }}</NText>
              <div v-if="stage.key === 'execution_flow'">
                <NEmpty
                  v-if="waterfallRows(stage.nodes ?? []).length === 0"
                  :description="t('widgets.noExecutionTiming')"
                />
                <div v-else class="rtp-waterfall-shell">
                  <svg
                    :viewBox="`0 0 ${waterfallWidth} ${waterfallHeight(stage.nodes ?? [])}`"
                    width="100%"
                    :height="waterfallHeight(stage.nodes ?? [])"
                  >
                    <g>
                      <line
                        v-for="tick in waterfallTicks(stage.nodes ?? [])"
                        :key="tick.x"
                        :x1="tick.x"
                        :x2="tick.x"
                        y1="28"
                        :y2="waterfallHeight(stage.nodes ?? []) - 12"
                        stroke="rgba(255,255,255,0.12)"
                        stroke-width="1"
                      />
                      <text
                        v-for="tick in waterfallTicks(stage.nodes ?? [])"
                        :key="tick.label + tick.x"
                        :x="tick.x + 4"
                        y="18"
                        fill="rgba(255,255,255,0.72)"
                        font-size="11"
                      >
                        {{ tick.label }}
                      </text>
                    </g>
                    <g v-for="row in waterfallRows(stage.nodes ?? [])" :key="row.key">
                      <text x="12" :y="row.y + 16" fill="rgba(255,255,255,0.92)" font-size="12">
                        {{ row.label }}
                      </text>
                      <rect
                        :x="row.barX"
                        :y="row.y"
                        :width="row.barWidth"
                        height="22"
                        rx="4"
                        :fill="row.color"
                      />
                      <text
                        :x="row.barX + 8"
                        :y="row.y + 15"
                        fill="rgba(255,255,255,0.95)"
                        font-size="11"
                      >
                        {{ row.caption }}
                      </text>
                    </g>
                  </svg>
                </div>
              </div>
              <NSteps
                v-else
                vertical
                size="small"
                :current="currentStep(stage.nodes ?? [])"
                status="process"
              >
                <NStep
                  v-for="node in stage.nodes ?? []"
                  :key="node.key"
                  :title="node.label"
                  :description="node.detail"
                />
              </NSteps>
            </NSpace>
          </NCollapseItem>
        </NCollapse>
        <NEmpty v-else :description="t('sc.noTaskInsight')" />

        <div class="rtp-progress">
          <div class="rtp-progress-header">
            <NSpace align="center" size="small">
              <NText strong>{{ t("sc.predictProgress") }}</NText>
              <NTag size="small" :type="statusType(predictionStatus)">
                {{ predictionStatus || "not_started" }}
              </NTag>
            </NSpace>
            <NText depth="3">
              {{ predictionPercent === null ? "--" : `${predictionPercent}%` }}
            </NText>
          </div>
          <NProgress
            type="line"
            :percentage="predictionPercent ?? 100"
            :show-indicator="false"
            :processing="predictionProcessing"
            :status="predictionStatus === 'failed' ? 'error' : 'default'"
          />
          <div class="rtp-progress-footer">
            <NText depth="3" class="rtp-progress-label">
              {{ predictionProgressLabel }}
            </NText>
            <NText depth="3" class="rtp-progress-label">
              {{ predictionJobId ? predictionJobId.slice(0, 8) : t("sc.pendingJob") }}
            </NText>
          </div>
        </div>
      </NSpace>
    </NSpin>
  </NModal>
</template>

<style scoped>
.rtp-waterfall-shell {
  border: 1px solid rgba(255, 255, 255, 0.08);
  border-radius: 8px;
  background: #1a1d24;
  overflow-x: auto;
  padding: 8px;
}

.rtp-progress {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.rtp-progress-header,
.rtp-progress-footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.rtp-progress-label {
  font-size: 12px;
}
</style>
