<template>
  <n-modal :show="show" preset="card" style="width: min(960px, 96vw)" @update:show="emit('update:show', $event)">
    <template #header>
      <n-space justify="space-between" align="center" style="width: 100%">
        <n-space vertical :size="2">
          <n-text strong>{{ task?.display_name || 'Task Insight' }}</n-text>
          <n-space size="small" align="center">
            <n-tag size="small" :type="statusType(activeDetail?.derived.display_status)">{{ activeDetail?.derived.display_status || 'unknown' }}</n-tag>
            <n-tag size="small" :type="capacityType(activeDetail?.derived.capacity_status)">{{ activeDetail?.derived.capacity_status || 'unknown' }}</n-tag>
          </n-space>
        </n-space>
        <n-space>
          <n-switch :value="handoffEnabled" @update:value="emit('toggle-handoff', $event)">
            <template #checked>Handoff On</template>
            <template #unchecked>Handoff Off</template>
          </n-switch>
          <n-button v-if="canCancel" type="warning" ghost :loading="cancelMutation.isPending.value" @click="cancelMutation.mutate()">
            Interrupt
          </n-button>
          <n-button v-if="activeDetail?.derived.deep_links.prefect_run_url" tag="a" :href="activeDetail?.derived.deep_links.prefect_run_url || undefined" target="_blank">
            Prefect
          </n-button>
        </n-space>
      </n-space>
    </template>

    <n-spin :show="isLoading">
      <n-space vertical size="large">
        <n-grid :cols="4" :x-gap="12">
          <n-gi>
            <n-statistic label="Queue" :value="task?.work_queue_name || '-'" />
          </n-gi>
          <n-gi>
            <n-statistic label="Queue Priority" :value="activeDetail?.derived.queue_priority_label || 'none'" />
          </n-gi>
          <n-gi>
            <n-statistic label="Ahead In Queue" :value="activeDetail?.derived.queue_depth_ahead !== null && activeDetail?.derived.queue_depth_ahead !== undefined ? String(activeDetail.derived.queue_depth_ahead) : '-'" />
          </n-gi>
          <n-gi>
            <n-statistic label="Capacity" :value="activeDetail?.derived.capacity_status || 'unknown'" />
          </n-gi>
        </n-grid>

        <n-collapse :default-expanded-names="defaultExpanded">
          <n-collapse-item v-for="stage in activeDetail?.derived.stages || []" :key="stage.key" :name="stage.key" :title="stage.label">
            <n-space vertical>
              <n-text depth="3">{{ stage.summary }}</n-text>
              <div v-if="stage.key === 'execution_flow'">
                <n-empty v-if="waterfallRows(stage.nodes).length === 0" description="No execution timing available" />
                <div v-else class="waterfall-shell">
                  <svg :viewBox="`0 0 ${waterfallWidth} ${waterfallHeight(stage.nodes)}`" width="100%" :height="waterfallHeight(stage.nodes)">
                    <g>
                      <line
                        v-for="tick in waterfallTicks(stage.nodes)"
                        :key="tick.x"
                        :x1="tick.x"
                        :x2="tick.x"
                        y1="28"
                        :y2="waterfallHeight(stage.nodes) - 12"
                        stroke="rgba(255,255,255,0.12)"
                        stroke-width="1"
                      />
                      <text
                        v-for="tick in waterfallTicks(stage.nodes)"
                        :key="tick.label + tick.x"
                        :x="tick.x + 4"
                        y="18"
                        fill="rgba(255,255,255,0.72)"
                        font-size="11"
                      >{{ tick.label }}</text>
                    </g>
                    <g v-for="row in waterfallRows(stage.nodes)" :key="row.key">
                      <text
                        x="12"
                        :y="row.y + 16"
                        fill="rgba(255,255,255,0.92)"
                        font-size="12"
                      >{{ row.label }}</text>
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
                      >{{ row.caption }}</text>
                    </g>
                  </svg>
                </div>
              </div>
              <n-steps v-else vertical size="small" :current="currentStep(stage.nodes)" status="process">
                <n-step v-for="node in stage.nodes" :key="node.key" :title="node.label" :description="node.detail" />
              </n-steps>
            </n-space>
          </n-collapse-item>
        </n-collapse>

        <n-grid :cols="2" :x-gap="16">
          <n-gi>
            <n-card title="Dynamic Console" size="small">
              <n-space vertical size="small">
                <n-text v-if="activeDetail?.derived.summary_metrics.rate_hint" depth="3">{{ activeDetail?.derived.summary_metrics.rate_hint }}</n-text>
                <n-code
                  :code="consoleText"
                  language="text"
                  word-wrap
                  style="max-height: 220px; overflow: auto"
                />
              </n-space>
            </n-card>
          </n-gi>
          <n-gi>
            <n-card title="Validation & Output" size="small">
              <n-space vertical>
                <n-grid :cols="3" :x-gap="12">
                  <n-gi><n-statistic label="Errors" :value="String(activeDetail?.derived.scorecard.errors || 0)" /></n-gi>
                  <n-gi><n-statistic label="Warnings" :value="String(activeDetail?.derived.scorecard.warnings || 0)" /></n-gi>
                  <n-gi><n-statistic label="Artifacts" :value="String(activeDetail?.derived.artifacts.length || 0)" /></n-gi>
                </n-grid>
                <n-empty v-if="(activeDetail?.derived.scorecard.checks.length || 0) === 0" description="No checks available" />
                <n-space v-else vertical size="small">
                  <n-card v-for="check in activeDetail?.derived.scorecard.checks || []" :key="check.key" size="small" embedded>
                    <n-space justify="space-between" align="center">
                      <n-text strong>{{ check.label }}</n-text>
                      <n-tag size="small" :type="checkType(check.status)">{{ check.status }}</n-tag>
                    </n-space>
                    <n-text depth="3">{{ check.message }}</n-text>
                  </n-card>
                </n-space>
              </n-space>
            </n-card>
          </n-gi>
        </n-grid>
      </n-space>
    </n-spin>
  </n-modal>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useMutation, useQuery, useQueryClient } from '@tanstack/vue-query'
