<template>
  <div class="kanban-card" @click="$emit('select', task)">
    <div class="card-top-row">
      <span class="task-priority" :style="{ background: priorityColor }">P{{ task.priority || 0 }}</span>
      <span class="task-assignee chip" v-if="task.assignee">{{ task.assignee }}</span>
    </div>
    <div class="task-title">{{ task.title || task.id }}</div>
    <div class="task-meta">
      <span v-if="task.created_at">{{ fmtDate(task.created_at) }}</span>
      <span v-if="task.completed_at" class="done">DONE</span>
      <span v-if="task.status === 'blocked'" class="blocked">BLOCKED</span>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  task: { type: Object, required: true },
})
defineEmits(['select'])

const priorityColor = computed(() => {
  const p = props.task.priority || 0
  if (p <= 3) return 'var(--red)'
  if (p <= 7) return 'var(--amber)'
  return 'var(--cyan)'
})

function fmtDate(ts) {
  if (!ts) return ''
  const d = new Date(ts * 1000)
  const now = new Date()
  const diff = (now - d) / 1000
  if (diff < 86400) return d.toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit' })
  return d.toISOString().slice(0, 10)
}
</script>

<style scoped>
.kanban-card {
  background: var(--bg-elevated);
  border: 1px solid var(--line);
  padding: 10px 12px;
  cursor: pointer;
  transition: border-color 0.2s;
  margin-bottom: 6px;
}
.kanban-card:hover { border-color: var(--line-strong); }
.card-top-row { display: flex; align-items: center; gap: 6px; margin-bottom: 4px; }
.task-priority {
  font-family: var(--font-mono);
  font-size: 8px;
  color: var(--bg-void);
  padding: 1px 5px;
  font-weight: 700;
  letter-spacing: 0.1em;
}
.task-title {
  font-family: var(--font-body);
  font-size: 12px;
  color: var(--text);
  font-weight: 500;
  line-height: 1.3;
}
.task-meta {
  display: flex;
  gap: 8px;
  margin-top: 4px;
  font-family: var(--font-mono);
  font-size: 9px;
  color: var(--text-faint);
}
.task-meta .done { color: var(--green); }
.task-meta .blocked { color: var(--red); }
</style>
