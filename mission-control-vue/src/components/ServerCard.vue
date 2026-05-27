<template>
  <div class="server-card panel" :class="{ 'panel-glow': server.has_dokku }">
    <!-- Header -->
    <div class="srv-header">
      <div class="srv-info">
        <span class="status-dot" :class="healthDotClass"></span>
        <span class="srv-name">{{ server.display || server.name }}</span>
        <span class="chip" v-if="server.type" :class="server.type === 'vps' ? 'red' : 'cyan'">{{ server.type.toUpperCase() }}</span>
      </div>
      <div class="srv-notes mono" v-if="server.notes">{{ server.notes }}</div>
    </div>

    <!-- Health -->
    <div class="srv-section">
      <div class="srv-section-head" @click="toggleSection('health')" :class="{ open: sections.health }">
        <span class="srv-section-arrow">▶</span>
        <span>HEALTH</span>
      </div>
      <div class="srv-section-body" :class="{ open: sections.health }">
        <HealthBar label="CPU" :pct="health.cpu_pct" />
        <HealthBar label="RAM" :pct="health.mem_pct" />
        <HealthBar label="DSK" :pct="health.disk_pct" />
        <div v-if="health.ssh_ok === false" class="srv-warn">SSH connection failed</div>
      </div>
    </div>

    <!-- Cron jobs -->
    <div class="srv-section" v-if="crons.length">
      <div class="srv-section-head" @click="toggleSection('crons')" :class="{ open: sections.crons }">
        <span class="srv-section-arrow">▶</span>
        <span>{{ server.cron_label || 'CRON JOBS' }} ({{ crons.length }})</span>
      </div>
      <div class="srv-section-body" :class="{ open: sections.crons }">
        <div v-for="(cron, i) in crons" :key="i" class="cron-row">
          <span class="cron-schedule mono">{{ cron.schedule_display || cron.schedule || '--' }}</span>
          <span class="cron-name">{{ cron.name || cron.command || '--' }}</span>
        </div>
      </div>
    </div>

    <!-- Dokku -->
    <div class="srv-section" v-if="server.has_dokku">
      <div class="srv-section-head" @click="toggleSection('dokku')" :class="{ open: sections.dokku }">
        <span class="srv-section-arrow">▶</span>
        <span>DOKKU ({{ dokkuAppCount }} apps)</span>
      </div>
      <div class="srv-section-body" :class="{ open: sections.dokku }">
        <div v-if="!server.dokku" class="srv-warn">No Dokku data available</div>
        <template v-else>
          <div v-if="server.dokku.errors?.length" class="srv-warn">{{ server.dokku.errors.join(', ') }}</div>
          <DokkuGrid
            :dokku="server.dokku"
            :server-name="server.name"
            @open-logs="openLogs"
          />
        </template>
      </div>
    </div>

    <!-- Log viewer modal -->
    <LogViewer
      :visible="logsVisible"
      :app-name="logsApp"
      :server-name="server.name"
      @close="logsVisible = false"
    />
  </div>
</template>

<script setup>
import { computed, reactive, ref } from 'vue'
import HealthBar from './HealthBar.vue'
import DokkuGrid from './DokkuGrid.vue'
import LogViewer from './LogViewer.vue'

const props = defineProps({
  server: { type: Object, required: true },
})

const sections = reactive({ health: true, crons: false, dokku: false })
const logsVisible = ref(false)
const logsApp = ref('')

function toggleSection(key) {
  sections[key] = !sections[key]
}

function openLogs(appName) {
  logsApp.value = appName
  logsVisible.value = true
}

const health = computed(() => {
  const h = props.server.health || {}
  return {
    cpu_pct: h.cpu_pct ?? null,
    mem_pct: h.mem?.mem_pct ?? null,
    disk_pct: h.disk?.disk_pct_display ?? h.disk?.disk_pct ?? null,
    ssh_ok: h.ssh_ok,
  }
})

const healthDotClass = computed(() => {
  if (health.value.ssh_ok === false) return 'red'
  const cpu = health.value.cpu_pct
  if (cpu != null && cpu > 85) return 'amber'
  return ''
})

const crons = computed(() => props.server.crons || [])
const dokkuAppCount = computed(() => props.server.dokku?.apps?.length || 0)
</script>

<style scoped>
.server-card { padding: 18px; margin-bottom: 16px; }
.srv-header { margin-bottom: 14px; }
.srv-info { display: flex; align-items: center; gap: 8px; }
.srv-name {
  font-family: var(--font-display);
  font-size: 16px;
  font-weight: 600;
  letter-spacing: 0.04em;
  color: var(--text-hi);
}
.srv-notes { margin-top: 4px; font-size: 10px; color: var(--text-faint); }

.srv-section { margin-bottom: 8px; }
.srv-section-head {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 0;
  cursor: pointer;
  font-family: var(--font-mono);
  font-size: 10px;
  letter-spacing: 0.12em;
  color: var(--text-dim);
  text-transform: uppercase;
  border-bottom: 1px solid var(--line-dim);
  user-select: none;
}
.srv-section-head:hover { color: var(--text); }
.srv-section-arrow { font-size: 7px; transition: transform 0.2s; }
.srv-section-head.open .srv-section-arrow { transform: rotate(90deg); }
.srv-section-body { display: none; padding: 10px 0; }
.srv-section-body.open { display: block; }
.srv-warn {
  font-family: var(--font-mono);
  font-size: 10px;
  color: var(--red);
  padding: 6px 0;
}
.cron-row {
  display: flex;
  gap: 12px;
  padding: 3px 0;
  font-size: 10px;
  border-bottom: 1px solid rgba(255,255,255,0.03);
}
.cron-schedule { color: var(--amber-soft); min-width: 60px; font-size: 9px; }
.cron-name { color: var(--text-dim); }
</style>
