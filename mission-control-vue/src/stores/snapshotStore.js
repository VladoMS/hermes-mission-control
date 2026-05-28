import { defineStore } from 'pinia'
import { ref } from 'vue'

export const useSnapshotStore = defineStore('snapshot', () => {
  const data = ref({})
  const connected = ref(false)
  const lastUpdated = ref(null)
  const _fingerprints = {}

  function patch(key, value) {
    const fp = JSON.stringify(value)
    if (_fingerprints[key] === fp) return false
    _fingerprints[key] = fp

    // Clone + assign to guarantee new reference for ref reactivity
    const next = Object.assign({}, data.value)
    next[key] = value
    data.value = next

    lastUpdated.value = Date.now() / 1000
    connected.value = true
    return true
  }

  function setDisconnected() {
    connected.value = false
  }

  return { data, connected, lastUpdated, patch, setDisconnected }
})
