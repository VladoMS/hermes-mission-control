<template>
  <div class="directive-bar">
    <span class="directive-icon">◆</span>
    <Transition name="directive-fade" mode="out-in">
      <span class="directive-text" :key="current">{{ current }}</span>
    </Transition>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { useSnapshotStore } from '../stores/snapshotStore.js'

const snap = useSnapshotStore()
const current = ref('INITIALIZING')

const directives = computed(() => {
  const d = snap.data
  if (!d) return ['NO DATA']
  const lines = []
  const profiles = d.profiles || []
  if (profiles.length) lines.push('MONITORING ' + profiles.length + ' PROFILES')
  const gw = d.gateway || {}
  if (gw.gateway_state === 'running') lines.push('GATEWAY ONLINE — ' + (gw.active_agents || 0) + ' AGENTS')
  const kanban = d.kanban?.boards || {}
  let blocked = 0
  for (const b of Object.values(kanban)) blocked += (b.columns?.blocked || []).length
  if (blocked) lines.push(blocked + ' BLOCKED TASKS ACTIVE')
  const errors = d.errors || []
  if (errors.length) lines.push(errors.length + ' DATA SOURCE ERRORS')
  if (d.timestamp_iso) lines.push('LAST SNAPSHOT: ' + d.timestamp_iso.replace('T', ' ').slice(0, 19))
  return lines.length ? lines : ['SYSTEM NOMINAL']
})

let idx = 0
let timer = null
function cycle() {
  const lines = directives.value
  if (!lines.length) return
  current.value = lines[idx % lines.length]
  idx++
}
onMounted(() => {
  cycle()
  timer = setInterval(cycle, 2600)
})
onUnmounted(() => { if (timer) clearInterval(timer) })
</script>

<style scoped>
.directive-bar {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 18px;
  background: var(--bg-deep);
  border: 1px solid var(--line);
  margin-bottom: 28px;
  font-family: var(--font-mono);
  font-size: 10px;
  letter-spacing: 0.18em;
  text-transform: uppercase;
  color: var(--text-dim);
}
.directive-icon {
  color: var(--red);
  font-size: 8px;
  flex-shrink: 0;
}
.directive-text {
  white-space: nowrap;
}
.directive-fade-enter-active,
.directive-fade-leave-active {
  transition: opacity 0.3s ease;
}
.directive-fade-enter-from,
.directive-fade-leave-to {
  opacity: 0;
}
</style>
