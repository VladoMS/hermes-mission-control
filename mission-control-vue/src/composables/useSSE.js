import { ref } from 'vue'
import { useSnapshotStore } from '../stores/snapshotStore.js'

// ── Module-level singletons (one EventSource / one poll timer per app) ──
let source = null
let pollTimer = null

const uplink = ref('disconnected') // 'synced' | 'degraded' | 'offline' | 'disconnected'
const sseActive = ref(false)

/**
 * useSSE composable — manages EventSource connection to /events
 * with polling fallback to /api/snapshot every 8s.
 *
 * Returns reactive uplink state, SSE active flag, connect(), and startPolling().
 * Connect is called once in App.vue on mount; uplink state drives TopBar indicator.
 */
export function useSSE() {
  let store = null

  // ── Resolve store lazily (Pinia must be installed before first call) ──
  function _getStore() {
    if (!store) store = useSnapshotStore()
    return store
  }

  // ── Stop polling (called when SSE recovers) ──
  function _stopPolling() {
    if (pollTimer) {
      clearInterval(pollTimer)
      pollTimer = null
    }
  }

  // ── Polling fallback ──
  function startPolling() {
    if (pollTimer) return // already polling
    uplink.value = 'degraded'

    pollTimer = setInterval(async () => {
      try {
        const r = await fetch('/api/snapshot')
        if (!r.ok) throw new Error(`HTTP ${r.status}`)
        const snap = await r.json()
        _getStore().hydrate(snap)
        uplink.value = 'degraded' // polling is still degraded, but data flows
      } catch (err) {
        console.warn('Poll fetch failed:', err)
        uplink.value = 'offline'
      }
    }, 8000)
  }

  // ── SSE connection ──
  function connect() {
    if (source) return // already connected (or connecting)

    uplink.value = 'connecting'
    source = new EventSource('/events')

    source.onopen = () => {
      sseActive.value = true
      uplink.value = 'synced'
      // Stop polling if it was running
      _stopPolling()
    }

    source.addEventListener('snapshot', (event) => {
      try {
        const snap = JSON.parse(event.data)
        _getStore().hydrate(snap)
      } catch (err) {
        console.warn('SSE snapshot parse error:', err)
      }
    })

    source.addEventListener('heartbeat', () => {
      // Silently acknowledge — keeps connection alive
    })

    source.onerror = () => {
      sseActive.value = false
      uplink.value = 'degraded'
      // Close the broken connection
      source.close()
      source = null
      // Start polling fallback
      startPolling()
    }
  }

  return { uplink, sseActive, connect, startPolling }
}
