import { defineStore } from 'pinia'
import { reactive, ref } from 'vue'

export const useSnapshotStore = defineStore('snapshot', () => {
  /** Reactive data object — mutated directly, no spreads needed */
  const data = reactive({})
  const connected = ref(false)
  const lastUpdated = ref(null)
  const _fingerprints = {}

  /**
   * Per-channel patch. Mutates `data` directly by setting `data[key] = value`.
   * Fingerprint-gated: skips if identical to last payload for this key.
   */
  function patch(key, value) {
    const fp = JSON.stringify(value)
    if (_fingerprints[key] === fp) return false
    _fingerprints[key] = fp

    // Direct mutation on reactive object — Vue tracks property sets
    data[key] = value

    lastUpdated.value = Date.now() / 1000
    connected.value = true
    return true
  }

  function setDisconnected() {
    connected.value = false
  }

  return { data, connected, lastUpdated, patch, setDisconnected }
})
