<template>
  <div class="vps-health panel">
    <div class="eyebrow">VPS HEALTH</div>
    <div class="health-grid">
      <div v-for="host in hosts" :key="host.key" class="health-host">
        <div class="host-name">{{ host.label }}</div>
        <div v-if="host.loading" class="loading-text">LOADING...</div>
        <div v-else-if="!host.data" class="host-empty">No data</div>
        <template v-else>
          <div class="health-bar-row">
            <div class="health-label">CPU</div>
            <div class="health-bar"><div class="fill" :style="barStyle(host.data.cpu_pct, 'cpu')"></div></div>
            <div class="health-pct" :style="{ color: pctColor(host.data.cpu_pct) }">{{ pct(host.data.cpu_pct) }}</div>
          </div>
          <div class="health-bar-row">
            <div class="health-label">RAM</div>
            <div class="health-bar"><div class="fill" :style="barStyle(host.data.mem_pct, 'ram')"></div></div>
            <div class="health-pct" :style="{ color: pctColor(host.data.mem_pct) }">{{ pct(host.data.mem_pct) }}</div>
          </div>
          <div class="health-bar-row">
            <div class="health-label">DISK</div>
            <div class="health-bar"><div class="fill" :style="barStyle(host.data.disk_pct, 'disk')"></div></div>
            <div class="health-pct" :style="{ color: pctColor(host.data.disk_pct) }">{{ pct(host.data.disk_pct) }}</div>
          </div>
        </template>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { useSnapshotStore } from '../stores/snapshotStore.js'

const snap = useSnapshotStore()

const hosts = computed(() => {
  const d = snap.data
  // Before ANY data arrives: both hosts loading
  if (!d) {
    return [
      { key: 'hermes', label: 'HERMES VPS', data: null, loading: true },
      { key: 'prod', label: 'PRODUCTION', data: null, loading: true },
    ]
  }

  const vps = d.vps || {}
  const result = []

  // Hermes — always configured (local /proc)
  const hermes = vps.hermes
  if (hermes && (hermes.cpu_pct != null || (hermes.mem && hermes.mem.mem_pct != null))) {
    result.push({
      key: 'hermes', label: 'HERMES VPS', loading: false,
      data: {
        cpu_pct: hermes.cpu_pct ?? null,
        mem_pct: hermes.mem?.mem_pct ?? null,
        disk_pct: hermes.disk?.disk_pct_display ?? hermes.disk?.disk_pct ?? null,
      },
    })
  } else {
    result.push({
      key: 'hermes', label: 'HERMES VPS', data: null,
      loading: true,  // waiting for hermes-health channel
    })
  }

  // Prod — only configured if it appears with real data
  const prod = vps.prod
  if (prod && (prod.cpu_pct != null || (prod.mem && prod.mem.mem_pct != null) || prod.ssh_ok !== undefined)) {
    result.push({
      key: 'prod', label: 'PRODUCTION', loading: false,
      data: {
        cpu_pct: prod.cpu_pct ?? null,
        mem_pct: prod.mem?.mem_pct ?? null,
        disk_pct: prod.disk?.disk_pct_display ?? prod.disk?.disk_pct ?? null,
      },
    })
  } else if (prod && Object.keys(prod).length === 0) {
    // Empty prod object — not configured, no prod in servers.json
    result.push({ key: 'prod', label: 'PRODUCTION', data: null, loading: false })
  } else {
    // No prod data yet — either not configured or still loading
    result.push({ key: 'prod', label: 'PRODUCTION', data: null, loading: true })
  }

  return result
})

function pct(v) { return v != null ? v.toFixed(0) + '%' : '--' }
function pctColor(v) {
  if (v == null) return 'var(--text-faint)'
  if (v > 85) return 'var(--red)'
  if (v > 70) return 'var(--amber)'
  return 'var(--text-dim)'
}
function barStyle(v, type) {
  if (v == null) return { width: '0%' }
  const p = Math.min(v, 100)
  let bg = ''
  if (v > 85) bg = 'var(--red)'
  else if (v > 70) bg = 'var(--amber)'
  return { width: p + '%', background: bg || undefined }
}
</script>

<style scoped>
.vps-health { padding: 18px; margin-bottom: 28px; }
.health-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 20px;
  margin-top: 14px;
}
.host-name {
  font-family: var(--font-mono);
  font-size: 10px;
  letter-spacing: 0.15em;
  color: var(--text-dim);
  text-transform: uppercase;
  margin-bottom: 10px;
}
.host-empty {
  font-family: var(--font-mono);
  font-size: 10px;
  color: var(--text-faint);
}
.health-bar-row {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 6px;
}
.health-label {
  font-family: var(--font-mono);
  font-size: 9px;
  letter-spacing: 0.1em;
  color: var(--text-faint);
  width: 28px;
}
.health-bar {
  flex: 1;
  height: 5px;
  background: rgba(255, 255, 255, 0.06);
  overflow: hidden;
}
.health-bar .fill {
  height: 100%;
  min-width: 0;
  background: linear-gradient(90deg, var(--green), var(--amber));
  transition: width 0.4s;
}
.health-pct {
  font-family: var(--font-mono);
  font-size: 10px;
  width: 34px;
  text-align: right;
}
@media (max-width: 720px) {
  .health-grid { grid-template-columns: 1fr; }
}
</style>
