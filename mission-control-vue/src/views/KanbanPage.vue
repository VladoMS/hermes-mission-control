<template>
  <div class="kanban-page section">
    <div class="section-head">
      <div class="title-block">
        <div class="eyebrow">KANBAN</div>
        <div class="display medium">{{ taskCount }} TASKS</div>
      </div>
    </div>

    <KanbanBoard @select="kanbanStore.selectTask" />

    <TaskModal :task="kanbanStore.selectedTask" @close="kanbanStore.clearTask()" />
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { useKanbanStore } from '../stores/kanban.js'
import KanbanBoard from '../components/KanbanBoard.vue'
import TaskModal from '../components/TaskModal.vue'

const kanbanStore = useKanbanStore()
const taskCount = computed(() => kanbanStore.taskCount)
</script>

<style scoped>
.kanban-page { position: relative; z-index: 5; }
</style>
