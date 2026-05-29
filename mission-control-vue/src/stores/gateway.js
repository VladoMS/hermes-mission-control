import { defineStore } from 'pinia'
import { ref } from 'vue'

export const useGatewayStore = defineStore('gateway', () => {
  const data = ref(null)

  function patch(newData) {
    data.value = newData
  }

  async function fetchLatest() {
    try {
      const r = await fetch('/api/v2/gateway')
      if (r.ok) data.value = await r.json()
    } catch (e) {
      console.warn('fetch /api/v2/gateway failed:', e)
    }
  }

  return { data, patch, fetchLatest }
})
