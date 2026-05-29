import { defineStore } from 'pinia'
import { ref, computed } from 'vue'

const ACCENTS = {
  default:    '#1ec8ff',
  coder:      '#ff3b1f',
  researcher: '#4ade80',
  writer:     '#ffb020',
  devops:     '#d946ef',
  creative:   '#1ec8ff',
}

const BADGES = {
  default:    'ADA',
  coder:      'DEV',
  researcher: 'RCH',
  writer:     'WRT',
  devops:     'OPS',
  creative:   'ART',
}

export const useProfilesStore = defineStore('profiles', () => {
  const data = ref([])

  const profiles = computed(() => data.value || [])

  const activeCount = computed(() =>
    profiles.value.filter(p =>
      (p.state_db_stats?.active_sessions || 0) > 0
    ).length
  )

  const idleCount = computed(() =>
    profiles.value.filter(p =>
      p.has_state_db && (p.state_db_stats?.active_sessions || 0) === 0
    ).length
  )

  const dormantCount = computed(() =>
    profiles.value.filter(p => !p.has_state_db).length
  )

  function getStatus(profile) {
    if (!profile?.has_state_db) return 'dormant'
    if ((profile.state_db_stats?.active_sessions || 0) > 0) return 'active'
    return 'idle'
  }

  function getAccent(name) {
    return ACCENTS[name] || '#6b7585'
  }

  function getBadge(name) {
    return BADGES[name] || (name ? name.slice(0, 3).toUpperCase() : '???')
  }

  function patch(newData) {
    data.value = newData
  }

  async function fetchLatest() {
    try {
      const r = await fetch('/api/v2/profiles')
      if (r.ok) data.value = await r.json()
    } catch (e) {
      console.warn('fetch /api/v2/profiles failed:', e)
    }
  }

  return {
    data, profiles, activeCount, idleCount, dormantCount,
    getStatus, getAccent, getBadge, ACCENTS, BADGES,
    patch, fetchLatest,
  }
})
