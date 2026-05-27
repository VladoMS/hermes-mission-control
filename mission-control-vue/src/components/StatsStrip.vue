<template>
  <div class="stats-strip">
    <div class="stat-box" v-for="stat in stats" :key="stat.label">
      <div class="stat-label">{{ stat.label }}</div>
      <div class="stat-value">{{ stat.value }}</div>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { useSnapshotStore } from '../stores/snapshotStore.js'

const snap = useSnapshotStore()

function fmtTokens(n) {
  if (!n && n !== 0) return '--'
  if (n >= 1e9) return (n / 1e9).toFixed(1) + 'B'
  if (n >= 1e6) return (n / 1e6).toFixed(1) + 'M'
  if (n >= 1e3) return (n / 1e3).toFixed(1) + 'K'
  return String(n)
}

const stats = computed(() => {
  const d = snap.data
  if (!d) return []

  const gwState = (d.gateway?.gateway_state || 'unknown').toUpperCase()
  const profiles = d.profiles?.length || 0
  const sessions = d.sessions || []
  const todayCutoff = Date.now() / 1000 - 86400
  const sessionsToday = Array.isArray(sessions)
    ? sessions.filter(s => s.started_at && s.started_at >= todayCutoff).length
    : 0
  const ledger = d.sessions_ledger || {}
  const tokens = ledger.total_tokens || 0
  const kanban = d.kanban?.boards || {}
  let totalTasks = 0
  for (const b of Object.values(kanban)) totalTasks += b.task_count || 0

  return [
    { label: 'GATEWAY', value: gwState },
    { label: 'PROFILES', value: profiles },
    { label: 'SESSIONS TODAY', value: sessionsToday || Object.keys(sessions).length || '--' },
    { label: 'TOKENS', value: fmtTokens(tokens) },
    { label: 'KANBAN TASKS', value: totalTasks },
  ]
})
</script>

<style scoped>
.stats-strip {
  display: grid;
  grid-template-columns: repeat(5, 1fr);
  gap: 1px;
  background: var(--line);
  border: 1px solid var(--line);
  margin-bottom: 28px;
}
.stat-box {
  background: var(--bg-surface);
  padding: 16px 20px;
  text-align: center;
}
.stat-label {
  font-family: var(--font-mono);
  font-size: 9px;
  letter-spacing: 0.22em;
  color: var(--text-dim);
  text-transform: uppercase;
  margin-bottom: 6px;
}
.stat-value {
  font-family: var(--font-display);
  font-size: 22px;
  font-weight: 700;
  color: var(--text-hi);
  letter-spacing: 0.04em;
}
@media (max-width: 720px) {
  .stats-strip { grid-template-columns: repeat(2, 1fr); }
  .stat-value { font-size: 18px; }
}
</style>
