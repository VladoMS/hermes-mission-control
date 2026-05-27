<template>
  <div class="kanban-board">
    <!-- Board selector -->
    <div class="board-selector">
      <button
        v-for="name in boardNames"
        :key="name"
        class="board-chip chip"
        :class="{ red: name === activeBoardName }"
        @click="kanbanStore.setActiveBoard(name)"
      >
        {{ name }}
      </button>
    </div>

    <!-- Columns -->
    <div class="board-columns">
      <div
        v-for="col in columns"
        :key="col.key"
        class="board-col"
      >
        <div class="col-header">
          <span class="col-dot" :style="{ background: col.color }"></span>
          <span class="col-label">{{ col.label }}</span>
          <span class="col-count">{{ col.tasks.length }}</span>
        </div>
        <div class="col-body">
          <KanbanCard
            v-for="task in col.tasks"
            :key="task.id"
            :task="task"
            @select="$emit('select', $event)"
          />
          <div v-if="col.tasks.length === 0" class="col-empty">--</div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { useKanbanStore } from '../stores/kanban.js'
import KanbanCard from './KanbanCard.vue'

defineEmits(['select'])

const kanbanStore = useKanbanStore()

const boardNames = computed(() => kanbanStore.boardNames)
const activeBoardName = computed(() => kanbanStore.activeBoardName)

const COL_DEFS = [
  { key: 'triage', label: 'TRIAGE', color: '#6b7585' },
  { key: 'todo', label: 'TODO', color: '#1ec8ff' },
  { key: 'in_progress', label: 'IN PROGRESS', color: '#ffb020' },
  { key: 'blocked', label: 'BLOCKED', color: '#ff3b1f' },
  { key: 'review', label: 'REVIEW', color: '#d946ef' },
  { key: 'done', label: 'DONE', color: '#4ade80' },
  { key: 'cancelled', label: 'CANCELLED', color: '#404a58' },
]

const columns = computed(() => {
  const cols = kanbanStore.columns
  return COL_DEFS.map(def => ({
    ...def,
    tasks: cols[def.key] || [],
  }))
})
</script>

<style scoped>
.kanban-board { }
.board-selector {
  display: flex;
  gap: 6px;
  flex-wrap: wrap;
  margin-bottom: 16px;
}
.board-chip { cursor: pointer; }
.board-columns {
  display: grid;
  grid-template-columns: repeat(7, 1fr);
  gap: 8px;
  overflow-x: auto;
}
.board-col {
  background: var(--bg-deep);
  border: 1px solid var(--line);
  min-height: 200px;
}
.col-header {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 8px 10px;
  border-bottom: 1px solid var(--line);
  font-family: var(--font-mono);
  font-size: 9px;
  letter-spacing: 0.12em;
  text-transform: uppercase;
}
.col-dot { width: 6px; height: 6px; border-radius: 50%; flex-shrink: 0; }
.col-label { color: var(--text-dim); flex: 1; }
.col-count { color: var(--text-faint); }
.col-body { padding: 6px; }
.col-empty {
  font-family: var(--font-mono);
  font-size: 10px;
  color: var(--text-faint);
  text-align: center;
  padding: 20px 0;
}
@media (max-width: 1200px) {
  .board-columns { grid-template-columns: repeat(4, 1fr); }
}
@media (max-width: 720px) {
  .board-columns { grid-template-columns: repeat(2, 1fr); }
}
</style>
