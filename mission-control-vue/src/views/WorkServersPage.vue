<template>
  <div class="work-servers-page section">
    <div class="section-head">
      <div class="title-block">
        <div class="eyebrow">WORK SERVERS</div>
        <div class="display medium">{{ servers.length }} WORK SERVERS</div>
      </div>
      <div class="last-updated mono" v-if="lastUpdate">
        Last update: {{ lastUpdate }}
      </div>
    </div>

    <!-- Tier 1: Summary strip -->
    <div v-if="servers.length" class="summary-strip panel">
      <div class="summary-cell">
        <div class="summary-label mono">Servers</div>
        <div class="summary-val">{{ servers.length }}</div>
      </div>
      <div class="summary-cell">
        <div class="summary-label mono">Healthy</div>
        <div class="summary-val green">{{ healthyCount }}</div>
      </div>
      <div class="summary-cell">
        <div class="summary-label mono">Warning</div>
        <div class="summary-val amber">{{ warningCount }}</div>
      </div>
      <div class="summary-cell">
        <div class="summary-label mono">Critical</div>
        <div class="summary-val red">{{ criticalCount }}</div>
      </div>
      <div class="summary-cell">
        <div class="summary-label mono">Containers</div>
        <div class="summary-val">{{ totalRunningContainers }} / {{ totalContainers }}</div>
      </div>
    </div>

    <div v-if="servers.length === 0" class="empty-state panel">
      <div class="placeholder-panel" style="color: var(--text-dim)">Collecting data... first poll at 15-minute intervals.</div>
    </div>

    <div v-for="srv in servers" :key="srv.key" class="server-card panel">
      <!-- Header -->
      <div class="card-header">
        <span class="status-dot" :class="healthClass(srv.health)"></span>
        <span class="server-name">{{ srv.hostname || srv.serverName }}</span>
        <span class="server-group chip">{{ srv.ansibleGroup }}</span>
      </div>

      <!-- Health bars -->
      <div class="health-grid" v-if="srv.health.cpu_pct !== undefined">
        <HealthBar label="CPU" :pct="srv.health.cpu_pct" unit="%" color="var(--cyan)" />
        <HealthBar label="MEM" :pct="srv.health.memory?.pct" unit="%" :color="memColor(srv.health.memory?.pct)" />
        <HealthBar label="DISK" :pct="srv.health.disk?.pct" unit="%" :color="diskColor(srv.health.disk?.pct)" />
        <div class="health-meta">
          <span class="mono">Load: {{ srv.health.load?.load_1m || '--' }}</span>
          <span class="mono">Up: {{ fmtUptime(srv.health.uptime_hours) }}</span>
        </div>
      </div>

      <!-- Docker panel -->
      <div v-if="srv.docker && !srv.docker.error" class="role-panel">
        <div class="role-header">◆ DOCKER</div>
        <div class="role-grid">
          <div class="role-stat">
            <span class="role-label mono">Running</span>
            <span class="role-val">{{ srv.docker.running_count || 0 }} / {{ srv.docker.total_containers || 0 }}</span>
          </div>
          <div class="role-stat">
            <span class="role-label mono">Stopped</span>
            <span class="role-val dim">{{ srv.docker.stopped_count || 0 }}</span>
          </div>
          <div class="role-stat">
            <span class="role-label mono">Images</span>
            <span class="role-val">{{ srv.docker.image_count || 0 }}</span>
          </div>
          <div class="role-stat">
            <span class="role-label mono">Swarm</span>
            <span class="role-val" :class="srv.docker.swarm_state === 'active' ? 'green' : ''">{{ srv.docker.swarm_state || '--' }}</span>
          </div>
        </div>
        <!-- Stopped containers -->
        <div v-if="srv.docker.stopped?.length" class="role-subpanel">
          <div class="role-subheader mono">RECENTLY STOPPED</div>
          <div v-for="c in srv.docker.stopped.slice(0, 8)" :key="c.name" class="swarm-svc-row">
            <span class="svc-name mono">{{ c.name }}</span>
            <span class="mono dim stopped-status">{{ c.status }}</span>
          </div>
        </div>
        <!-- Swarm services -->
        <div v-if="srv.docker.swarm_services?.length" class="swarm-services">
          <div class="role-subheader mono">SWARM SERVICES</div>
          <div v-for="svc in srv.docker.swarm_services" :key="svc.name" class="swarm-svc-row">
            <span class="svc-name mono">{{ svc.name }}</span>
            <span class="svc-replicas mono">{{ svc.replicas }}</span>
          </div>
        </div>
      </div>

      <!-- Nexus panel -->
      <div v-if="srv.nexus && !srv.nexus.error" class="role-panel">
        <div class="role-header">◆ NEXUS</div>
        <div class="role-grid">
          <div class="role-stat">
            <span class="role-label mono">Repositories</span>
            <span class="role-val">{{ srv.nexus.repo_count || 0 }}</span>
          </div>
          <div class="role-stat">
            <span class="role-label mono">Blob Stores</span>
            <span class="role-val">{{ srv.nexus.blobstores?.length || 0 }}</span>
          </div>
        </div>
        <!-- Format breakdown -->
        <div v-if="srv.nexus.formats" class="role-subpanel">
          <div class="role-subheader mono">FORMATS</div>
          <div class="format-chips">
            <span v-for="(count, fmt) in srv.nexus.formats" :key="fmt" class="chip">{{ fmt }}: {{ count }}</span>
          </div>
        </div>
        <!-- Blob stores with sizes -->
        <div v-if="srv.nexus.blobstores?.length" class="role-subpanel">
          <div class="role-subheader mono">BLOB STORES</div>
          <div v-for="blob in srv.nexus.blobstores" :key="blob.name" class="blob-row">
            <span class="mono">{{ blob.name }}</span>
            <span class="mono dim">{{ blob.blobCount || 0 }} blobs</span>
            <span class="mono dim">{{ blob.size_gb ? blob.size_gb + ' GB' : blob.disk_usage || '--' }}</span>
          </div>
        </div>
      </div>

      <!-- Jenkins panel -->
      <div v-if="srv.jenkins && !srv.jenkins.error" class="role-panel">
        <div class="role-header">◆ JENKINS <span class="jenkins-type chip">{{ srv.jenkinsType || '' }}</span></div>
        <div class="role-grid">
          <div class="role-stat">
            <span class="role-label mono">Jobs</span>
            <span class="role-val">{{ srv.jenkins.jobCount || 0 }}</span>
          </div>
          <div class="role-stat">
            <span class="role-label mono">Failing</span>
            <span class="role-val" :class="srv.jenkins.failingCount > 0 ? 'red' : ''">{{ srv.jenkins.failingCount || 0 }}</span>
          </div>
          <div class="role-stat">
            <span class="role-label mono">Building</span>
            <span class="role-val" :class="srv.jenkins.buildingCount > 0 ? 'amber' : ''">{{ srv.jenkins.buildingCount || 0 }}</span>
          </div>
          <div class="role-stat">
            <span class="role-label mono">Queue</span>
            <span class="role-val">{{ srv.jenkins.queueSize || 0 }}</span>
          </div>
        </div>
      </div>

      <!-- Postgres panel -->
      <div v-if="srv.postgres" class="role-panel">
        <div class="role-header">
          ◆ POSTGRES
          <span v-if="srv.patroni?.state" class="patroni-chip" :class="srv.patroni.role">
            {{ srv.patroni.role.toUpperCase() }}
          </span>
          <span v-if="srv.postgres.running" class="pg-running green">● LIVE</span>
        </div>

        <!-- Patroni is the source of truth for PG health -->
        <div v-if="srv.patroni?.state" class="patroni-primary">
          <div class="role-grid">
            <div class="role-stat">
              <span class="role-label mono">Cluster</span>
              <span class="role-val green">{{ srv.patroni.state }}</span>
            </div>
            <div class="role-stat">
              <span class="role-label mono">Timeline</span>
              <span class="role-val">{{ srv.patroni.timeline }}</span>
            </div>
            <div class="role-stat">
              <span class="role-label mono">PG Version</span>
              <span class="role-val mono dim">{{ fmtVersion(srv.patroni.server_version) }}</span>
            </div>
            <div class="role-stat">
              <span class="role-label mono">Restart Pending</span>
              <span class="role-val" :class="srv.patroni.pending_restart ? 'amber' : ''">{{ srv.patroni.pending_restart ? 'YES' : 'no' }}</span>
            </div>
          </div>

          <!-- Patroni members -->
          <div v-if="srv.patroni.members?.length" class="role-subpanel">
            <div class="role-subheader mono">CLUSTER MEMBERS</div>
            <div v-for="m in srv.patroni.members" :key="m.name" class="patroni-row">
              <span class="mono" :class="m.role === 'leader' || m.role === 'master' ? 'green' : ''">{{ m.name }}</span>
              <span class="mono dim">{{ m.role }}</span>
              <span class="mono dim">{{ m.state }}</span>
              <span class="mono dim">{{ m.host }}</span>
              <span v-if="m.lag_mb" class="mono amber">{{ m.lag_mb }}MB lag</span>
            </div>
          </div>
        </div>

        <!-- Direct PG stats (only if accessible) -->
        <div v-if="srv.postgres.running" class="role-subpanel">
          <div class="role-subheader mono">DIRECT PG STATS</div>
          <div class="role-grid">
            <div class="role-stat">
              <span class="role-label mono">Databases</span>
              <span class="role-val">{{ srv.postgres.db_count || 0 }}</span>
            </div>
            <div class="role-stat">
              <span class="role-label mono">Connections</span>
              <span class="role-val">{{ srv.postgres.total_connections || 0 }}</span>
            </div>
            <div class="role-stat">
              <span class="role-label mono">Cache Hit</span>
              <span class="role-val">{{ srv.postgres.cache_hit_pct || 0 }}%</span>
            </div>
          </div>
        </div>
      </div>

      <!-- Etcd panel -->
      <div v-if="srv.etcd?.endpoints?.length" class="role-panel">
        <div class="role-header">
          ◆ ETCD
          <span class="mono dim etcd-node-count">{{ srv.etcd.endpoints.length }} nodes</span>
          <span v-if="srv.etcd.healthy" class="green etcd-health">● HEALTHY</span>
          <span v-else class="red etcd-health">● UNHEALTHY</span>
        </div>
        <div class="role-grid">
          <div class="role-stat">
            <span class="role-label mono">DB Size</span>
            <span class="role-val">{{ srv.etcd.total_db_mb }} MB</span>
          </div>
          <div class="role-stat">
            <span class="role-label mono">Raft Term</span>
            <span class="role-val">{{ srv.etcd.endpoints[0]?.raft_term }}</span>
          </div>
          <div class="role-stat">
            <span class="role-label mono">Leader</span>
            <span class="role-val">{{ srv.etcd.leader_count }} / {{ srv.etcd.endpoints.length }}</span>
          </div>
        </div>
        <div v-for="ep in srv.etcd.endpoints" :key="ep.endpoint" class="etcd-row">
          <span class="mono dim">{{ ep.endpoint }}</span>
          <span class="mono dim" :class="ep.is_leader ? 'green' : ''">{{ ep.is_leader ? 'LEADER' : 'follower' }}</span>
          <span class="mono dim">v{{ ep.version }}</span>
          <span class="mono dim">{{ ep.db_size_mb }}MB</span>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { useWorkServersStore } from '../stores/workServers.js'
