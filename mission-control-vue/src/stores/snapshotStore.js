import { defineStore } from 'pinia'
import { shallowRef } from 'vue'

export const useSnapshotStore = defineStore('snapshot', () => {
  /** Shallow ref — only .value reassignment triggers reactivity */
  const data = shallowRef(null)
  const connected = shallowRef(false)
  const lastUpdated = shallowRef(null)
  const _fingerprints = {}
  /** Serial counter incremented on every patch — brute-force reactivity trigger */
  const _version = shallowRef(0)

  function patch(key, value) {
    const fp = JSON.stringify(value)
    if (_fingerprints[key] === fp) return false
    _fingerprints[key] = fp

    // Build new object — new reference guarantees shallowRef triggers
    const prev = data.value || {}
    const next = {}
    // Copy all existing keys
    for (const k of Object.keys(prev)) {
      next[k] = prev[k]
    }
    // Set the new key
    next[key] = value
    data.value = next

    _version.value++
    lastUpdated.value = Date.now() / 1000
    connected.value = true
    return true
  }

  function setDisconnected() {
    connected.value = false
  }

  return { data, connected, lastUpdated, patch, setDisconnected }
})
