import { ref, onMounted } from 'vue'
import { useSnapshotStore } from '../stores/snapshotStore.js'

const uplink = ref('disconnected')
const sseActive = ref(false)

const CHANNELS = {
  'gateway':          { key: 'gateway',          interval: 5000 },
  'processes':        { key: 'processes',        interval: 5000 },
  'hermes-health':    { key: 'vps',              interval: 5000 },
  'sessions-ledger':  { key: 'sessions_ledger',  interval: 15000 },
  'profiles':         { key: 'profiles',         interval: 60000 },
  'sessions':         { key: 'sessions',         interval: 30000 },
  'kanban':           { key: 'kanban',           interval: 30000 },
  'prod-health':      { key: 'vps',              interval: 30000 },
  'dokku':            { key: 'dokku',            interval: 60000 },
  'server-crons':     { key: 'server_crons',     interval: 300000 },
}

/**
 * Simplified useSSE — starts per-channel polling immediately.
 * SSE connection is attempted in parallel; if it connects, polling stops.
 */
export function useSSE() {
  const store = useSnapshotStore()
  let source = null
  let pollTimers = {}

  function _stopAllPolling() {
    for (const id of Object.values(pollTimers)) clearInterval(id)
    pollTimers = {}
  }

  function _applyChannel(channelName, rawData) {
    const config = CHANNELS[channelName]
    if (!config) return

    if (channelName === 'hermes-health') {
      const cur = store.data?.vps || {}
      store.patch('vps', { ...cur, hermes: rawData.health || rawData })
    } else if (channelName === 'prod-health') {
      const cur = store.data?.vps || {}
      store.patch('vps', { ...cur, prod: rawData.health || rawData })
    } else {
      store.patch(config.key, rawData)
    }
  }

  function _startPolling() {
    for (const [name, cfg] of Object.entries(CHANNELS)) {
      if (pollTimers[name]) continue
      const url = window.location.origin + '/api/' + name
      // Immediate first fetch, then interval
      const fetchOnce = async () => {
        try {
          const r = await fetch(url)
          if (!r.ok) throw new Error('HTTP ' + r.status)
          const data = await r.json()
          _applyChannel(name, data)
        } catch (err) {
          console.warn('Poll ' + name + ' failed:', err)
        }
      }
      fetchOnce()
      pollTimers[name] = setInterval(fetchOnce, cfg.interval)
    }
  }

  function connect() {
    uplink.value = 'connecting'

    // Start polling immediately — data first, SSE optional
    _startPolling()

    // Try SSE in parallel
    source = new EventSource('/events')
    source.onopen = () => {
      sseActive.value = true
      uplink.value = 'synced'
      _stopAllPolling()
    }

    for (const eventType of Object.keys(CHANNELS)) {
      source.addEventListener(eventType, (event) => {
        try {
          const data = JSON.parse(event.data)
          _applyChannel(eventType, data)
        } catch (err) {
          console.warn('SSE ' + eventType + ' parse error:', err)
        }
      })
    }

    source.addEventListener('heartbeat', () => {})

    source.onerror = () => {
      sseActive.value = false
      if (uplink.value === 'synced') uplink.value = 'degraded'
      source.close()
      source = null
      _startPolling()  // restart polling if it was stopped
    }
  }

  return { uplink, sseActive, connect }
}
