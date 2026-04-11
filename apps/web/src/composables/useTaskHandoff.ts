import { computed, onUnmounted, ref, watch, type Ref } from 'vue'
import type { TaskTrackerDetail, TaskTrackerSummary } from '../types'

const watchedTasks = ref<Record<string, TaskTrackerSummary>>({})
const previousStatuses = new Map<string, string>()

let titleTimer: number | null = null
let titleBase = 'ML Training Platform'

function stopTitleFlash() {
  if (titleTimer !== null) {
    window.clearInterval(titleTimer)
    titleTimer = null
    document.title = titleBase
  }
}

function startTitleFlash(message: string) {
  stopTitleFlash()
  let visible = false
  titleTimer = window.setInterval(() => {
    visible = !visible
    document.title = visible ? message : titleBase
  }, 1000)
}

function playTone(kind: 'success' | 'error') {
  try {
    const audio = new AudioContext()
    const osc = audio.createOscillator()
    const gain = audio.createGain()
    osc.connect(gain)
    gain.connect(audio.destination)
    osc.type = kind === 'success' ? 'sine' : 'square'
    osc.frequency.value = kind === 'success' ? 880 : 440
    gain.gain.value = 0.04
    osc.start()
    window.setTimeout(() => {
      osc.stop()
      void audio.close()
    }, kind === 'success' ? 180 : 320)
  } catch {
    /* ignore browser audio failures */
  }
}

async function notifyTerminal(task: TaskTrackerSummary, status: string) {
  const title = status === 'completed' ? 'Task completed' : 'Task needs attention'
  const body = `${task.display_name} is now ${status}.`
  startTitleFlash(status === 'completed' ? '[[ Task Complete ]]' : '[[ Task Alert ]]')
  if ('Notification' in window) {
    if (Notification.permission === 'default') {
      await Notification.requestPermission()
    }
    if (Notification.permission === 'granted') {
      new Notification(title, { body })
    }
  }
  playTone(status === 'completed' ? 'success' : 'error')
}

export function useTaskHandoff() {
  titleBase = document.title

  function watchTask(task: TaskTrackerSummary) {
    watchedTasks.value = {
      ...watchedTasks.value,
      [task.id]: task,
    }
    previousStatuses.set(task.id, task.display_status)
  }

  function unwatchTask(taskId: string) {
    const next = { ...watchedTasks.value }
    delete next[taskId]
    watchedTasks.value = next
    previousStatuses.delete(taskId)
    if (Object.keys(next).length === 0) {
      stopTitleFlash()
    }
  }

  async function syncTask(task: TaskTrackerSummary) {
    const previous = previousStatuses.get(task.id)
    previousStatuses.set(task.id, task.display_status)
    if (!previous || previous === task.display_status) {
      return
    }
    if (['completed', 'failed', 'cancelled'].includes(task.display_status)) {
      await notifyTerminal(task, task.display_status)
    }
  }

  const activeIds = computed(() => Object.keys(watchedTasks.value))

  onUnmounted(() => {
    stopTitleFlash()
  })

  return {
    watchedTasks,
    activeIds,
    watchTask,
    unwatchTask,
    syncTask,
    stopTitleFlash,
  }
}

export async function syncWatchedTaskIds(
  taskIds: string[],
  onDetail: (detail: TaskTrackerDetail) => void,
) {
  const { api } = await import('../api')
  for (const taskId of taskIds) {
    try {
      const detail = await api.getTrackedTask(taskId)
      onDetail(detail)
    } catch {
      /* ignore stale watched ids */
    }
  }
}

export function useTaskStream(
  taskId: Ref<string | null>,
  onDetail: (detail: TaskTrackerDetail) => void,
) {
  let source: EventSource | null = null

  function close() {
    if (source !== null) {
      source.close()
      source = null
    }
  }

  watch(taskId, (value) => {
    close()
    if (!value) {
      return
    }
    import('../api').then(({ buildTrackedTaskEventSource }) => {
      source = buildTrackedTaskEventSource(value)
      source.onmessage = (event) => {
        try {
          onDetail(JSON.parse(event.data) as TaskTrackerDetail)
        } catch {
          /* ignore malformed payload */
        }
      }
      source.onerror = () => {
        close()
      }
    })
  }, { immediate: true })

  onUnmounted(() => {
    close()
  })

  return { close }
}
