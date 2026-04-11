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
              <n-steps vertical size="small" :current="currentStep(stage.nodes)" status="process">
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
import type { TaskTrackerSummary } from '../types'
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
</script>
