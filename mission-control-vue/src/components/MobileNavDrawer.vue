<template>
  <div v-if="open" class="drawer-overlay" @click="$emit('close')"/>
  <aside class="mobile-drawer" :class="{ open }">
    <nav class="drawer-nav">
      <button
        v-for="tab in tabs"
        :key="tab.id"
        class="drawer-tab"
        :class="{ active: isActive(tab.id) }"
        @click="uiStore.navigateTo(tab.id)"
      >
        {{ tab.label }}
      </button>
    </nav>
  </aside>
</template>

<script setup>
import { useRoute } from 'vue-router'
import { useUiStore } from '../stores/ui.js'

defineProps({
  open: { type: Boolean, default: false },
  tabs: { type: Array, default: () => [] },
})
defineEmits(['close'])

const route = useRoute()
const uiStore = useUiStore()

function isActive(tabId) {
  return route.name === tabId
}
</script>

<style scoped>
.mobile-drawer {
  position: fixed;
  top: var(--top-h);
  right: 0;
  bottom: 0;
  width: 280px;
  max-width: 80vw;
  background: var(--bg-surface);
  border-left: 1px solid var(--line);
  z-index: 70;
  transform: translateX(100%);
  transition: transform 0.25s ease;
  padding: 20px;
}

.mobile-drawer.open {
  transform: translateX(0);
}

.drawer-nav {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.drawer-tab {
  display: block;
  width: 100%;
  text-align: left;
  padding: 10px 14px;
  font-family: var(--font-mono);
  font-size: 11px;
  letter-spacing: 0.12em;
  text-transform: uppercase;
  color: var(--text-dim);
  background: transparent;
  border: 1px solid transparent;
  border-left: 2px solid transparent;
  cursor: pointer;
  transition: all 0.2s;
}

.drawer-tab:hover {
  color: var(--text);
  background: rgba(255, 255, 255, 0.03);
}

.drawer-tab.active {
  color: var(--text-hi);
  border-left-color: var(--red);
  background: var(--red-bg);
}

.drawer-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.5);
  z-index: 69;
}
</style>
