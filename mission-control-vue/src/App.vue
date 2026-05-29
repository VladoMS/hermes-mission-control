<template>
  <BackgroundLayers />
  <TopBar />
  <MobileNavDrawer
    :open="uiStore.mobileMenuOpen"
    :tabs="navTabs"
    @close="uiStore.closeMobileMenu()"
  />
  <main class="frame">
    <router-view />
  </main>
  <ToastNotification />
</template>

<script setup>
import { onMounted, onUnmounted, watch, computed } from 'vue'
import { useRoute } from 'vue-router'
import { useSSE } from './composables/useSSE.js'
import { useUiStore } from './stores/ui.js'
import TopBar from './components/TopBar.vue'
import BackgroundLayers from './components/BackgroundLayers.vue'
import MobileNavDrawer from './components/MobileNavDrawer.vue'
import ToastNotification from './components/ToastNotification.vue'

const uiStore = useUiStore()
const route = useRoute()

const navTabs = [
  { id: 'overview', label: 'Overview' },
  { id: 'profiles', label: 'Profiles' },
  { id: 'kanban', label: 'Kanban' },
  { id: 'servers', label: 'Servers' },
  { id: 'sessions', label: 'Sessions' },
  { id: 'content', label: 'Content' },
  { id: 'work-servers', label: 'Work' },
]

// ── Page → SSE channel mapping ───────────────────────────────────────
const PAGE_CHANNELS = {
  overview:  ['gateway', 'processes', 'hermes-health', 'sessions-ledger',
              'profiles', 'sessions', 'kanban', 'prod-health',
              'openrouter-usage'],
  profiles:  ['profiles'],
  kanban:    ['kanban'],
  servers:   ['servers', 'dokku', 'prod-health', 'server-crons'],
  sessions:  ['sessions', 'sessions-ledger', 'daily-costs'],
  content:   [],  // Content page uses its own REST API — no SSE needed
}

const routeChannels = computed(() => {
  const name = route.name || 'overview'
  return PAGE_CHANNELS[name] || null
})

const { connect } = useSSE()

onMounted(() => {
  connect(routeChannels.value)
})

watch(routeChannels, (channels) => {
  connect(channels)
})

onUnmounted(() => {
  uiStore.stopClock()
})
</script>

<style scoped>
.frame {
  padding-top: var(--top-h);
  padding-bottom: 24px;
  position: relative;
  z-index: 5;
}
</style>
