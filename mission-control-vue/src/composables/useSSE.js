import { ref } from 'vue'
import { useSnapshotStore } from '../stores/snapshotStore.js'

// ── Module-level singletons ──
let source = null
let channelPollTimers = {}

const uplink = ref('disconnected')
const sseActive = ref(false)

// ── Channel event type → store key mapping ──
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
 * useSSE composable — must be called during component setup (Pinia must be active).
 */
export function useSSE() {
  // ── Eagerly create the store while Pinia is active ──
  const store = useSnapshotStore()

  // ── Stop all polling ──
  function _stopAllPolling() {
    for (const id of Object.values(channelPollTimers)) {
      clearInterval(id)
    }
    channelPollTimers = {}
  }

  // ── Apply channel data to the store ──
  function _applyChannel(channelName, rawData) {
    const config = CHANNELS[channelName]
    if (!config) {
      console.warn('useSSE: unknown channel', channelName)
      return
    }

    // hermes-health and prod-health merge into 'vps' key
    if (channelName === 'hermes-health') {
      const currentVps = store.data?.vps || {}
      store.patch('vps', { ...currentVps, hermes: rawData.health || rawData })
    } else if (channelName === 'prod-health') {
      const currentVps = store.data?.vps || {}
      store.patch('vps', { ...currentVps, prod: rawData.health || rawData })
    } else {
      store.patch(config.key, rawData)
    }
  }

  // ── Per-channel polling fallback ──
  function startChannelPolling(channelName) {
    const config = CHANNELS[channelName]
    if (!config || channelPollTimers[channelName]) return

    const url = window.location.origin + '/api/' + channelName
    channelPollTimers[channelName] = setInterval(async () => {
      try {
        const r = await fetch(url)
        if (!r.ok) throw new Error('HTTP ' + r.status)
        const data = await r.json()
        _applyChannel(channelName, data)
      } catch (err) {
        console.warn('Poll ' + channelName + ' failed:', err)
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
    for (const eventType of Object.keys(CHANNELS)) {
      source.addEventListener(eventType, (event) => {
        try {
          const data = JSON.parse(event.data)
          console.log('[MC] SSE ' + eventType + ' received, keys:', Object.keys(data).join(','))
          _applyChannel(eventType, data)
        } catch (err) {
          console.warn('SSE ' + eventType + ' parse error:', err)
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
