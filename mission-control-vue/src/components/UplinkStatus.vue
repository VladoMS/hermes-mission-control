<template>
  <span class="uplink-label">
    <span class="status-dot" :class="dotClass" />
    {{ label }}
  </span>
</template>

<script setup>
import { computed } from 'vue'
import { useSSE } from '../composables/useSSE.js'

const { uplink } = useSSE()

const dotClass = computed(() => {
  switch (uplink.value) {
    case 'synced': return ''
    case 'degraded':
    case 'connecting': return 'amber'
    case 'offline':
    case 'disconnected': return 'red'
    default: return ''
  }
})

const label = computed(() => {
  switch (uplink.value) {
    case 'synced': return 'UPLINK SYNCED'
    case 'degraded': return 'UPLINK DEGRADED'
    case 'connecting': return 'UPLINK CONNECTING'
    case 'offline': return 'UPLINK OFFLINE'
    case 'disconnected': return 'UPLINK \u2014'
    default: return 'UPLINK \u2014'
  }
})
</script>

<style scoped>
.uplink-label {
  display: flex;
  align-items: center;
  gap: 7px;
  color: var(--green);
  letter-spacing: 0.18em;
}

.status-dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: var(--green);
  box-shadow: 0 0 8px var(--green), 0 0 2px var(--green);
  animation: pulse 2.4s ease-in-out infinite;
  flex-shrink: 0;
  display: inline-block;
}

.status-dot.red {
  background: var(--red);
  box-shadow: 0 0 8px var(--red-glow);
}

.status-dot.amber {
  background: var(--amber);
  box-shadow: 0 0 8px var(--amber);
}

.status-dot.cyan {
  background: var(--cyan);
  box-shadow: 0 0 8px var(--cyan);
}

@keyframes pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.4; }
}
</style>
