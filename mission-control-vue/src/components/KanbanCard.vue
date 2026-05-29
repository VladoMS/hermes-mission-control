<template>
  <div class="kanban-card" :class="agingClass" @click="$emit('select', task)">
    <div class="card-top-row">
      <span class="task-priority" :style="{ background: priorityColor }">P{{ task.priority || 0 }}</span>
      <span class="task-assignee chip" v-if="task.assignee">{{ task.assignee }}</span>
      <span v-if="ageDays >= 30" class="task-stale" title="Stale — 30+ days">⚡</span>
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

const ageDays = computed(() => {
  const ts = props.task.created_at
  if (!ts) return 0
  return (Date.now() / 1000 - ts) / 86400
})

const agingClass = computed(() => {
  if (ageDays.value >= 30) return 'aging-critical'
  if (ageDays.value >= 7) return 'aging-warn'
  return ''
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
.kanban-card.aging-warn { border-left: 2px solid var(--amber); }
.kanban-card.aging-critical { border-left: 2px solid var(--red); }
.card-top-row { display: flex; align-items: center; gap: 6px; margin-bottom: 4px; }
.task-stale {
  margin-left: auto;
  font-size: 10px;
  color: var(--red);
  opacity: 0.7;
}
.task-priority {
  font-family: var(--font-mono);
  font-size: 10px;
  color: var(--bg-void);
  padding: 1px 6px;
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
