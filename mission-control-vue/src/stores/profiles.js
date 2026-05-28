import { defineStore } from 'pinia'
import { computed } from 'vue'
import { useSnapshotStore } from './snapshotStore.js'

/**
 * Profile status → accent color mapping.
 * Inspired by vladoms design tokens.
 */
const ACCENTS = {
  default:    '#1ec8ff',  // cyan
  coder:      '#ff3b1f',  // red
  researcher: '#4ade80',  // green
  writer:     '#ffb020',  // amber
  devops:     '#d946ef',  // magenta
  creative:   '#1ec8ff',  // cyan
}

/** Profile name → short badge label. Fallback: first 3 chars uppercase. */
const BADGES = {
  default:    'ADA',
  coder:      'DEV',
  researcher: 'RCH',
  writer:     'WRT',
  devops:     'OPS',
  creative:   'ART',
}

export const useProfilesStore = defineStore('profiles', () => {
  const snap = useSnapshotStore()

  /** All profiles from snapshot (unwraps channel wrapper if present) */
  const profiles = computed(() => {
    const p = snap.data?.profiles
    return Array.isArray(p) ? p : (p?.profiles || [])
  })

  /** Profiles with at least one active session */
  const activeCount = computed(() =>
    profiles.value.filter(p =>
      (p.state_db_stats?.active_sessions || 0) > 0
    ).length
  )

  /** Profiles with state DB but zero active sessions */
  const idleCount = computed(() =>
    profiles.value.filter(p =>
      p.has_state_db && (p.state_db_stats?.active_sessions || 0) === 0
    ).length
  )

  /** Profiles without a state DB (never used) */
  const dormantCount = computed(() =>
    profiles.value.filter(p => !p.has_state_db).length
  )

  /**
   * Classify a profile as 'active', 'idle', or 'dormant'.
   */
  function getStatus(profile) {
    if (!profile?.has_state_db) return 'dormant'
    if ((profile.state_db_stats?.active_sessions || 0) > 0) return 'active'
    return 'idle'
  }

  /** Get the accent color for a profile by name. Falls back to dim text color. */
  function getAccent(name) {
    return ACCENTS[name] || '#6b7585'
  }

  /** Get the badge label for a profile by name. */
  function getBadge(name) {
    return BADGES[name] || (name ? name.slice(0, 3).toUpperCase() : '???')
  }

  return {
    profiles,
    activeCount,
    idleCount,
    dormantCount,
    getStatus,
    getAccent,
    getBadge,
    ACCENTS,
    BADGES,
  }
})
