<template>
  <header class="top-bar">
    <!-- Brand -->
    <div class="brand">
      <svg class="brand-svg" viewBox="0 0 24 24">
        <defs>
          <linearGradient id="hexGrad" x1="0" y1="0" x2="24" y2="24">
            <stop offset="0%" stop-color="var(--red)"/>
            <stop offset="100%" stop-color="var(--cyan)"/>
          </linearGradient>
        </defs>
        <polygon class="hex-ring" points="12,2 20,7 20,17 12,22 4,17 4,7"/>
        <circle class="hex-dot" cx="12" cy="12" r="3"/>
      </svg>
      <span class="brand-name">ADA</span>
      <span class="brand-sub">MISSION CONTROL</span>
    </div>

    <div class="divider"/>

    <!-- Desktop tabs -->
    <nav class="tabs">
      <router-link
        v-for="tab in tabs"
        :key="tab.id"
        :to="tab.path"
        class="tab"
        :class="{ active: isActive(tab.id) }"
      >
        {{ tab.label }}
      </router-link>
    </nav>

    <div class="spacer"/>

    <!-- Status cluster -->
    <div class="status-cluster">
      <button
        v-if="pwaInstall.installable.value"
        class="install-btn"
        @click="pwaInstall.install()"
        title="Install as desktop app"
      >
        <span class="install-icon">⬇</span>
        <span class="install-label">INSTALL</span>
      </button>
      <UplinkStatus />
      <span class="utc-clock">{{ uiStore.clock }}</span>
      <VersionBadge />
    </div>

    <!-- Hamburger (mobile) -->
    <button class="hamburger-btn" @click="uiStore.toggleMobileMenu()">
      <span/>
    </button>
  </header>
</template>

<script setup>
import { onMounted, onUnmounted } from 'vue'
import { useRoute } from 'vue-router'
import { useUiStore } from '../stores/ui.js'
import { usePwaInstall } from '../composables/usePwaInstall.js'
import UplinkStatus from './UplinkStatus.vue'
import VersionBadge from './VersionBadge.vue'

const route = useRoute()
const uiStore = useUiStore()
const pwaInstall = usePwaInstall()

const tabs = [
  { id: 'overview', label: 'Overview', path: '/' },
  { id: 'profiles', label: 'Profiles', path: '/profiles' },
  { id: 'kanban', label: 'Kanban', path: '/kanban' },
  { id: 'servers', label: 'Servers', path: '/servers' },
  { id: 'sessions', label: 'Sessions', path: '/sessions' },
  { id: 'content', label: 'Content', path: '/content' },
  { id: 'work-servers', label: 'Work', path: '/work-servers' },
]

function isActive(tabId) {
  return route.name === tabId
}

onMounted(() => {
  uiStore.startClock()
})

onUnmounted(() => {
  uiStore.stopClock()
})
</script>

<style scoped>
/* ── TOP BAR (44px) ── */
.top-bar {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  height: var(--top-h);
  background: linear-gradient(to bottom, rgba(8, 12, 17, 0.96), rgba(8, 12, 17, 0.9));
  backdrop-filter: blur(6px);
  -webkit-backdrop-filter: blur(6px);
  border-bottom: 1px solid var(--line);
  display: flex;
  align-items: center;
  padding: 0 18px;
  z-index: 60;
}

/* ── Brand ── */
.brand {
  display: flex;
  align-items: center;
  gap: 10px;
}

.brand-svg {
  width: 22px;
  height: 22px;
  flex-shrink: 0;
}

.brand-svg :deep(.hex-ring) {
  fill: none;
  stroke: url(#hexGrad);
  stroke-width: 1.6;
}

.brand-svg :deep(.hex-dot) {
  fill: var(--red);
  animation: pulse 2.4s ease-in-out infinite;
}

.brand-name {
  font-family: var(--font-display);
  font-weight: 700;
  letter-spacing: 0.22em;
  font-size: 14px;
  color: var(--text-hi);
  text-transform: uppercase;
}

.brand-sub {
  color: var(--red);
  letter-spacing: 0.22em;
  font-size: 10px;
  font-family: var(--font-mono);
}

.divider {
  width: 1px;
  height: 18px;
  background: var(--line);
  margin: 0 12px;
}

.spacer {
  flex: 1;
}

/* ── Pill tabs ── */
.tabs {
  display: flex;
  gap: 4px;
  align-items: center;
}

.tab {
  padding: 5px 14px;
  font-family: var(--font-mono);
  font-size: 10px;
  letter-spacing: 0.12em;
  text-transform: uppercase;
  color: var(--text-dim);
  cursor: pointer;
  border: 1px solid transparent;
  border-radius: 20px;
  background: transparent;
  transition: all 0.2s;
  white-space: nowrap;
  text-decoration: none;
}

.tab:hover {
  color: var(--text);
  border-color: var(--line-strong);
}

.tab.active {
  color: var(--cyan);
  background: rgba(30, 200, 255, 0.1);
  border-color: rgba(30, 200, 255, 0.3);
  font-weight: 600;
}

/* ── Hamburger ── */
.hamburger-btn {
  display: none;
  align-items: center;
  justify-content: center;
  width: 32px;
  height: 32px;
  background: transparent;
  border: 1px solid var(--line-strong);
  cursor: pointer;
  padding: 0;
  flex-shrink: 0;
}

.hamburger-btn span {
  display: block;
  width: 14px;
  height: 1px;
  background: var(--text-dim);
  position: relative;
  transition: background 0.2s;
}

.hamburger-btn span::before,
.hamburger-btn span::after {
  content: '';
  position: absolute;
  left: 0;
  width: 14px;
  height: 1px;
  background: var(--text-dim);
  transition: transform 0.2s;
}

.hamburger-btn span::before {
  top: -4px;
}

.hamburger-btn span::after {
  top: 4px;
}

.hamburger-btn:hover span,
.hamburger-btn:hover span::before,
.hamburger-btn:hover span::after {
  background: var(--text-hi);
}

/* ── Status cluster ── */
.status-cluster {
  display: flex;
  gap: 14px;
  align-items: center;
  font-family: var(--font-mono);
  font-size: 10px;
  letter-spacing: 0.12em;
  color: var(--text-dim);
}

.utc-clock {
  color: var(--text);
  letter-spacing: 0.08em;
}

/* ── PWA Install button ── */
.install-btn {
  display: flex;
  align-items: center;
  gap: 5px;
  padding: 3px 10px;
  background: var(--cyan);
  color: var(--bg-void);
  border: none;
  border-radius: 3px;
  font-family: var(--font-mono);
  font-size: 9px;
  font-weight: 600;
  letter-spacing: 0.1em;
  cursor: pointer;
  transition: background 0.2s;
}

.install-btn:hover {
  background: #3dd4ff;
}

.install-icon {
  font-size: 11px;
}

.install-label {
  white-space: nowrap;
}

/* ── Responsive ── */
@media (max-width: 900px) {
  .tabs {
    overflow-x: auto;
    gap: 0;
  }

  .tab {
    font-size: 9px;
    padding: 4px 10px;
  }

  .brand-sub {
    display: none;
  }
}

@media (max-width: 720px) {
  .top-bar {
    padding: 0 10px;
  }

  .status-cluster {
    font-size: 9px;
    gap: 8px;
  }

  .tabs {
    display: none;
  }

  .hamburger-btn {
    display: flex;
  }
}

@media (max-width: 480px) {
  .status-cluster {
    display: none;
  }
}

/* ── Animations ── */
@keyframes pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.4; }
}
</style>
