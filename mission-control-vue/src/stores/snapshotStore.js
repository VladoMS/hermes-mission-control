import { defineStore } from 'pinia'
import { ref, reactive } from 'vue'

/**
 * Snapshot store — holds the latest data from the backend.
 * Supports two update paths:
 *   1. hydrate(snap) — full snapshot replacement (legacy, polling fallback)
 *   2. patch(key, value) — per-channel update (multiplexed SSE + channel polling)
 *
 * Per-key fingerprint comparison skips unnecessary reactive updates.
 * Domain stores derive from `data` via computed() — unchanged.
 */
export const useSnapshotStore = defineStore('snapshot', () => {
  const data = ref(null)
  const connected = ref(false)
  const lastUpdated = ref(null)

  /** Per-key MD5-like fingerprints — compared on each patch() */
  const _fingerprints = reactive({})

  /** Per-channel loaded flags — true once the first payload for this channel arrives */
  const _loaded = reactive({})

  /**
   * Legacy: full snapshot replacement (fingerprint-gated).
   * Returns true if data changed, false if identical.
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

  /**
   * Per-channel patch (fingerprint-gated per-key).
   * Merges `value` into `data.value[key]`.
   * Skips update if this channel's fingerprint hasn't changed.
   * Returns true if this channel's data changed.
   */
  function patch(key, value) {
    const fp = JSON.stringify(value)
    if (_fingerprints[key] === fp) {
      return false  // this channel didn't change
    }
    _fingerprints[key] = fp
    _loaded[key] = true  // mark this channel as loaded

    if (!data.value) {
      data.value = { [key]: value }
    } else {
      data.value = { ...data.value, [key]: value }
    }

    console.log('[MC] store.patch key=' + key + ' dataKeys=' + Object.keys(data.value).join(',') + ' firstTime=' + !_fingerprints._wasSet)
    _fingerprints._wasSet = true
    lastUpdated.value = Date.now() / 1000
    connected.value = true
    return true
  }

  /**
   * Check if a channel has delivered its first payload yet.
   * Used by widgets to distinguish "loading" from "empty/unconfigured."
   */
  function isChannelLoaded(key) {
    return !!_loaded[key]
  }

  /** Mark connection as lost (SSE error). Data is preserved. */
  function setDisconnected() {
    connected.value = false
  }

  return { data, connected, lastUpdated, hydrate, patch, isChannelLoaded, setDisconnected }
})