import { useMessage } from 'naive-ui'
import { api } from '../api'
import type { TaskTrackerNode, TaskTrackerSummary } from '../types'
import { useTaskStream } from '../composables/useTaskHandoff'
import { useOrgStore } from '../stores/org'

const props = defineProps<{
  show: boolean
  task: TaskTrackerSummary | null
  handoffEnabled: boolean
}>()

const emit = defineEmits<{
  'update:show': [value: boolean]
  'toggle-handoff': [value: boolean]
}>()

const message = useMessage()
const queryClient = useQueryClient()
const orgStore = useOrgStore()

const { data: detail, isLoading } = useQuery({
  queryKey: computed(() => ['task-tracker-detail', orgStore.currentOrgId, props.task?.id]),
  queryFn: () => api.getTrackedTask(props.task!.id),
  enabled: computed(() => props.show && !!props.task?.id && !!orgStore.currentOrgId),
  refetchInterval: computed(() => (props.show ? 5000 : false)),
})

const streamedDetail = ref<typeof detail.value | null>(null)

watch(detail, (value) => {
  if (value) {
    streamedDetail.value = value
  }
}, { immediate: true })

const activeDetail = computed(() => streamedDetail.value ?? detail.value ?? null)

useTaskStream(
  computed(() => (props.show && props.task?.id ? props.task.id : null)),
  (payload) => {
    streamedDetail.value = payload
  },
)

const cancelMutation = useMutation({
  mutationFn: () => api.cancelTrackedTask(props.task!.id),
  onSuccess: () => {
    void queryClient.invalidateQueries({ queryKey: ['task-tracker', orgStore.currentOrgId] })
    void queryClient.invalidateQueries({ queryKey: ['task-tracker-detail', orgStore.currentOrgId, props.task?.id] })
    message.warning('Cancellation requested')
  },
  onError: (error: Error) => {
    message.error(error.message || 'Failed to cancel task')
  },
})

const defaultExpanded = computed(() => {
  const stage = activeDetail.value?.derived.stage
  if (!stage) return ['queue_allocation']
  return [stage]
})

const canCancel = computed(() => {
  const status = activeDetail.value?.derived.display_status
  return status === 'queued' || status === 'running'
})

const consoleText = computed(() => {
  const lines = activeDetail.value?.derived.dynamic_console_lines || []
  if (lines.length > 0) return lines.join('\n')
  return 'No runtime output available.'
})

