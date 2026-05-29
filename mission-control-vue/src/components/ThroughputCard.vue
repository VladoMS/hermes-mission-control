<template>
  <div class="throughput-card panel">
    <div class="eyebrow">THROUGHPUT</div>
    <div class="tp-total">{{ totalSessions }}</div>
    <div class="tp-sub">total sessions</div>
    <ThroughputSparkline />
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { useSessionsStore } from '../stores/sessions.js'
import ThroughputSparkline from './ThroughputSparkline.vue'

const sess = useSessionsStore()

const totalSessions = computed(() => {
  return sess.ledger?.session_count || sess.sessions?.length || '--'
})
</script>

<style scoped>
.throughput-card {
  padding: 18px;
  margin-bottom: 28px;
  min-height: 0;
  overflow: hidden;
}
.tp-total {
  font-family: var(--font-display);
  font-size: clamp(32px, 3vw, 48px);
  font-weight: 700;
  line-height: 1;
  color: var(--text-hi);
  margin-top: 6px;
}
.tp-sub {
  font-family: var(--font-mono);
  font-size: 10px;
  letter-spacing: 0.15em;
  color: var(--text-faint);
  text-transform: uppercase;
  margin-bottom: 18px;
}
</style>
