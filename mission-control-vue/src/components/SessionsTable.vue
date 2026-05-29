<template>
  <div class="sessions-table panel">
    <div class="eyebrow">SESSIONS</div>

    <!-- Filters -->
    <div class="sess-filters">
      <select v-model="sessionsStore.filterProfile" class="sess-filter">
        <option value="all">ALL PROFILES</option>
        <option v-for="p in profilesInSessions" :key="p" :value="p">{{ p.toUpperCase() }}</option>
      </select>
      <select v-model="sessionsStore.filterModel" class="sess-filter">
        <option value="all">ALL MODELS</option>
        <option v-for="m in modelsInSessions" :key="m" :value="m">{{ m }}</option>
      </select>
    </div>

    <!-- Table -->
    <div class="sess-table-wrap">
      <table class="sess-table">
        <thead>
          <tr>
            <th class="col-prof">PROFILE</th>
            <th class="col-title">TITLE</th>
            <th class="col-msgs">MSG</th>
            <th class="col-tokens">TOKENS</th>
            <th class="col-date">DATE</th>
          </tr>
        </thead>
        <tbody>
          <tr v-if="filteredSessions.length === 0">
            <td colspan="5" class="sess-empty">No sessions found</td>
          </tr>
          <tr v-for="s in filteredSessions.slice(0, 50)" :key="s.id || s.session_id">
            <td class="col-prof">
              <div class="sess-prof">
                <span class="sess-prof-dot" :style="{ background: profileColor(s.profile) }"></span>
                <span class="sess-prof-name">{{ s.profile }}</span>
              </div>
            </td>
            <td class="col-title">
              <span class="sess-title" :title="s.display_name || s.id">{{ truncate(s.display_name || s.title || s.id, 50) }}</span>
            </td>
            <td class="col-msgs"><span class="sess-msgs">{{ s.message_count || 0 }}</span></td>
            <td class="col-tokens">
              <span class="sess-tokens" title="Input / Output / Cache tokens">
                <span class="tk-in" title="Input tokens">{{ fmtTokens(s.input_tokens) }}</span>
                <span class="tk-sep">/</span>
                <span class="tk-out" title="Output tokens">{{ fmtTokens(s.output_tokens) }}</span>
                <span class="tk-sep">/</span>
                <span class="tk-cache" title="Cache read+write tokens">{{ fmtTokens((s.cache_read_tokens || 0) + (s.cache_write_tokens || 0)) }}</span>
              </span>
            </td>
            <td class="col-date">
              <span class="sess-date">{{ fmtDate(s.started_at) }}</span>
            </td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { useSessionsStore } from '../stores/sessions.js'

const PROFILE_COLORS = {
  default: '#ff3b1f', coder: '#1ec8ff', researcher: '#4ade80',
  writer: '#ffb020', devops: '#d946ef', creative: '#fbbf24',
}

const sessionsStore = useSessionsStore()
const filteredSessions = computed(() => sessionsStore.filteredSessions)
const profilesInSessions = computed(() => sessionsStore.profilesInSessions)
const modelsInSessions = computed(() => sessionsStore.modelsInSessions)

function profileColor(name) {
  return PROFILE_COLORS[name] || '#ff3b1f'
}

function fmtTokens(n) {
  if (!n && n !== 0) return '--'
  if (n >= 1e6) return (n / 1e6).toFixed(1) + 'M'
  if (n >= 1e3) return (n / 1e3).toFixed(1) + 'K'
  return String(n)
}

function fmtDate(ts) {
  if (!ts) return '--'
  return new Date(ts * 1000).toISOString().slice(0, 10)
}

function truncate(s, max) {
  if (!s) return '--'
  return s.length > max ? s.slice(0, max - 3) + '...' : s
}
</script>

<style scoped>
.sessions-table { padding: 18px; }
.sess-filters {
  display: flex;
  gap: 8px;
  margin: 12px 0;
}
.sess-filter {
  background: var(--bg-deep);
  border: 1px solid var(--line);
  color: var(--text);
  font-family: var(--font-mono);
  font-size: 10px;
  padding: 6px 10px;
  letter-spacing: 0.08em;
}
.sess-table-wrap { overflow-x: auto; }
.sess-table { width: 100%; border-collapse: collapse; }
.sess-table th {
  font-family: var(--font-mono);
  font-size: 9px;
  letter-spacing: 0.15em;
  color: var(--text-dim);
  text-transform: uppercase;
  text-align: left;
  padding: 8px 10px;
  border-bottom: 1px solid var(--line);
  white-space: nowrap;
}
.sess-table td {
  padding: 6px 10px;
  border-bottom: 1px solid var(--line-dim);
  font-size: 11px;
  vertical-align: middle;
}
.col-prof { width: 100px; }
.col-title { min-width: 160px; }
.col-msgs { width: 40px; text-align: right; }
.col-tokens { width: 150px; }
.col-date { width: 90px; }
.sess-empty {
  font-family: var(--font-mono);
  font-size: 10px;
  color: var(--text-faint);
  text-align: center;
  padding: 20px;
}
.sess-prof { display: flex; align-items: center; gap: 6px; }
.sess-prof-dot {
  width: 6px; height: 6px; border-radius: 50%;
  flex-shrink: 0;
  box-shadow: 0 0 4px currentColor;
}
.sess-prof-name {
  font-family: var(--font-mono);
  font-size: 10px;
  color: var(--text-dim);
  text-transform: uppercase;
}
.sess-title {
  font-family: var(--font-body);
  font-size: 11px;
  color: var(--text);
}
.sess-msgs { font-family: var(--font-mono); font-size: 10px; color: var(--text-dim); }
.sess-tokens { font-family: var(--font-mono); font-size: 9px; }
.tk-in { color: var(--green); }
.tk-out { color: var(--cyan); }
.tk-cache { color: var(--amber-soft); }
.tk-sep { color: var(--text-faint); margin: 0 2px; }
.sess-date { font-family: var(--font-mono); font-size: 10px; color: var(--text-faint); }
</style>
