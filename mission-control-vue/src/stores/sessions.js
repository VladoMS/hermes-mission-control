import { defineStore } from 'pinia'
import { computed, ref } from 'vue'

export const useSessionsStore = defineStore('sessions', () => {
  const sessions = ref([])
  const ledger = ref({})
  const dailyCosts = ref({ days: [], daily_average: 0.0, today_so_far: 0.0 })

  const filterProfile = ref('all')
  const filterModel = ref('all')

  const filteredSessions = computed(() => {
    let s = sessions.value
    if (filterProfile.value !== 'all') {
      s = s.filter(sess => sess.profile === filterProfile.value)
    }
    if (filterModel.value !== 'all') {
      s = s.filter(sess => (sess.model || 'unknown') === filterModel.value)
    }
    return s
  })

  const profilesInSessions = computed(() => {
    const names = new Set(sessions.value.map(s => s.profile).filter(Boolean))
    return [...names].sort()
  })

  const modelsInSessions = computed(() => {
    const names = new Set(sessions.value.map(s => s.model || 'unknown'))
    return [...names].sort()
  })

  const totalTokens = computed(() => ledger.value?.total_tokens || 0)
  const totalCost = computed(() => ledger.value?.total_estimated_cost_usd || 0)
  const cacheHitRate = computed(() => ledger.value?.cache_hit_rate_pct || 0)
  const sessionCount = computed(() => ledger.value?.session_count || 0)

  const pieByModel = computed(() => {
    const pm = ledger.value?.per_model || {}
    return Object.entries(pm).map(([name, data]) => ({
      name,
      inputTokens: data.input_tokens || 0,
      outputTokens: data.output_tokens || 0,
      cacheReadTokens: data.cache_read_tokens || 0,
      cacheWriteTokens: data.cache_write_tokens || 0,
      tokens: (data.input_tokens || 0) + (data.output_tokens || 0)
        + (data.cache_read_tokens || 0) + (data.cache_write_tokens || 0),
      cost: data.estimated_cost_usd || 0,
      sessions: data.sessions || 0,
    }))
  })

  const pieByProfile = computed(() => {
    const pp = ledger.value?.per_profile || {}
    return Object.entries(pp).map(([name, data]) => ({
      name,
      inputTokens: data.input_tokens || 0,
      outputTokens: data.output_tokens || 0,
      cacheReadTokens: data.cache_read_tokens || 0,
      cacheWriteTokens: data.cache_write_tokens || 0,
      tokens: (data.input_tokens || 0) + (data.output_tokens || 0)
        + (data.cache_read_tokens || 0) + (data.cache_write_tokens || 0),
      cost: data.estimated_cost_usd || 0,
      sessions: data.sessions || 0,
    }))
  })

  function setFilterProfile(profile) {
    filterProfile.value = profile
  }

  function setFilterModel(model) {
    filterModel.value = model
  }

  function resetFilters() {
    filterProfile.value = 'all'
    filterModel.value = 'all'
  }

  function patchSessions(newData) {
    sessions.value = newData
  }

  function patchLedger(newData) {
    ledger.value = newData
  }

  function patchDailyCosts(newData) {
    dailyCosts.value = newData
  }

  async function fetchSessions() {
    try {
      const r = await fetch('/api/v2/sessions')
      if (r.ok) sessions.value = await r.json()
    } catch (e) {
      console.warn('fetch /api/v2/sessions failed:', e)
    }
  }

  async function fetchLedger() {
    try {
      const r = await fetch('/api/v2/sessions-ledger')
      if (r.ok) ledger.value = await r.json()
    } catch (e) {
      console.warn('fetch /api/v2/sessions-ledger failed:', e)
    }
  }

  async function fetchDailyCosts() {
    try {
      const r = await fetch('/api/v2/daily-costs')
      if (r.ok) dailyCosts.value = await r.json()
    } catch (e) {
      console.warn('fetch /api/v2/daily-costs failed:', e)
    }
  }

  return {
    sessions, ledger, dailyCosts,
    filteredSessions, filterProfile, filterModel,
    profilesInSessions, modelsInSessions,
    totalTokens, totalCost, cacheHitRate, sessionCount,
    pieByModel, pieByProfile,
    setFilterProfile, setFilterModel, resetFilters,
    patchSessions, patchLedger, patchDailyCosts,
    fetchSessions, fetchLedger, fetchDailyCosts,
  }
})
