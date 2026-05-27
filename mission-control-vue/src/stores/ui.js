import { defineStore } from 'pinia'
import { ref } from 'vue'
import router from '../router/index.js'

/**
 * UI store — active tab (synced with route), mobile menu, and clock.
 * Pure local state; does not derive from snapshot data.
 */
export const useUiStore = defineStore('ui', () => {
  /** Currently active tab name — synced with Vue Router */
  const activeTab = ref('overview')

  /** Mobile navigation drawer open state */
  const mobileMenuOpen = ref(false)

  /** Live clock string (e.g., "14:32:07") */
  const clock = ref('')

  // ── Navigation ─────────────────────────────────────────

  /**
   * Navigate to a tab by name.
   * Maps tab name to route path and closes the mobile drawer.
   */
  function navigateTo(tab) {
    activeTab.value = tab
    if (tab === 'overview') {
      router.push('/')
    } else {
      router.push(`/${tab}`)
    }
    mobileMenuOpen.value = false
  }

  /** Toggle the mobile navigation drawer */
  function toggleMobileMenu() {
    mobileMenuOpen.value = !mobileMenuOpen.value
  }

  /** Close the mobile drawer */
  function closeMobileMenu() {
    mobileMenuOpen.value = false
  }

  // ── Clock ──────────────────────────────────────────────

  let clockInterval = null

  /** Start the live clock (GB locale, HH:MM:SS). Idempotent. */
  function startClock() {
    if (clockInterval) return
    const tick = () => {
      const now = new Date()
      clock.value = now.toLocaleTimeString('en-GB', {
        hour: '2-digit',
        minute: '2-digit',
        second: '2-digit',
      })
    }
    tick()
    clockInterval = setInterval(tick, 1000)
  }

  /** Stop the clock interval */
  function stopClock() {
    if (clockInterval) {
      clearInterval(clockInterval)
      clockInterval = null
    }
  }

  return {
    activeTab,
    mobileMenuOpen,
    clock,
    navigateTo,
    toggleMobileMenu,
    closeMobileMenu,
    startClock,
    stopClock,
  }
})
