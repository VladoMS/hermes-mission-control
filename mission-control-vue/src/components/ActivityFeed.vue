<template>
  <div class="activity-feed panel">
    <div class="eyebrow">ACTIVITY</div>
    <div v-if="items.length === 0" class="feed-empty">Awaiting activity</div>
    <div v-for="(item, i) in items" :key="i" class="feed-item">
      <span class="feed-time">{{ item.time }}</span>
      <span class="feed-dot" :style="{ background: item.color }"></span>
      <span class="feed-text">{{ item.text }}</span>
    </div>
  </div>
</template>

<script setup>
import { ref, watch } from 'vue'
import { useSessionsStore } from '../stores/sessions.js'
import { useKanbanStore } from '../stores/kanban.js'
import { useProfilesStore } from '../stores/profiles.js'

const sess = useSessionsStore()
const kan = useKanbanStore()
const prof = useProfilesStore()

let lastFeedKey = ''

const PROFILE_COLORS = {
  default: '#ff3b1f', coder: '#1ec8ff', researcher: '#4ade80',
  writer: '#ffb020', devops: '#d946ef', creative: '#fbbf24',
}

function ago(ts) {
  if (!ts) return ''
  const diff = (Date.now() / 1000) - ts
  if (diff < 60) return Math.floor(diff) + 's'
  if (diff < 3600) return Math.floor(diff / 60) + 'm'
  if (diff < 86400) return Math.floor(diff / 3600) + 'h'
  return Math.floor(diff / 86400) + 'd'
}

const items = ref([])

function rebuild() {
  const newKey = JSON.stringify([prof.data?.length, sess.sessions?.length])
  if (newKey === lastFeedKey) return
  lastFeedKey = newKey

  const result = []

  const sessions = sess.sessions || []
  const recent = [...sessions].sort((a, b) => (b.started_at || 0) - (a.started_at || 0)).slice(0, 6)
  for (const s of recent) {
    result.push({
      _ts: s.started_at || 0,
      time: ago(s.started_at),
      color: PROFILE_COLORS[s.profile] || '#6b7585',
      text: (s.display_name || s.title || s.id || 'session') + ' · ' + (s.profile || 'unknown'),
    })
  }

  const boards = kan.data?.boards || {}
  for (const [bname, board] of Object.entries(boards)) {
    const cols = board.columns || {}
    for (const colName of ['in_progress', 'done']) {
      for (const task of (cols[colName] || []).slice(0, 3)) {
        const ts = task.completed_at || task.started_at || task.created_at || 0
        const status = colName === 'done' ? 'completed' : 'in progress'
        result.push({
          _ts: ts,
          time: ago(ts),
          color: colName === 'done' ? '#4ade80' : '#ffb020',
          text: status + ': ' + (task.title || task.id) + ' [' + bname + ']',
        })
      }
    }
  }

  result.sort((a, b) => (b._ts || 0) - (a._ts || 0))
  items.value = result.slice(0, 12)
}

watch([() => sess.sessions, () => kan.data, () => prof.data], rebuild, { deep: true })
rebuild()
</script>

<style scoped>
.activity-feed { padding: 18px; }
.feed-empty {
  font-family: var(--font-mono);
  font-size: 10px;
  color: var(--text-faint);
  padding: 20px 0;
}
.feed-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 0;
  border-bottom: 1px solid var(--line-dim);
  font-family: var(--font-mono);
  font-size: 10px;
}
.feed-time {
  color: var(--text-faint);
  min-width: 30px;
}
.feed-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  flex-shrink: 0;
  box-shadow: 0 0 4px currentColor;
}
.feed-text { color: var(--text-dim); flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
</style>
