import { ref, onMounted } from 'vue'
import { useSnapshotStore } from '../stores/snapshotStore.js'
import { useWorkServersStore } from '../stores/workServers.js'

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
  'servers':          { key: 'servers',          interval: 60000 },
  // Work servers
  'work-system':      { key: 'work-system',      interval: 900000 },
  'work-docker':      { key: 'work-docker',      interval: 1800000 },
  'work-nexus':       { key: 'work-nexus',       interval: 1800000 },
  'work-jenkins':     { key: 'work-jenkins',     interval: 1800000 },
  'work-postgres':    { key: 'work-postgres',    interval: 1800000 },
}

// ── Module-level singleton state ────────────────────────────────────────
let source = null
let pollTimers = {}
let currentChannels = null  // array or null (all)
let intentionalClose = false

/**
 * Per-channel SSE with page-aware subscription.
 *
 * Call connect(channels) with an array of channel names (or null for all).
 * When channels change, the SSE connection reconnects with the new filter.
 * Polling fallback also respects the channel list.
 */
export function useSSE() {
  const store = useSnapshotStore()

  function _stopAllPolling() {
    for (const id of Object.values(pollTimers)) clearInterval(id)
    pollTimers = {}
  }

  function _disconnectSSE() {
    intentionalClose = true
    if (source) {
      source.close()
      source = null
    }
  }

  function _applyChannel(channelName, rawData) {
    // Work server channels go to their own store
    if (channelName.startsWith('work-')) {
      const wsStore = useWorkServersStore()
      wsStore.patch(channelName, rawData)
      return
    }

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
    const names = currentChannels || Object.keys(CHANNELS)
    for (const name of names) {
      if (pollTimers[name]) continue
      const cfg = CHANNELS[name]
      if (!cfg) continue
      const url = window.location.origin + '/api/' + name
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

  function connect(channels) {
    // Update the module-level channel list
    currentChannels = channels || null

    // Disconnect existing SSE (flag prevents onerror fallout)
    _disconnectSSE()
    intentionalClose = false

    // Stop polling
    _stopAllPolling()

    // If explicit empty array, page needs no live data — go dark
    if (Array.isArray(currentChannels) && currentChannels.length === 0) {
      uplink.value = 'disconnected'
      return
    }

    uplink.value = 'connecting'

    // Start polling immediately — data first, SSE optional
    _startPolling()

    // Build SSE URL with channel filter
    let sseUrl = '/events'
    if (currentChannels && currentChannels.length > 0) {
      sseUrl += '?channels=' + encodeURIComponent(currentChannels.join(','))
    }

    // Try SSE in parallel
    source = new EventSource(sseUrl)
    source.onopen = () => {
      sseActive.value = true
      uplink.value = 'synced'
      _stopAllPolling()
    }

    const subscribed = currentChannels || Object.keys(CHANNELS)
    for (const eventType of subscribed) {
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
      // Ignore errors from intentional close (page navigation / reconnect)
      if (intentionalClose) {
        intentionalClose = false
        return
      }

      sseActive.value = false
      // Transition to degraded from any state: synced (dropped) or connecting (failed to establish)
      uplink.value = 'degraded'
      _disconnectSSE()
      intentionalClose = false
      _startPolling()  // restart polling if it was stopped
    }
  }

  return { uplink, sseActive, connect }
}
