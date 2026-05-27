import { defineStore } from 'pinia'
import { computed, ref } from 'vue'
import { useSnapshotStore } from './snapshotStore.js'

/**
 * Kanban store — boards, columns, tasks, and task modal state.
 * Derives from snapshot.data.kanban.
 */
export const useKanbanStore = defineStore('kanban', () => {
  const snap = useSnapshotStore()

  /** All boards keyed by name: { name, columns: {colName: [tasks]}, task_count } */
  const boards = computed(() => snap.data?.kanban?.boards || {})

  /** Sorted list of board names */
  const boardNames = computed(() => Object.keys(boards.value).sort())

  /** User-selected board override (null = use default) */
  const activeBoardName = ref(null)

  /** Currently active board — explicit selection or snapshot default */
  const activeBoard = computed(() => {
    const name = activeBoardName.value
      || snap.data?.kanban?.default_board
      || boardNames.value[0]
    return boards.value[name] || null
  })

  /** Columns for the active board: { triage: [...], todo: [...], ... } */
  const columns = computed(() => activeBoard.value?.columns || {})

  /** Flattened task list for the active board */
  const tasks = computed(() =>
    Object.values(columns.value).flat()
  )

  /** Total task count for the active board */
  const taskCount = computed(() => activeBoard.value?.task_count || 0)

  // ── Task modal ──────────────────────────────────────────

  /** Currently selected task for the detail modal (null = closed) */
  const selectedTask = ref(null)

  function selectTask(task) {
    selectedTask.value = task
  }

  function clearTask() {
    selectedTask.value = null
  }

  // ── Board switching ────────────────────────────────────

  function setActiveBoard(name) {
    activeBoardName.value = name
  }

  /** Get tasks for a specific column in the active board */
  function tasksForColumn(colName) {
    return columns.value[colName] || []
  }

  return {
    boards,
    boardNames,
    activeBoard,
    activeBoardName,
    columns,
    tasks,
    taskCount,
    selectedTask,
    selectTask,
    clearTask,
    setActiveBoard,
    tasksForColumn,
  }
})
