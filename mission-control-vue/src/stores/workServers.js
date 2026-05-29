import { defineStore } from 'pinia'
import { ref, computed } from 'vue'

export const useWorkServersStore = defineStore('workServers', () => {
  // Per-channel data
  const system = ref({ servers: [] })
  const docker = ref({ servers: [] })
  const nexus = ref({ servers: [] })
  const jenkins = ref({ servers: [] })
  const postgres = ref({ servers: [] })

  // Last collected timestamps
  const lastCollected = ref({
    system: null,
    docker: null,
    nexus: null,
    jenkins: null,
    postgres: null,
  })

  function patch(channel, data) {
    switch (channel) {
      case 'work-system':
        system.value = data
        lastCollected.value.system = data.collected_at || Date.now() / 1000
        break
      case 'work-docker':
        docker.value = data
        lastCollected.value.docker = data.collected_at || Date.now() / 1000
        break
      case 'work-nexus':
        nexus.value = data
        lastCollected.value.nexus = data.collected_at || Date.now() / 1000
        break
      case 'work-jenkins':
        jenkins.value = data
        lastCollected.value.jenkins = data.collected_at || Date.now() / 1000
        break
      case 'work-postgres':
        postgres.value = data
        lastCollected.value.postgres = data.collected_at || Date.now() / 1000
        break
    }
  }

  // Merged server list — system health as base, enriched with role data
  const servers = computed(() => {
    const map = new Map()

    for (const s of system.value.servers || []) {
      const key = s.hostname || s.server_name
      map.set(key, {
        key,
        serverName: s.server_name,
        hostname: s.hostname,
        ansibleGroup: s.ansible_group,
        health: s.health || {},
        docker: null,
        nexus: null,
        jenkins: null,
        postgres: null,
        patroni: null,
        etcd: null,
      })
    }

    // Enrich with docker data
    for (const d of docker.value.servers || []) {
      const entry = map.get(d.hostname)
      if (entry) entry.docker = d.docker
    }

    // Enrich with nexus data
    for (const n of nexus.value.servers || []) {
      const entry = map.get(n.hostname)
      if (entry) entry.nexus = n.nexus
    }

    // Enrich with jenkins data
    for (const j of jenkins.value.servers || []) {
      const entry = map.get(j.hostname)
      if (entry) entry.jenkins = j.jenkins
    }

    // Enrich with postgres data
    for (const p of postgres.value.servers || []) {
      const entry = map.get(p.hostname)
      if (entry) {
        entry.postgres = p.postgres
        entry.patroni = p.patroni
        entry.etcd = p.etcd
      }
    }

    return Array.from(map.values())
  })

  function ago(ts) {
    if (!ts) return '--'
    const diff = (Date.now() / 1000) - ts
    if (diff < 60) return Math.floor(diff) + 's ago'
    if (diff < 3600) return Math.floor(diff / 60) + 'm ago'
    if (diff < 86400) return Math.floor(diff / 3600) + 'h ago'
    return Math.floor(diff / 86400) + 'd ago'
  }

  return { system, docker, nexus, jenkins, postgres, lastCollected, servers, patch, ago }
})
