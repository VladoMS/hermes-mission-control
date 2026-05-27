<template>
  <div class="activity-log panel">
    <div class="eyebrow">RECENT ACTIVITY</div>
    <div v-if="activities.length === 0" class="log-empty">No recent activity</div>
    <table v-else class="log-table">
      <thead>
        <tr>
          <th>PROFILE</th>
          <th>ACTION</th>
          <th>WHEN</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="(a, i) in activities" :key="i">
          <td><span class="log-dot" :style="{ background: a.color }"></span> {{ a.profile }}</td>
          <td>{{ a.action }}</td>
          <td>{{ a.when }}</td>
        </tr>
      </tbody>
    </table>
  </div>
</template>

<script setup>
import { computed, ref, watch } from 'vue'
import { useSnapshotStore } from '../stores/snapshotStore.js'

const snap = useSnapshotStore()

const COLORS = {
  default: '#ff3b1f', coder: '#1ec8ff', researcher: '#4ade80',
  writer: '#ffb020', devops: '#d946ef', creative: '#fbbf24',
}

function ago(ts) {
  if (!ts) return ''
  const diff = (Date.now() / 1000) - ts
  if (diff < 60) return Math.floor(diff) + 's ago'
  if (diff < 3600) return Math.floor(diff / 60) + 'm ago'
  if (diff < 86400) return Math.floor(diff / 3600) + 'h ago'
  return Math.floor(diff / 86400) + 'd ago'
}

const activities = computed(() => {
  const d = snap.data
  if (!d) return []

  const result = []
  const sessions = d.sessions || []
  const recent = [...sessions].sort((a, b) => (b.started_at || 0) - (a.started_at || 0)).slice(0, 20)

  for (const s of recent) {
    result.push({
      profile: s.profile || 'unknown',
      color: COLORS[s.profile] || '#6b7585',
      action: s.display_name || s.title || 'session ' + (s.id || '').slice(0, 8),
      when: ago(s.started_at),
    })
  }

  // Add kanban activity
  const boards = d.kanban?.boards || {}
  for (const [bname, board] of Object.entries(boards)) {
    for (const colName of ['done']) {
      for (const task of (board.columns?.[colName] || []).slice(0, 5)) {
        result.push({
          profile: bname,
          color: '#4ade80',
          action: 'completed: ' + (task.title || task.id),
          when: ago(task.completed_at || task.created_at),
        })
      }
    }
  }

  result.sort((a, b) => {
    const aNum = parseInt(a.when) || 999
    const bNum = parseInt(b.when) || 999
    return aNum - bNum
  })
  return result.slice(0, 15)
})
</script>

<style scoped>
.activity-log { padding: 18px; }
.log-empty {
  font-family: var(--font-mono);
  font-size: 10px;
  color: var(--text-faint);
  padding: 20px 0;
}
.log-table { width: 100%; border-collapse: collapse; margin-top: 10px; }
.log-table th {
  font-family: var(--font-mono);
  font-size: 9px;
  letter-spacing: 0.15em;
  color: var(--text-dim);
  text-transform: uppercase;
  text-align: left;
  padding: 6px 8px;
  border-bottom: 1px solid var(--line);
}
.log-table td {
  font-family: var(--font-mono);
  font-size: 10px;
  color: var(--text-dim);
  padding: 5px 8px;
  border-bottom: 1px solid var(--line-dim);
}
.log-dot {
  display: inline-block;
  width: 6px;
  height: 6px;
  border-radius: 50%;
  margin-right: 4px;
  vertical-align: middle;
}
</style>
