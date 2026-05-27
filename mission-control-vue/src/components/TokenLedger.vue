<template>
  <div class="token-ledger panel">
    <div class="eyebrow">TOKEN LEDGER</div>
    <div class="ledger-grid">
      <div class="ledger-cell">
        <div class="ledger-label">Total Tokens</div>
        <div class="ledger-val">{{ fmtTokens(ledger.total_tokens) }}</div>
      </div>
      <div class="ledger-cell">
        <div class="ledger-label">Est. Cost</div>
        <div class="ledger-val">{{ fmtCost(ledger.total_estimated_cost_usd) }}</div>
      </div>
      <div class="ledger-cell">
        <div class="ledger-label">Sessions</div>
        <div class="ledger-val">{{ ledger.session_count || 0 }}</div>
      </div>
      <div class="ledger-cell">
        <div class="ledger-label">Cache Hit Rate</div>
        <div class="ledger-val">{{ cacheHitRate }}</div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { useSessionsStore } from '../stores/sessions.js'

const sessionsStore = useSessionsStore()
const ledger = computed(() => sessionsStore.ledger)
const cacheHitRate = computed(() => (sessionsStore.cacheHitRate || 0).toFixed(1) + '%')

function fmtTokens(n) {
  if (!n && n !== 0) return '--'
  if (n >= 1e9) return (n / 1e9).toFixed(1) + 'B'
  if (n >= 1e6) return (n / 1e6).toFixed(1) + 'M'
  if (n >= 1e3) return (n / 1e3).toFixed(1) + 'K'
  return String(n)
}

function fmtCost(n) {
  if (!n && n !== 0) return '--'
  return '$' + n.toFixed(2)
}
</script>

<style scoped>
.token-ledger { padding: 18px; margin-bottom: 28px; }
.ledger-grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 1px;
  background: var(--line);
  margin-top: 14px;
}
.ledger-cell {
  background: var(--bg-deep);
  padding: 14px;
  text-align: center;
}
.ledger-label {
  font-family: var(--font-mono);
  font-size: 9px;
  letter-spacing: 0.12em;
  color: var(--text-dim);
  text-transform: uppercase;
  margin-bottom: 6px;
}
.ledger-val {
  font-family: var(--font-display);
  font-size: 20px;
  font-weight: 600;
  color: var(--text-hi);
}
@media (max-width: 720px) {
  .ledger-grid { grid-template-columns: repeat(2, 1fr); }
}
</style>
