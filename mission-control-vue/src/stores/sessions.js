import { defineStore } from 'pinia'
import { computed, ref } from 'vue'
import { useSnapshotStore } from './snapshotStore.js'

/**
 * Sessions store — session list, token ledger, filters, and pie chart data.
 * Derives from snapshot.data.sessions and snapshot.data.sessions_ledger.
 */
export const useSessionsStore = defineStore('sessions', () => {
  const snap = useSnapshotStore()

  /** Unified session list (top 50, across all profiles) */
  const sessions = computed(() => snap.data?.sessions || [])

  /** Token/cost ledger aggregate */
  const ledger = computed(() => snap.data?.sessions_ledger || {})

  /** Daily cost breakdown with predictions */
  const dailyCosts = computed(() => snap.data?.daily_costs || { days: [], daily_average: 0.0, today_so_far: 0.0 })

  // ── Filters ────────────────────────────────────────────

  const filterProfile = ref('all')
  const filterModel = ref('all')

  /** Sessions filtered by profile and model */
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

  /** Unique profile names across all sessions */
  const profilesInSessions = computed(() => {
    const names = new Set(sessions.value.map(s => s.profile).filter(Boolean))
    return [...names].sort()
  })

  /** Unique model names across all sessions */
  const modelsInSessions = computed(() => {
    const names = new Set(sessions.value.map(s => s.model || 'unknown'))
    return [...names].sort()
  })

  /* Total from ledger */
  const totalTokens = computed(() => ledger.value?.total_tokens || 0)
  const totalCost = computed(() => ledger.value?.total_estimated_cost_usd || 0)
  const cacheHitRate = computed(() => ledger.value?.cache_hit_rate_pct || 0)
  const sessionCount = computed(() => ledger.value?.session_count || 0)

  // ── Pie chart data ─────────────────────────────────────

  /** Token distribution by model (for pie/donut charts) */
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

  /** Token distribution by profile (for pie/donut charts) */
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

  // ── Actions ────────────────────────────────────────────

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

  return {
    sessions,
    ledger,
    dailyCosts,
    filteredSessions,
    filterProfile,
    filterModel,
    profilesInSessions,
    modelsInSessions,
    totalTokens,
    totalCost,
    cacheHitRate,
    sessionCount,
    pieByModel,
    pieByProfile,
    setFilterProfile,
    setFilterModel,
    resetFilters,
  }
})