import { useSSE } from '../composables/useSSE.js'
import HealthBar from '../components/HealthBar.vue'

const ws = useWorkServersStore()
const { connect } = useSSE()
const servers = computed(() => ws.servers)

// Tier 1 summary aggregates
const healthyCount = computed(() => servers.value.filter(s => {
  const h = s.health || {}
  const cpu = h.cpu_pct ?? 0; const mem = h.memory?.pct ?? 0
  return cpu !== undefined && cpu <= 70 && mem <= 75
}).length)

const warningCount = computed(() => servers.value.filter(s => {
  const h = s.health || {}
  const cpu = h.cpu_pct ?? 0; const mem = h.memory?.pct ?? 0
  return (cpu > 70 && cpu <= 90) || (mem > 75 && mem <= 90)
}).length)

const criticalCount = computed(() => servers.value.filter(s => {
  const h = s.health || {}
  const cpu = h.cpu_pct ?? 0; const mem = h.memory?.pct ?? 0
  return cpu > 90 || mem > 90
}).length)

const totalRunningContainers = computed(() => {
  let n = 0
  for (const s of servers.value) {
    if (s.docker) n += s.docker.running_count || 0
  }
  return n
})

const totalContainers = computed(() => {
  let n = 0
  for (const s of servers.value) {
    if (s.docker) n += s.docker.total_containers || 0
  }
  return n
})

