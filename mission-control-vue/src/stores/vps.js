import { defineStore } from 'pinia'
import { ref, computed } from 'vue'

export const useVpsStore = defineStore('vps', () => {
  const hermes = ref(null)
  const prod = ref(null)

  const all = computed(() => ({
    hermes: hermes.value,
    prod: prod.value,
  }))

  function patchHermes(newData) {
    hermes.value = newData
  }

  function patchProd(newData) {
    prod.value = newData
  }

  async function fetchHermes() {
    try {
      const r = await fetch('/api/v2/hermes-health')
      if (r.ok) hermes.value = await r.json()
    } catch (e) {
      console.warn('fetch /api/v2/hermes-health failed:', e)
    }
  }

  async function fetchProd() {
    try {
      const r = await fetch('/api/v2/prod-health')
      if (r.ok) prod.value = await r.json()
    } catch (e) {
      console.warn('fetch /api/v2/prod-health failed:', e)
    }
  }

  return { hermes, prod, all, patchHermes, patchProd, fetchHermes, fetchProd }
})
