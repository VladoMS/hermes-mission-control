<template>
  <div class="overview-page section">
    <div class="section-head">
      <div class="title-block">
        <div class="eyebrow">OVERVIEW</div>
        <div class="display large">MISSION CONTROL</div>
      </div>
    </div>

    <GlanceStrip />
    <StatsStrip />
    <DirectiveCycler />

    <div class="overview-grid">
      <div class="grid-left">
        <RadarCanvas />
        <ThroughputCard />
        <VpsHealth />
      </div>
      <div class="grid-right">
        <SystemStatus />
        <ActivityFeed />
      </div>
    </div>

    <!-- Ops Footer -->
    <div class="ops-footer panel">
      <div class="eyebrow amber">OPERATIONS</div>
      <div class="ops-grid">
        <div class="ops-cell">
          <div class="ops-label">Queue Depth</div>
          <div class="ops-val" v-if="ops.loading.queueDepth"><span class="loading-text">LOADING...</span></div>
          <div class="ops-val" v-else>{{ ops.queueDepth }}</div>
        </div>
        <div class="ops-cell">
          <div class="ops-label">Total Sessions</div>
          <div class="ops-val" v-if="ops.loading.sessionCount"><span class="loading-text">LOADING...</span></div>
          <div class="ops-val" v-else>{{ ops.sessionCount }}</div>
        </div>
        <div class="ops-cell">
          <div class="ops-label">Errors</div>
          <div class="ops-val" :class="{ bad: ops.errors > 0 }">{{ ops.errors }}</div>
        </div>
        <div class="ops-cell">
          <div class="ops-label">Tasks Today</div>
          <div class="ops-val" v-if="ops.loading.tasksToday"><span class="loading-text">LOADING...</span></div>
          <div class="ops-val" v-else>{{ ops.tasksToday }}</div>
        </div>
        <div class="ops-cell">
          <div class="ops-label">Uptime</div>
          <div class="ops-val" v-if="ops.loading.uptime"><span class="loading-text">LOADING...</span></div>
          <div class="ops-val" v-else>{{ ops.uptime }}</div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { useSnapshotStore } from '../stores/snapshotStore.js'
import StatsStrip from '../components/StatsStrip.vue'
import GlanceStrip from '../components/GlanceStrip.vue'
import RadarCanvas from '../components/RadarCanvas.vue'
import ThroughputCard from '../components/ThroughputCard.vue'
import DirectiveCycler from '../components/DirectiveCycler.vue'
import SystemStatus from '../components/SystemStatus.vue'
import VpsHealth from '../components/VpsHealth.vue'
import ActivityFeed from '../components/ActivityFeed.vue'

const store = useSnapshotStore()
const snap = store

const ops = computed(() => {
  const d = snap.data
  if (!d) return {
    queueDepth: '--', sessionCount: '--', errors: '--', tasksToday: '--', uptime: '--',
    loading: { queueDepth: true, sessionCount: true, errors: true, tasksToday: true, uptime: true }
  }

  // Loading detection: is each channel loaded yet?
  const kanbanLoaded = store.isChannelLoaded('kanban')
  const sessionsLoaded = store.isChannelLoaded('sessions_ledger')
  const vpsLoaded = store.isChannelLoaded('vps')

  // — Kanban-derived values —
  const boards = d.kanban?.boards || {}
  let queue = 0, today = 0
  if (kanbanLoaded) {
    const todayStr = new Date().toISOString().slice(0, 10)
    for (const b of Object.values(boards)) {
      const cols = b.columns || {}
      queue += (cols.backlog || []).length + (cols.in_progress || []).length
      for (const col of Object.values(cols)) {
        for (const t of col) {
          if (t.created_at) {
            const ds = new Date(t.created_at * 1000).toISOString().slice(0, 10)
            if (ds === todayStr) today++
          }
        }
      }
    }
  }

  // — Uptime —
  let uptime = '--'
  if (vpsLoaded) {
    const u = d.vps?.hermes?.uptime
    if (u != null) {
      const days = Math.floor(u / 86400)
      const hrs = Math.floor((u % 86400) / 3600)
      uptime = days + 'd ' + hrs + 'h'
    }
  }

  return {
    queueDepth: kanbanLoaded ? queue : '--',
    sessionCount: sessionsLoaded ? (d.sessions_ledger?.session_count || d.sessions?.length || 0) : '--',
    errors: (d.errors || []).length,
    tasksToday: kanbanLoaded ? today : '--',
    uptime,
    loading: {
      queueDepth: !kanbanLoaded,
      sessionCount: !sessionsLoaded,
      errors: false,  // errors array is always collected with the snapshot
      tasksToday: !kanbanLoaded,
      uptime: !vpsLoaded,
    }
  }
})
</script>

<style scoped>
.overview-page { position: relative; z-index: 5; overflow-x: hidden; }
.overview-grid {
  display: grid;
  grid-template-columns: 1fr 2fr;
  gap: 20px;
  margin-bottom: 28px;
  min-height: 0;
}
.grid-left, .grid-right {
  display: flex;
  flex-direction: column;
  gap: 20px;
  min-height: 0;
  min-width: 0;
}

/* Ops footer */
.ops-footer { padding: 18px; }
.ops-grid {
  display: grid;
  grid-template-columns: repeat(5, 1fr);
  gap: 1px;
  background: var(--line);
  margin-top: 14px;
}
.ops-cell {
  background: var(--bg-deep);
  padding: 12px;
  text-align: center;
}
.ops-label {
  font-family: var(--font-mono);
  font-size: 9px;
  letter-spacing: 0.12em;
  color: var(--text-dim);
  text-transform: uppercase;
  margin-bottom: 4px;
}
.ops-val {
  font-family: var(--font-display);
  font-size: 18px;
  font-weight: 600;
  color: var(--amber-soft);
}
.ops-val.bad { color: var(--red); }

@media (max-width: 720px) {
  .overview-grid { grid-template-columns: 1fr; }
  .ops-grid { grid-template-columns: repeat(3, 1fr); }
  .ops-val { font-size: 15px; }
}
@media (max-width: 480px) {
  .ops-grid { grid-template-columns: repeat(2, 1fr); }
  .ops-label { font-size: 8px; }
  .ops-val { font-size: 14px; }
}
@media (max-width: 360px) {
  .ops-grid { grid-template-columns: 1fr; }
}
</style>
