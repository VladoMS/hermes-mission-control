<template>
  <div class="servers-page section">
    <div class="section-head">
      <div class="title-block">
        <div class="eyebrow">SERVERS</div>
        <div class="display medium">{{ serverCount }} MACHINES</div>
      </div>
    </div>

    <div class="servers-list">
      <ServerCard
        v-for="srv in servers"
        :key="srv.name"
        :server="srv"
      />
      <div v-if="servers.length === 0" class="placeholder-panel">
        No server data — check servers.json
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { useServersStore } from '../stores/servers.js'
import ServerCard from '../components/ServerCard.vue'

const serversStore = useServersStore()
const servers = computed(() => serversStore.servers)
const serverCount = computed(() => serversStore.serverCount)
</script>

<style scoped>
.servers-page { position: relative; z-index: 5; }
.servers-list {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 12px;
  align-items: start;
}
.placeholder-panel {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 200px;
  color: var(--text-faint);
  font-family: var(--font-mono);
  font-size: 12px;
  letter-spacing: 0.15em;
  text-transform: uppercase;
}
</style>
