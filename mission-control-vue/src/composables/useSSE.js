import { ref } from 'vue'
import { useGatewayStore } from '../stores/gateway.js'
import { useVpsStore } from '../stores/vps.js'
import { useProfilesStore } from '../stores/profiles.js'
import { useSessionsStore } from '../stores/sessions.js'
import { useKanbanStore } from '../stores/kanban.js'
import { useServersStore } from '../stores/servers.js'
import { useOpenRouterStore } from '../stores/openrouter.js'
import { useWorkServersStore } from '../stores/workServers.js'

const uplink = ref('disconnected')
const sseActive = ref(false)

const CHANNELS = {
  'gateway':          { interval: 5000 },
  'hermes-health':    { interval: 5000 },
  'sessions-ledger':  { interval: 15000 },
  'profiles':         { interval: 60000 },
  'sessions':         { interval: 30000 },
  'kanban':           { interval: 30000 },
  'prod-health':      { interval: 30000 },
  'dokku':            { interval: 60000 },
  'server-crons':     { interval: 300000 },
  'servers':          { interval: 60000 },
  'openrouter-usage': { interval: 60000 },
  'daily-costs':      { interval: 120000 },
  'work-system':      { interval: 900000 },
  'work-docker':      { interval: 1800000 },
  'work-nexus':       { interval: 1800000 },
  'work-jenkins':     { interval: 1800000 },
  'work-postgres':    { interval: 1800000 },
}

let source = null
let pollTimers = {}
let currentChannels = null
let intentionalClose = false

export function useSSE() {
  const gw = useGatewayStore()
  const vps = useVpsStore()
  const prof = useProfilesStore()
  const sess = useSessionsStore()
  const kan = useKanbanStore()
  const srv = useServersStore()
  const or = useOpenRouterStore()
  const ws = useWorkServersStore()

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
    switch (channelName) {
      case 'gateway':        gw.patch(rawData); break
      case 'processes':      break  // consumed via v2 API
      case 'hermes-health':  vps.patchHermes(rawData); break
      case 'prod-health':    vps.patchProd(rawData); break
      case 'profiles':       prof.patch(rawData); break
      case 'sessions':       sess.patchSessions(rawData); break
      case 'sessions-ledger': sess.patchLedger(rawData); break
      case 'daily-costs':    sess.patchDailyCosts(rawData); break
      case 'kanban':         kan.patch(rawData); break
      case 'servers':        srv.patchServers(rawData); break
      case 'dokku':          srv.patchDokku(rawData); break
      case 'server-crons':   srv.patchCrons(rawData); break
      case 'openrouter-usage': or.patch(rawData); break
      default:
        if (channelName.startsWith('work-')) ws.patch(channelName, rawData)
    }
  }

  function _startPolling() {
    const names = currentChannels || Object.keys(CHANNELS)
    for (const name of names) {
      if (pollTimers[name]) continue
      const cfg = CHANNELS[name]
      if (!cfg) continue
      const url = window.location.origin + '/api/v2/' + name
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
    currentChannels = channels || null
    _disconnectSSE()
    intentionalClose = false
    _stopAllPolling()

    if (Array.isArray(currentChannels) && currentChannels.length === 0) {
      uplink.value = 'disconnected'
      return
    }

    uplink.value = 'connecting'
    _startPolling()

    let sseUrl = '/events'
    if (currentChannels && currentChannels.length > 0) {
      sseUrl += '?channels=' + encodeURIComponent(currentChannels.join(','))
    }

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
      if (intentionalClose) {
        intentionalClose = false
        return
      }
      sseActive.value = false
      uplink.value = 'degraded'
      _disconnectSSE()
      intentionalClose = false
      _startPolling()
    }
  }

  return { uplink, sseActive, connect }
}