function currentStep(nodes: Array<{ status: string }>): number {
  const activeIndex = nodes.findIndex((node) => node.status === 'active')
  if (activeIndex >= 0) return activeIndex + 1
  const completed = nodes.filter((node) => node.status === 'completed').length
  return Math.max(1, completed)
}

function statusType(status?: string) {
  if (status === 'completed') return 'success'
  if (status === 'failed') return 'error'
  if (status === 'cancelled') return 'warning'
  if (status === 'running') return 'info'
  return 'default'
}

function capacityType(status?: string) {
  if (status === 'at_capacity') return 'error'
  if (status === 'busy') return 'warning'
  if (status === 'normal') return 'success'
  return 'default'
}

function checkType(status?: string) {
  if (status === 'failed') return 'error'
  if (status === 'warning') return 'warning'
  if (status === 'passed') return 'success'
  return 'default'
}

const waterfallWidth = 920
const waterfallLabelWidth = 180
const waterfallRightPadding = 24
const waterfallTopOffset = 36
const waterfallRowHeight = 34
const waterfallBarHeight = 22

function waterfallRows(nodes: TaskTrackerNode[]) {
  const rows = nodes
    .map((node) => {
      const start = node.started_at || node.expected_start_at
      const end = node.ended_at || node.started_at || node.expected_start_at
      if (!start || !end) return null
      const startMs = Date.parse(start)
      const endMs = Date.parse(end)
      if (Number.isNaN(startMs) || Number.isNaN(endMs)) return null
      return {
        key: node.key,
        label: node.label,
        status: node.status,
        startMs,
        endMs: Math.max(endMs, startMs + 1000),
      }
    })
    .filter((row): row is { key: string; label: string; status: string; startMs: number; endMs: number } => row !== null)

  if (rows.length === 0) return []

  const minMs = Math.min(...rows.map((row) => row.startMs))
  const maxMs = Math.max(...rows.map((row) => row.endMs))
  const domain = Math.max(1000, maxMs - minMs)
  const plotWidth = waterfallWidth - waterfallLabelWidth - waterfallRightPadding

  return rows.map((row, index) => {
    const barX = waterfallLabelWidth + ((row.startMs - minMs) / domain) * plotWidth
    const barWidth = Math.max(10, ((row.endMs - row.startMs) / domain) * plotWidth)
    return {
      ...row,
      y: waterfallTopOffset + index * waterfallRowHeight,
      barX,
      barWidth,
      color: waterfallColor(row.status),
      caption: formatDuration(row.endMs - row.startMs),
    }
  })
}

function waterfallTicks(nodes: TaskTrackerNode[]) {
  const rows = waterfallRows(nodes)
  if (rows.length === 0) return []
  const minMs = Math.min(...rows.map((row) => row.startMs))
  const maxMs = Math.max(...rows.map((row) => row.endMs))
  const plotWidth = waterfallWidth - waterfallLabelWidth - waterfallRightPadding
  const tickCount = Math.min(8, Math.max(3, rows.length + 1))
  const step = Math.max(1, tickCount - 1)
  const domain = Math.max(1000, maxMs - minMs)

  return Array.from({ length: tickCount }, (_, index) => {
    const ratio = index / step
    const ts = minMs + domain * ratio
    return {
      x: waterfallLabelWidth + plotWidth * ratio,
      label: new Date(ts).toLocaleTimeString([], { hour: 'numeric', minute: '2-digit', second: '2-digit' }),
    }
  })
}

function waterfallHeight(nodes: TaskTrackerNode[]) {
  return Math.max(120, waterfallTopOffset + waterfallRows(nodes).length * waterfallRowHeight + 18)
}

function waterfallColor(status: string) {
  if (status === 'completed') return '#22c55e'
  if (status === 'failed') return '#ef4444'
  if (status === 'active') return '#3b82f6'
  return '#a78bfa'
}

function formatDuration(durationMs: number) {
  const seconds = Math.max(1, Math.round(durationMs / 1000))
  if (seconds < 60) return `${seconds}s`
  const minutes = Math.floor(seconds / 60)
  const remSeconds = seconds % 60
  return remSeconds === 0 ? `${minutes}m` : `${minutes}m ${remSeconds}s`
}
</script>

<style scoped>
.waterfall-shell {
  border: 1px solid rgba(255, 255, 255, 0.08);
  border-radius: 10px;
  background: #1a1d24;
  overflow-x: auto;
  padding: 8px;
}
</style>
