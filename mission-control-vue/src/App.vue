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
import { onMounted, onUnmounted } from 'vue'
import { useSSE } from './composables/useSSE.js'
import { useUiStore } from './stores/ui.js'
import TopBar from './components/TopBar.vue'
import BackgroundLayers from './components/BackgroundLayers.vue'
import MobileNavDrawer from './components/MobileNavDrawer.vue'
import ToastNotification from './components/ToastNotification.vue'

const uiStore = useUiStore()

const navTabs = [
  { id: 'overview', label: 'Overview' },
  { id: 'profiles', label: 'Profiles' },
  { id: 'kanban', label: 'Kanban' },
  { id: 'servers', label: 'Servers' },
  { id: 'sessions', label: 'Sessions' },
  { id: 'content', label: 'Content' },
]

const { connect } = useSSE()

onMounted(() => {
  connect()
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
