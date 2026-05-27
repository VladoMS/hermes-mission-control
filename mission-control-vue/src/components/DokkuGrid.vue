<template>
  <div class="dokku-grid">
    <div v-for="app in apps" :key="app.name" class="dokku-card">
      <!-- App header -->
      <div class="app-header">
        <span class="app-dot" :style="{ background: appDotColor(app) }"></span>
        <span class="app-name">{{ app.name }}</span>
        <span class="app-containers mono">{{ app.containers.length }} ctr</span>
      </div>

      <!-- Container rows -->
      <div class="app-containers-list">
        <div v-for="ctr in app.containers" :key="ctr.name" class="ctr-row">
          <span class="ctr-name mono">{{ ctr.shortName }}</span>
          <span class="ctr-status" :class="ctr.statusClass">{{ ctr.statusShort }}</span>
          <div class="ctr-bars">
            <div class="ctr-bar-row">
              <span class="ctr-bar-label">CPU</span>
              <div class="ctr-bar"><div class="fill" :style="barStyle(ctr.stats?.cpu_pct, 'cpu')"></div></div>
              <span class="ctr-bar-pct" :style="{ color: pctColor(ctr.stats?.cpu_pct) }">{{ fmtPct(ctr.stats?.cpu_pct) }}</span>
            </div>
            <div class="ctr-bar-row">
              <span class="ctr-bar-label">MEM</span>
              <div class="ctr-bar"><div class="fill" :style="barStyle(ctr.stats?.mem_pct, 'mem')"></div></div>
              <span class="ctr-bar-pct" :style="{ color: pctColor(ctr.stats?.mem_pct) }">{{ fmtPct(ctr.stats?.mem_pct) }}</span>
            </div>
          </div>
        </div>
      </div>

      <!-- Logs button -->
      <button class="btn ghost app-logs-btn" @click="$emit('openLogs', app.name)">
        LOGS
      </button>
    </div>

    <div v-if="apps.length === 0" class="grid-empty mono">No Dokku apps</div>
  </div>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  dokku: { type: Object, default: null },
  serverName: { type: String, default: '' },
})
defineEmits(['openLogs'])

const COLORS = ['#ff3b1f', '#1ec8ff', '#4ade80', '#ffb020', '#d946ef', '#fbbf24', '#5cd9ff', '#ffc657']

const apps = computed(() => {
  if (!props.dokku) return []
  const appNames = props.dokku.apps || []
  const containers = props.dokku.containers || []
  const stats = props.dokku.container_stats || {}

  return appNames.map((name, idx) => {
    // Find containers belonging to this app (e.g., "appname.web.1" or "appname.scheduler.1")
    const appContainers = containers.filter(c =>
      c.name === name + '.web.1' || c.name.startsWith(name + '.')
    )
    return {
      name,
      color: COLORS[idx % COLORS.length],
      containers: appContainers.map(c => ({
        ...c,
        shortName: c.name.replace(name + '.', ''),
        statusShort: statusShort(c.status),
        statusClass: statusClass(c.status),
        stats: stats[c.name] || null,
      })),
    }
  })
})

function appDotColor(app) { return app.color }

function statusShort(status) {
  if (!status) return '--'
  if (status.toLowerCase().includes('up')) return 'UP'
  if (status.toLowerCase().includes('exited')) return 'DOWN'
  return status.slice(0, 12)
}

function statusClass(status) {
  if (!status) return ''
  if (status.toLowerCase().includes('up')) return 'up'
  return 'down'
}

function fmtPct(v) { return v != null ? Math.round(v) + '%' : '--' }
function pctColor(v) {
  if (v == null) return 'var(--text-faint)'
  if (v > 85) return 'var(--red)'
  if (v > 70) return 'var(--amber)'
  return 'var(--text-dim)'
}
function barStyle(v, type) {
  if (v == null) return { width: '0%' }
  const p = Math.min(v, 100)
  return { width: p + '%' }
}
</script>

<style scoped>
.dokku-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 10px;
}
.grid-empty {
  grid-column: 1 / -1;
  text-align: center;
  color: var(--text-faint);
  font-size: 10px;
  padding: 20px 0;
}
.dokku-card {
  background: var(--bg-deep);
  border: 1px solid var(--line);
  padding: 12px;
}
.app-header {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-bottom: 8px;
}
.app-dot { width: 6px; height: 6px; border-radius: 50%; flex-shrink: 0; }
.app-name {
  font-family: var(--font-body);
  font-size: 12px;
  font-weight: 600;
  color: var(--text-hi);
  flex: 1;
}
.app-containers { font-size: 9px; color: var(--text-faint); }
.app-containers-list { margin-bottom: 8px; }
.ctr-row {
  padding: 4px 0;
  border-bottom: 1px solid rgba(255,255,255,0.03);
}
.ctr-name {
  font-size: 9px;
  color: var(--text-dim);
  margin-bottom: 2px;
}
.ctr-status { font-size: 8px; margin-left: 4px; }
.ctr-status.up { color: var(--green); }
.ctr-status.down { color: var(--red); }

.ctr-bars { margin-top: 2px; }
.ctr-bar-row {
  display: flex;
  align-items: center;
  gap: 4px;
  margin-bottom: 1px;
}
.ctr-bar-label {
  font-family: var(--font-mono);
  font-size: 7px;
  color: var(--text-faint);
  width: 18px;
}
.ctr-bar {
  flex: 1;
  height: 3px;
  background: rgba(255,255,255,0.06);
  overflow: hidden;
}
.ctr-bar .fill {
  height: 100%;
  min-width: 0;
  background: linear-gradient(90deg, var(--green), var(--amber));
  transition: width 0.4s;
}
.ctr-bar-pct {
  font-family: var(--font-mono);
  font-size: 7px;
  width: 22px;
  text-align: right;
}
.app-logs-btn {
  width: 100%;
  justify-content: center;
  font-size: 9px;
  padding: 6px 10px;
}

@media (max-width: 1100px) {
  .dokku-grid { grid-template-columns: repeat(2, 1fr); }
}
@media (max-width: 720px) {
  .dokku-grid { grid-template-columns: 1fr; }
}
</style>
