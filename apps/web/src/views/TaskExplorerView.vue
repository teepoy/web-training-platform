<template>
  <n-space vertical size="large">
    <template v-if="!orgStore.currentOrgId">
      <div style="padding: 48px; text-align: center;">
        <n-empty description="You are not a member of any organization. Contact an admin." />
      </div>
    </template>
    <template v-else>
      <n-page-header title="Task Explorer">
        <template #subtitle>
          Prefect-backed tracker for training, prediction, and embedding batch tasks.
        </template>
      </n-page-header>

      <n-space>
        <n-select v-model:value="kindFilter" :options="kindOptions" style="width: 180px" />
        <n-select v-model:value="statusFilter" :options="statusOptions" style="width: 180px" />
      </n-space>

      <n-data-table :columns="columns" :data="filteredTasks" :loading="isLoading" :bordered="true" :striped="true" />

      <TaskInsightModal
        v-model:show="showModal"
        :task="selectedTask"
        :handoff-enabled="selectedTask ? handoffIds.has(selectedTask.id) : false"
        @toggle-handoff="toggleHandoff"
      />
    </template>
  </n-space>
</template>

<script setup lang="ts">
import { computed, h, ref, watch } from 'vue'
import { useQuery } from '@tanstack/vue-query'
import type { DataTableColumns, SelectOption } from 'naive-ui'
import { NButton, NTag } from 'naive-ui'
import { api } from '../api'
import TaskInsightModal from '../components/TaskInsightModal.vue'
import { useTaskHandoff } from '../composables/useTaskHandoff'
import { useTaskHandoffState } from '../composables/taskHandoffState'
import type { TaskTrackerSummary } from '../types'
import { useOrgStore } from '../stores/org'

const orgStore = useOrgStore()
const kindFilter = ref<'all' | 'training' | 'prediction' | 'schedule_run'>('all')
const statusFilter = ref<'all' | 'queued' | 'running' | 'completed' | 'failed' | 'cancelled'>('all')
const showModal = ref(false)
const selectedTask = ref<TaskTrackerSummary | null>(null)
const { watchedTasks, watchTask, unwatchTask, syncTask } = useTaskHandoff()
const { addTaskId, removeTaskId } = useTaskHandoffState()

const handoffIds = computed(() => new Set(Object.keys(watchedTasks.value)))

const { data: tasks, isLoading } = useQuery({
  queryKey: computed(() => ['task-tracker', orgStore.currentOrgId]),
  queryFn: () => api.listTrackedTasks(),
  enabled: computed(() => !!orgStore.currentOrgId),
  refetchInterval: computed(() => (document.visibilityState === 'hidden' ? 20000 : 5000)),
})

const kindOptions: SelectOption[] = [
  { label: 'All Tasks', value: 'all' },
  { label: 'Training', value: 'training' },
  { label: 'Prediction', value: 'prediction' },
  { label: 'Schedule Runs', value: 'schedule_run' },
]

const statusOptions: SelectOption[] = [
  { label: 'All Statuses', value: 'all' },
  { label: 'Queued', value: 'queued' },
  { label: 'Running', value: 'running' },
  { label: 'Completed', value: 'completed' },
  { label: 'Failed', value: 'failed' },
  { label: 'Cancelled', value: 'cancelled' },
]

const filteredTasks = computed(() => {
  return (tasks.value || []).filter((task) => {
    const kindMatch = kindFilter.value === 'all' || task.task_kind === kindFilter.value
    const statusMatch = statusFilter.value === 'all' || task.display_status === statusFilter.value
    return kindMatch && statusMatch
  })
})

watch(tasks, (value) => {
  for (const task of value || []) {
    if (handoffIds.value.has(task.id)) {
      void syncTask(task)
    }
  }
}, { immediate: true })

const columns = computed<DataTableColumns<TaskTrackerSummary>>(() => [
  {
    title: 'Task',
    key: 'display_name',
    minWidth: 180,
  },
  {
    title: 'Kind',
    key: 'task_kind',
    width: 120,
    render: (row) => h(NTag, { size: 'small' }, { default: () => row.task_kind }),
  },
  {
    title: 'Status',
    key: 'display_status',
    width: 120,
    render: (row) => h(NTag, { size: 'small', type: statusType(row.display_status) }, { default: () => row.display_status }),
  },
  {
    title: 'Stage',
    key: 'stage',
    width: 160,
  },
  {
    title: 'Queue',
    key: 'work_queue_name',
    width: 140,
    render: (row) => row.work_queue_name || '-',
  },
  {
    title: 'Priority',
    key: 'queue_priority_label',
    width: 100,
  },
  {
    title: 'Capacity',
    key: 'capacity_status',
    width: 120,
    render: (row) => h(NTag, { size: 'small', type: capacityType(row.capacity_status) }, { default: () => row.capacity_status }),
  },
  {
    title: 'Updated',
    key: 'updated_at',
    width: 180,
    render: (row) => new Date(row.updated_at).toLocaleString(),
  },
  {
    title: 'Actions',
    key: 'actions',
    width: 120,
    render: (row) => h(NButton, {
      size: 'small',
      onClick: () => openTask(row),
    }, { default: () => 'Inspect' }),
  },
])

function openTask(task: TaskTrackerSummary) {
  selectedTask.value = task
  showModal.value = true
}

function toggleHandoff(value: boolean) {
  if (!selectedTask.value) return
  if (value) {
    watchTask(selectedTask.value)
    addTaskId(selectedTask.value.id)
    return
  }
  unwatchTask(selectedTask.value.id)
  removeTaskId(selectedTask.value.id)
}

function statusType(status: string) {
  if (status === 'completed') return 'success'
  if (status === 'failed') return 'error'
  if (status === 'cancelled') return 'warning'
  if (status === 'running') return 'info'
  return 'default'
}

function capacityType(status: string) {
  if (status === 'at_capacity') return 'error'
  if (status === 'busy') return 'warning'
  if (status === 'normal') return 'success'
  return 'default'
}
</script>
