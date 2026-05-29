import { defineStore } from 'pinia'
import { ref } from 'vue'

export const useOpenRouterStore = defineStore('openrouter', () => {
  const data = ref(null)

  function patch(newData) {
    data.value = newData
  }

  async function fetchLatest() {
    try {
      const r = await fetch('/api/v2/openrouter-usage')
      if (r.ok) data.value = await r.json()
    } catch (e) {
      console.warn('fetch /api/v2/openrouter-usage failed:', e)
    }
  }

  return { data, patch, fetchLatest }
})
