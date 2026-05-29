import { defineStore } from 'pinia'
import { computed, ref } from 'vue'

export const useKanbanStore = defineStore('kanban', () => {
  const data = ref(null)
  const activeBoardName = ref(null)
  const selectedTask = ref(null)

  const boards = computed(() => data.value?.boards || {})
  const boardNames = computed(() => Object.keys(boards.value).sort())

  const activeBoard = computed(() => {
    const name = activeBoardName.value
      || data.value?.default_board
      || boardNames.value[0]
    return boards.value[name] || null
  })

  const columns = computed(() => activeBoard.value?.columns || {})
  const tasks = computed(() => Object.values(columns.value).flat())
  const taskCount = computed(() => activeBoard.value?.task_count || 0)

  function selectTask(task) {
    selectedTask.value = task
  }

  function clearTask() {
    selectedTask.value = null
  }

  function setActiveBoard(name) {
    activeBoardName.value = name
  }

  function tasksForColumn(colName) {
    return columns.value[colName] || []
  }

  function patch(newData) {
    data.value = newData
  }

  async function fetchLatest() {
    try {
      const r = await fetch('/api/v2/kanban')
      if (r.ok) data.value = await r.json()
    } catch (e) {
      console.warn('fetch /api/v2/kanban failed:', e)
    }
  }

  return {
    data, boards, boardNames, activeBoard, activeBoardName,
    columns, tasks, taskCount, selectedTask,
    selectTask, clearTask, setActiveBoard, tasksForColumn,
    patch, fetchLatest,
  }
})
