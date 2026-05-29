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

    <div v-if="servers.length === 0" class="empty-state panel">
      <div class="placeholder-panel">Collecting data... first poll at 15-minute intervals.</div>
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
            <span class="role-label mono">Containers</span>
            <span class="role-val">{{ srv.docker.container_count || 0 }} / {{ srv.docker.total_containers || 0 }}</span>
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
        <div v-if="srv.nexus.blobstores?.length" class="blob-list">
          <div v-for="blob in srv.nexus.blobstores" :key="blob.name" class="blob-row">
            <span class="mono">{{ blob.name }}</span>
            <span class="mono dim">{{ blob.blobCount || 0 }} blobs</span>
            <span class="mono dim">{{ fmtBytes(blob.totalSizeInBytes) }}</span>
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
        <div class="role-header">◆ POSTGRES</div>
        <div class="role-grid">
          <div class="role-stat">
            <span class="role-label mono">PG Running</span>
            <span class="role-val" :class="srv.postgres.running ? 'green' : 'dim'">{{ srv.postgres.running ? 'YES' : 'NO' }}</span>
          </div>
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

        <!-- Patroni -->
        <div v-if="srv.patroni && srv.patroni.state" class="role-subpanel">
          <div class="role-subheader mono">PATRONI — {{ srv.patroni.role }} / {{ srv.patroni.state }}</div>
          <div v-if="srv.patroni.members?.length" class="patroni-members">
            <div v-for="m in srv.patroni.members" :key="m.name" class="patroni-row">
              <span class="mono" :class="m.role === 'leader' ? 'green' : ''">{{ m.name }}</span>
              <span class="mono dim">{{ m.role }}</span>
              <span class="mono dim">{{ m.state }}</span>
              <span v-if="m.lag_mb" class="mono amber">{{ m.lag_mb }}MB lag</span>
            </div>
          </div>
        </div>

        <!-- Etcd -->
        <div v-if="srv.etcd && srv.etcd.endpoints?.length" class="role-subpanel">
          <div class="role-subheader mono">ETCD</div>
          <div v-for="ep in srv.etcd.endpoints" :key="ep.endpoint" class="etcd-row">
            <span class="mono">{{ ep.endpoint }}</span>
            <span class="mono dim">v{{ ep.version }}</span>
            <span class="mono dim">{{ ep.db_size_mb }}MB</span>
            <span class="mono dim">term {{ ep.raft_term }}</span>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, onMounted } from 'vue'
import { useWorkServersStore } from '../stores/workServers.js'
import { useSSE } from '../composables/useSSE.js'
import HealthBar from '../components/HealthBar.vue'

const ws = useWorkServersStore()
const { connect } = useSSE()
const servers = computed(() => ws.servers)

onMounted(() => {
  connect(['work-system', 'work-docker', 'work-nexus', 'work-jenkins', 'work-postgres'])
})

const lastUpdate = computed(() => {
  const ts = ws.lastCollected.system
  return ws.ago(ts)
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

function fmtBytes(b) {
  if (!b) return '--'
  if (b >= 1e12) return (b / 1e12).toFixed(1) + 'TB'
  if (b >= 1e9) return (b / 1e9).toFixed(1) + 'GB'
  if (b >= 1e6) return (b / 1e6).toFixed(1) + 'MB'
  return (b / 1e3).toFixed(0) + 'KB'
}
</script>

<style scoped>
.work-servers-page { position: relative; z-index: 5; }
.last-updated { font-size: 10px; color: var(--text-faint); margin-top: 8px; }
.empty-state { padding: 40px; text-align: center; }

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
.jenkins-type { font-size: 9px; }
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
.role-label { font-size: 9px; color: var(--text-faint); text-transform: uppercase; letter-spacing: 0.08em; }
.role-val { font-family: var(--font-display); font-size: 15px; font-weight: 600; color: var(--text-hi); }

/* Sub-panels */
.role-subpanel { margin-top: 10px; }
.role-subheader {
  font-size: 9px; color: var(--text-dim); letter-spacing: 0.1em;
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

@media (max-width: 720px) {
  .health-grid { grid-template-columns: repeat(2, 1fr); }
  .role-grid { grid-template-columns: 1fr 1fr; }
}
</style>
