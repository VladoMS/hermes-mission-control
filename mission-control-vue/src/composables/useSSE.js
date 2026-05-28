import { ref } from 'vue'
import { useSnapshotStore } from '../stores/snapshotStore.js'

// ── Module-level singletons ──
let source = null
let channelPollTimers = {}  // { channelName: intervalId }

const uplink = ref('disconnected') // 'synced' | 'degraded' | 'offline' | 'connecting'
const sseActive = ref(false)

// ── Channel event type → store key mapping ──
// SSE event name → snapshotStore.data key (and REST endpoint path)
const CHANNELS = {
  'gateway':          { key: 'gateway',          tier: 1, interval: 5000 },
  'processes':        { key: 'processes',        tier: 1, interval: 5000 },
  'hermes-health':    { key: 'vps',              tier: 1, interval: 5000 },
  'sessions-ledger':  { key: 'sessions_ledger',  tier: 1, interval: 15000 },
  'profiles':         { key: 'profiles',         tier: 2, interval: 60000 },
  'sessions':         { key: 'sessions',         tier: 2, interval: 30000 },
  'kanban':           { key: 'kanban',           tier: 2, interval: 30000 },
  'prod-health':      { key: 'vps',              tier: 3, interval: 30000 },
  'dokku':            { key: 'dokku',            tier: 3, interval: 60000 },
  'server-crons':     { key: 'server_crons',     tier: 3, interval: 300000 },
}

/**
 * useSSE composable — manages EventSource connection to /events
 * with per-channel SSE listeners and per-channel polling fallback.
 * Called once in App.vue on mount.
 */
export function useSSE() {
  let store = null

  function _getStore() {
    if (!store) store = useSnapshotStore()
    return store
  }

  // ── Stop all polling ──
  function _stopAllPolling() {
    for (const id of Object.values(channelPollTimers)) {
      clearInterval(id)
    }
    channelPollTimers = {}
  }

  // ── Apply channel data to the store ──
  function _applyChannel(channelName, data) {
    const config = CHANNELS[channelName]
    if (!config) return

    // hermes-health and prod-health merge into 'vps' key
    if (channelName === 'hermes-health') {
      const st = _getStore()
      const currentVps = st.data?.vps || {}
      st.patch('vps', { ...currentVps, hermes: data.health || data })
    } else if (channelName === 'prod-health') {
      const st = _getStore()
      const currentVps = st.data?.vps || {}
      st.patch('vps', { ...currentVps, prod: data.health || data })
    } else {
      _getStore().patch(config.key, data)
    }
  }

  // ── Per-channel polling fallback ──
  function startChannelPolling(channelName) {
    const config = CHANNELS[channelName]
    if (!config || channelPollTimers[channelName]) return

    channelPollTimers[channelName] = setInterval(async () => {
      try {
        const r = await fetch(`/api/${channelName}`)
        if (!r.ok) throw new Error(`HTTP ${r.status}`)
        const data = await r.json()
        _applyChannel(channelName, data)
      } catch (err) {
        console.warn(`Poll ${channelName} failed:`, err)
      }
    }, config.interval)
  }

  // ── SSE connection ──
  function connect() {
    if (source) return

    uplink.value = 'connecting'
    source = new EventSource('/events')

    source.onopen = () => {
      sseActive.value = true
      uplink.value = 'synced'
      _stopAllPolling()
    }

    // ── Register per-channel event listeners ──
    for (const [eventType, config] of Object.entries(CHANNELS)) {
      source.addEventListener(eventType, (event) => {
        try {
          const data = JSON.parse(event.data)
          _applyChannel(eventType, data)
        } catch (err) {
          console.warn(`SSE ${eventType} parse error:`, err)
        }
      })
    }

    // ── Heartbeat ──
    source.addEventListener('heartbeat', () => {})

    source.onerror = () => {
      sseActive.value = false
      uplink.value = 'degraded'
      source.close()
      source = null
      // Start per-channel polling for all channels
      for (const name of Object.keys(CHANNELS)) {
        startChannelPolling(name)
      }
    }
  }

  return { uplink, sseActive, connect }
}
