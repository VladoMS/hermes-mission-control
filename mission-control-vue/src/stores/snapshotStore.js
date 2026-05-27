import { defineStore } from 'pinia'
import { ref } from 'vue'

/**
 * Snapshot store — holds the latest assembled snapshot from the backend.
 * Hydrated by useSSE composable via SSE 'snapshot' events or polling fallback.
 *
 * Fingerprint comparison skips unnecessary reactive updates when the
 * backend sends an identical snapshot (common during quiet periods).
 */
export const useSnapshotStore = defineStore('snapshot', () => {
  const data = ref(null)
  const connected = ref(false)
  const lastUpdated = ref(null)

  /**
   * Hydrate with new snapshot data.
   * Returns true if data changed (fingerprint mismatch), false if identical.
   */
  function hydrate(snap) {
    const fp = JSON.stringify(snap)
    if (data.value && JSON.stringify(data.value) === fp) {
      return false
    }
    data.value = snap
    lastUpdated.value = snap.timestamp || Date.now() / 1000
    connected.value = true
    return true
  }

  /** Mark connection as lost (SSE error). Data is preserved. */
  function setDisconnected() {
    connected.value = false
  }

  return { data, connected, lastUpdated, hydrate, setDisconnected }
})
