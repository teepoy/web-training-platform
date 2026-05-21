import { ref } from 'vue'

const STORAGE_KEY = 'task_handoff_ids'

function loadIds(): string[] {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (!raw) return []
    const parsed = JSON.parse(raw)
    return Array.isArray(parsed) ? parsed.filter((item): item is string => typeof item === 'string') : []
  } catch {
    return []
  }
}

const watchedTaskIds = ref<string[]>(loadIds())

function persist() {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(watchedTaskIds.value))
  } catch {
    /* ignore */
  }
}

export function useTaskHandoffState() {
  function addTaskId(taskId: string) {
    if (!watchedTaskIds.value.includes(taskId)) {
      watchedTaskIds.value = [...watchedTaskIds.value, taskId]
      persist()
    }
  }

  function removeTaskId(taskId: string) {
    watchedTaskIds.value = watchedTaskIds.value.filter((value) => value !== taskId)
    persist()
  }

  return {
    watchedTaskIds,
    addTaskId,
    removeTaskId,
  }
}
