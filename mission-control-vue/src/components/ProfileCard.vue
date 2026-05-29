<template>
  <div class="profile-card panel" :class="{ 'panel-glow': profile.status === 'active' }">
    <div class="card-top">
      <span class="prof-dot" :style="{ background: statusColor, boxShadow: '0 0 8px ' + statusColor }"></span>
      <span class="prof-name">{{ profile.name }}</span>
      <span class="prof-badge chip" :style="{ borderLeftColor: accent, color: accent, background: accent + '20' }">{{ badge }}</span>
    </div>
    <div class="card-stats">
      <div class="card-stat">
        <div class="cs-label">Sessions</div>
        <div class="cs-val">{{ stats.sessionCount }}</div>
      </div>
      <div class="card-stat">
        <div class="cs-label">Messages</div>
        <div class="cs-val">{{ stats.messageCount }}</div>
      </div>
      <div class="card-stat">
        <div class="cs-label">Tokens</div>
        <div class="cs-val">{{ stats.tokenCount }}</div>
      </div>
      <div class="card-stat">
        <div class="cs-label">Last Active</div>
        <div class="cs-val">{{ stats.lastActive }}</div>
      </div>
    </div>
    <div class="card-status" :style="{ color: statusColor }">
      {{ statusLabel }}
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { useProfilesStore } from '../stores/profiles.js'

const props = defineProps({
  profile: { type: Object, required: true },
})

const profilesStore = useProfilesStore()

const accent = computed(() => profilesStore.getAccent(props.profile.name))
const badge = computed(() => profilesStore.getBadge(props.profile.name))

function fmtTokens(n) {
  if (!n && n !== 0) return '--'
  if (n >= 1e6) return (n / 1e6).toFixed(1) + 'M'
  if (n >= 1e3) return (n / 1e3).toFixed(1) + 'K'
  return String(n)
}

function ago(ts) {
  if (!ts) return '--'
  const diff = (Date.now() / 1000) - ts
  if (diff < 60) return Math.floor(diff) + 's'
  if (diff < 3600) return Math.floor(diff / 60) + 'm'
  if (diff < 86400) return Math.floor(diff / 3600) + 'h'
  if (diff < 604800) return Math.floor(diff / 86400) + 'd'
  return Math.floor(diff / 604800) + 'w'
}

const stats = computed(() => {
  const s = props.profile.state_db_stats || {}
  const recent = s.recent_sessions || []
  const lastTs = recent.length ? recent[0].started_at : null
  return {
    sessionCount: s.session_count || 0,
    messageCount: s.message_count || 0,
    tokenCount: fmtTokens((s.total_input_tokens || 0) + (s.total_output_tokens || 0)),
    lastActive: ago(lastTs),
  }
})

const statusLabel = computed(() => {
  const status = profilesStore.getStatus(props.profile)
  if (status === 'active') return 'ACTIVE'
  if (status === 'idle') return 'IDLE'
  return 'DORMANT'
})

const statusColor = computed(() => {
  const status = profilesStore.getStatus(props.profile)
  if (status === 'active') return 'var(--green)'
  if (status === 'idle') return 'var(--amber)'
  return 'var(--text-faint)'
})
</script>

<style scoped>
.profile-card { padding: 18px; }
.card-top { display: flex; align-items: center; gap: 8px; margin-bottom: 12px; }
.prof-dot { width: 8px; height: 8px; border-radius: 50%; flex-shrink: 0; }
.prof-name {
  font-family: var(--font-display);
  font-size: 16px;
  font-weight: 600;
  letter-spacing: 0.06em;
  color: var(--text-hi);
  text-transform: uppercase;
}
.prof-badge { margin-left: auto; font-size: 9px; }
.card-stats {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 1px;
  background: var(--line-dim);
}
.card-stat {
  background: var(--bg-deep);
  padding: 8px;
  text-align: center;
}
.cs-label {
  font-family: var(--font-mono);
  font-size: 10px;
  color: var(--text-faint);
  text-transform: uppercase;
  letter-spacing: 0.1em;
  margin-bottom: 2px;
}
.cs-val {
  font-family: var(--font-display);
  font-size: 14px;
  font-weight: 600;
  color: var(--text-hi);
}
.card-status {
  font-family: var(--font-mono);
  font-size: 10px;
  letter-spacing: 0.22em;
  text-transform: uppercase;
  margin-top: 10px;
}
</style>
