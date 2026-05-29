<template>
  <div class="health-bar-row">
    <div class="health-label">{{ label }}</div>
    <div class="health-bar">
      <div class="fill" :style="barStyle" :class="barClass"></div>
    </div>
    <div class="health-pct" :style="{ color: pctColor }">{{ displayValue }}</div>
  </div>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  label: { type: String, required: true },
  pct: { type: Number, default: null },
  suffix: { type: String, default: '%' },
})

const displayValue = computed(() => props.pct != null ? props.pct.toFixed(0) + props.suffix : '--')
const pctColor = computed(() => {
  if (props.pct == null) return 'var(--text-faint)'
  if (props.pct > 85) return 'var(--red)'
  if (props.pct > 70) return 'var(--amber)'
  return 'var(--text-dim)'
})
const barStyle = computed(() => {
  const p = props.pct != null ? Math.min(props.pct, 100) : 0
  return { width: p + '%' }
})
const barClass = computed(() => {
  if (props.pct == null) return ''
  if (props.pct > 85) return 'red'
  if (props.pct > 70) return 'amber'
  return ''
})
</script>

<style scoped>
.health-bar-row {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 6px;
}
.health-label {
  font-family: var(--font-mono);
  font-size: 9px;
  letter-spacing: 0.1em;
  color: var(--text-faint);
  width: 32px;
  text-transform: uppercase;
}
.health-bar {
  flex: 1;
  height: 5px;
  background: rgba(255, 255, 255, 0.06);
  overflow: hidden;
}
.fill {
  height: 100%;
  min-width: 0;
  background: linear-gradient(90deg, var(--green), var(--amber));
  transition: width 0.4s;
}
.fill.red { background: var(--red); }
.fill.amber { background: var(--amber); }
.health-pct {
  font-family: var(--font-mono);
  font-size: 12px;
  width: 34px;
  text-align: right;
}
</style>