// Reactive "time ago" that ticks every 30s
const now = ref(Date.now())
let tickTimer = null

onMounted(() => {
  connect(['work-system', 'work-docker', 'work-nexus', 'work-jenkins', 'work-postgres'])
  tickTimer = setInterval(() => { now.value = Date.now() }, 30000)
})

onUnmounted(() => {
  if (tickTimer) clearInterval(tickTimer)
})

const lastUpdate = computed(() => {
  const ts = ws.lastCollected.system
  if (!ts) return '--'
  const diff = (now.value / 1000) - ts
  if (diff < 60) return Math.floor(diff) + 's ago'
  if (diff < 3600) return Math.floor(diff / 60) + 'm ago'
  if (diff < 86400) return Math.floor(diff / 3600) + 'h ago'
  return Math.floor(diff / 86400) + 'd ago'
})

function healthClass(h) {
  if (!h || h.cpu_pct === undefined) return ''
  if (h.cpu_pct > 90 || (h.memory?.pct || 0) > 95) return 'red'
  if (h.cpu_pct > 70 || (h.memory?.pct || 0) > 85) return 'amber'
  return 'green'
}

function memColor(pct) {
  if (!pct && pct !== 0) return 'var(--cyan)'
  if (pct > 90) return 'var(--red)'
  if (pct > 75) return 'var(--amber)'
  return 'var(--green)'
}

