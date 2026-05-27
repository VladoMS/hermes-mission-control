<template>
  <div class="sys-status panel">
    <div class="eyebrow">SYSTEM STATUS</div>
    <div class="status-grid">
      <div class="ctx-stat">
        <div class="ctx-label">Active Sessions</div>
        <div class="ctx-stat-val">{{ stats.activeSessions }}</div>
      </div>
      <div class="ctx-stat">
        <div class="ctx-label">Blocked Tasks</div>
        <div class="ctx-stat-val" :class="stats.blockedTasks > 0 ? 'bad' : 'good'">{{ stats.blockedTasks }}</div>
      </div>
      <div class="ctx-stat">
        <div class="ctx-label">Errors</div>
        <div class="ctx-stat-val" :class="stats.errors > 0 ? 'bad' : 'good'">{{ stats.errors }}</div>
      </div>
      <div class="ctx-stat">
        <div class="ctx-label">Tokens Today</div>
        <div class="ctx-stat-val">{{ stats.tokensToday }}</div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { useSnapshotStore } from '../stores/snapshotStore.js'

const snap = useSnapshotStore()

function fmtTokens(n) {
  if (!n && n !== 0) return '--'
  if (n >= 1e6) return (n / 1e6).toFixed(1) + 'M'
  if (n >= 1e3) return (n / 1e3).toFixed(1) + 'K'
  return String(n)
}

const stats = computed(() => {
  const d = snap.data
  if (!d) return { activeSessions: '--', blockedTasks: '--', errors: '--', tokensToday: '--' }

  let totalSessions = 0
  for (const p of (d.profiles || [])) {
    const s = p.state_db_stats
    totalSessions += (s?.active_sessions || 0) + (s?.completed_sessions || 0)
  }

  const kanbanBoards = d.kanban?.boards || {}
  let blocked = 0
  for (const b of Object.values(kanbanBoards)) blocked += (b.columns?.blocked || []).length

  return {
    activeSessions: totalSessions,
    blockedTasks: blocked,
    errors: (d.errors || []).length,
    tokensToday: fmtTokens(d.sessions_ledger?.total_tokens || 0),
  }
})
</script>

<style scoped>
.sys-status { padding: 18px; margin-bottom: 28px; }
.status-grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 1px;
  background: var(--line);
  margin-top: 14px;
}
.ctx-stat {
  background: var(--bg-deep);
  padding: 14px;
  text-align: center;
}
.ctx-label {
  font-family: var(--font-mono);
  font-size: 9px;
  letter-spacing: 0.15em;
  color: var(--text-dim);
  text-transform: uppercase;
  margin-bottom: 6px;
}
.ctx-stat-val {
  font-family: var(--font-display);
  font-size: 20px;
  font-weight: 600;
  color: var(--text-hi);
}
.ctx-stat-val.good { color: var(--green); }
.ctx-stat-val.bad { color: var(--red); }
@media (max-width: 720px) {
  .status-grid { grid-template-columns: repeat(2, 1fr); }
}
</style>
