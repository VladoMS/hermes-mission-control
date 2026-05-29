import { defineStore } from 'pinia'
import { ref, computed } from 'vue'

export const useServersStore = defineStore('servers', () => {
  const servers = ref([])
  const dokkuData = ref(null)
  const cronData = ref({ crons: {}, errors: [] })

  const serverCount = computed(() => servers.value.length)

  function getServer(name) {
    return servers.value.find(s => s.name === name) || null
  }

  function getHealth(name) {
    return getServer(name)?.health || {}
  }

  function getCrons(name) {
    const byServer = cronData.value?.crons || {}
    return byServer[name] || []
  }

  function getDokku(name) {
    return getServer(name)?.dokku || null
  }

  const dokkuServers = computed(() =>
    servers.value.filter(s => s.has_dokku && s.dokku)
  )

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

  function patchServers(newData) {
    servers.value = newData
  }

  function patchDokku(newData) {
    dokkuData.value = newData
  }

  function patchCrons(newData) {
    cronData.value = newData
  }

  async function fetchServers() {
    try {
      const r = await fetch('/api/v2/servers')
      if (r.ok) servers.value = await r.json()
    } catch (e) {
      console.warn('fetch /api/v2/servers failed:', e)
    }
  }

  async function fetchDokku() {
    try {
      const r = await fetch('/api/v2/dokku')
      if (r.ok) dokkuData.value = await r.json()
    } catch (e) {
      console.warn('fetch /api/v2/dokku failed:', e)
    }
  }

  async function fetchCrons() {
    try {
      const r = await fetch('/api/v2/server-crons')
      if (r.ok) cronData.value = await r.json()
    } catch (e) {
      console.warn('fetch /api/v2/server-crons failed:', e)
    }
  }

  return {
    servers, serverCount, dokkuData, cronData,
    getServer, getHealth, getCrons, getDokku,
    dokkuServers, allDokkuApps,
    patchServers, patchDokku, patchCrons,
    fetchServers, fetchDokku, fetchCrons,
  }
})