function diskColor(pct) {
  if (!pct && pct !== 0) return 'var(--cyan)'
  if (pct > 90) return 'var(--red)'
  if (pct > 80) return 'var(--amber)'
  return 'var(--green)'
}

function fmtUptime(h) {
  if (!h && h !== 0) return '--'
  if (h >= 720) return Math.floor(h / 720) + 'mo'
  if (h >= 168) return Math.floor(h / 168) + 'w'
  if (h >= 24) return Math.floor(h / 24) + 'd'
  return Math.floor(h) + 'h'
}

function fmtVersion(v) {
  if (!v) return '--'
  const s = String(v)
  if (s.length >= 6) return s.slice(0,2) + '.' + s.slice(2,4) + '.' + s.slice(4)
  return s
}
</script>

<style scoped>
.work-servers-page { position: relative; z-index: 5; }
.last-updated { font-size: 10px; color: var(--text-faint); margin-top: 8px; }
.empty-state { padding: 40px; text-align: center; }

/* Summary strip (Tier 1) */
.summary-strip {
  display: flex;
  padding: 18px;
  margin-bottom: 28px;
  gap: 0;
}
.summary-cell {
  flex: 1;
  text-align: center;
  padding: 8px 12px;
}
.summary-label {
  font-size: 10px; color: var(--text-faint);
  text-transform: uppercase; letter-spacing: 0.1em;
  margin-bottom: 4px;
}
.summary-val {
  font-family: var(--font-display);
  font-size: 22px; font-weight: 700; color: var(--text-hi);
}

