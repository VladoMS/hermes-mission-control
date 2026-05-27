import { defineStore } from 'pinia'
import { computed } from 'vue'
import { useSnapshotStore } from './snapshotStore.js'

/**
 * Servers store — server list, per-server health, crons, and Dokku data.
 * Derives from snapshot.data.servers.
 *
 * Each server entry shape:
 *   { name, display, host, type, notes, has_dokku, cron_label,
 *     health: { cpu_pct, mem: {...}, disk: {...}, ssh_ok },
 *     crons: [{ name, command, schedule_display, schedule_desc, ... }],
 *     dokku: { apps: [...], containers: [{ id, image, status, name }], errors: [...] } | null }
 */
export const useServersStore = defineStore('servers', () => {
  const snap = useSnapshotStore()

  /** Server list from snapshot */
  const servers = computed(() => snap.data?.servers || [])

  /** Total server count */
  const serverCount = computed(() => servers.value.length)

  /** Look up a server by name */
  function getServer(name) {
    return servers.value.find(s => s.name === name) || null
  }

  /** Get health data for a server */
  function getHealth(name) {
    return getServer(name)?.health || {}
  }

  /** Get cron jobs for a server */
  function getCrons(name) {
    return getServer(name)?.crons || []
  }

  /** Get Dokku data for a server (apps + containers) */
  function getDokku(name) {
    return getServer(name)?.dokku || null
  }

  /** All servers that have Dokku enabled */
  const dokkuServers = computed(() =>
    servers.value.filter(s => s.has_dokku && s.dokku)
  )

  /** Flat list of all Dokku apps across all servers */
  const allDokkuApps = computed(() => {
    const apps = []
    for (const s of servers.value) {
      if (s.has_dokku && s.dokku?.apps) {
        for (const app of s.dokku.apps) {
          apps.push({ server: s.name, app })
        }
      }
    }
    return apps
  })

  return {
    servers,
    serverCount,
    getServer,
    getHealth,
    getCrons,
    getDokku,
    dokkuServers,
    allDokkuApps,
  }
})