/* Server card */
.server-card {
  padding: 18px;
  margin-bottom: 20px;
}
.card-header {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 14px;
}
.status-dot {
  width: 8px; height: 8px; border-radius: 50%; flex-shrink: 0;
  background: var(--text-faint);
}
.status-dot.green { background: var(--green); box-shadow: 0 0 6px var(--green); }
.status-dot.amber { background: var(--amber); box-shadow: 0 0 6px var(--amber); }
.status-dot.red   { background: var(--red);   box-shadow: 0 0 6px var(--red); }
.server-name {
  font-family: var(--font-display);
  font-size: 16px; font-weight: 600; color: var(--text-hi);
  text-transform: uppercase; letter-spacing: 0.06em;
}
.server-group { margin-left: auto; }

/* Health grid */
.health-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 12px;
  margin-bottom: 8px;
}
.health-meta {
  grid-column: 1 / -1;
  display: flex; gap: 18px;
  font-size: 10px; color: var(--text-dim);
}

/* Role panel */
.role-panel {
  margin-top: 14px;
  padding-top: 14px;
  border-top: 1px solid var(--line);
}
.role-header {
  font-family: var(--font-mono);
  font-size: 10px; letter-spacing: 0.15em; color: var(--cyan);
  text-transform: uppercase; margin-bottom: 10px;
  display: flex; align-items: center; gap: 8px;
}
.jenkins-type { font-size: 10px; }
.patroni-chip {
  font-size: 10px;
  padding: 1px 6px;
  font-family: var(--font-mono);
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.08em;
}
.patroni-chip.master, .patroni-chip.leader { color: var(--green); background: rgba(74,222,128,0.12); }
.patroni-chip.replica, .patroni-chip.standby { color: var(--cyan); background: rgba(30,200,255,0.12); }
.pg-running { font-size: 10px; font-family: var(--font-mono); }
.role-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(120px, 1fr));
  gap: 8px;
}
.role-stat {
  background: var(--bg-deep);
  padding: 8px 10px;
  display: flex; flex-direction: column; gap: 2px;
}
.role-label { font-size: 10px; color: var(--text-faint); text-transform: uppercase; letter-spacing: 0.08em; }
.role-val { font-family: var(--font-display); font-size: 15px; font-weight: 600; color: var(--text-hi); }

/* Sub-panels */
.role-subpanel { margin-top: 10px; }
.role-subheader {
  font-size: 10px; color: var(--text-dim); letter-spacing: 0.1em;
  text-transform: uppercase; margin-bottom: 6px;
}

/* Swarm services */
.swarm-services { margin-top: 8px; }
.swarm-svc-row {
  display: flex; justify-content: space-between; align-items: center;
  padding: 3px 0; font-size: 10px;
}
.svc-name { color: var(--text-dim); }
.svc-replicas { color: var(--text-faint); }

/* Patroni / Etcd rows */
.patroni-members, .blob-list { margin-top: 4px; }
.patroni-row, .blob-row, .etcd-row {
  display: flex; gap: 12px; align-items: center;
  padding: 3px 0; font-size: 10px;
}

/* Utility */
.mono { font-family: var(--font-mono); }
.dim { color: var(--text-faint); }
.green { color: var(--green); }
.amber { color: var(--amber); }
.red { color: var(--red); }

/* Role header badges */
.etcd-node-count { font-size: 10px; }
.etcd-health { font-size: 10px; }
.stopped-status { font-size: 10px; }

/* Format chips */
.format-chips {
  display: flex; flex-wrap: wrap; gap: 4px;
}
.format-chips .chip {
  font-family: var(--font-mono); font-size: 10px;
  padding: 2px 6px;
  background: var(--bg-elevated);
  color: var(--text-dim);
  letter-spacing: 0.06em;
}

@media (max-width: 720px) {
  .health-grid { grid-template-columns: repeat(2, 1fr); }
  .role-grid { grid-template-columns: 1fr 1fr; }
}
</style>
