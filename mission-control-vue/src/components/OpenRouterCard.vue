<template>
  <div class="or-card panel">
    <div class="eyebrow">OPENROUTER</div>

    <!-- Total spend -->
    <div class="or-spend">{{ fmtUsd(data.total_usage_usd) }}</div>
    <div class="tp-sub">total spend</div>

    <!-- Period breakdown -->
    <div class="or-breakdown" v-if="hasData">
      <div class="or-period">
        <div class="or-period-label">24H</div>
        <div class="or-period-val">{{ fmtUsd(data.usage_daily_usd) }}</div>
      </div>
      <div class="or-period">
        <div class="or-period-label">7D</div>
        <div class="or-period-val">{{ fmtUsd(data.usage_weekly_usd) }}</div>
      </div>
      <div class="or-period">
        <div class="or-period-label">30D</div>
        <div class="or-period-val">{{ fmtUsd(data.usage_monthly_usd) }}</div>
      </div>
    </div>

    <!-- Credit remaining (only if limit is set) -->
    <div class="or-remaining" v-if="data.credit_remaining_usd != null">
      <div class="or-rem-label">CREDITS REMAINING</div>
      <div class="or-rem-val">{{ fmtUsd(data.credit_remaining_usd) }}</div>
    </div>

    <!-- Error state -->
    <div class="or-error" v-if="data.error">
      {{ data.error }}
    </div>

    <!-- Loading -->
    <div class="or-loading" v-if="!hasData && !data.error">
      <span class="loading-text">AWAITING DATA...</span>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { useOpenRouterStore } from '../stores/openrouter.js'

const or = useOpenRouterStore()

const data = computed(() => {
  return or.data || {}
})

const hasData = computed(() => {
  return data.value.total_usage_usd != null || data.value.usage_daily_usd != null
})

function fmtUsd(n) {
  if (n == null || n === undefined) return '--'
  return '$' + Number(n).toFixed(4)
}
</script>

<style scoped>
.or-card {
  padding: 18px;
  min-height: 0;
  overflow: hidden;
}

.or-spend {
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

.or-breakdown {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 1px;
  background: var(--line);
  margin-bottom: 12px;
}

.or-period {
  background: var(--bg-deep);
  padding: 10px 8px;
  text-align: center;
}

.or-period-label {
  font-family: var(--font-mono);
  font-size: 10px;
  letter-spacing: 0.15em;
  color: var(--text-dim);
  margin-bottom: 4px;
}

.or-period-val {
  font-family: var(--font-display);
  font-size: 16px;
  font-weight: 600;
  color: var(--cyan);
}

.or-remaining {
  border-top: 1px solid var(--line);
  padding-top: 12px;
  margin-top: 4px;
  display: flex;
  justify-content: space-between;
  align-items: baseline;
}

.or-rem-label {
  font-family: var(--font-mono);
  font-size: 10px;
  letter-spacing: 0.15em;
  color: var(--text-dim);
  text-transform: uppercase;
}

.or-rem-val {
  font-family: var(--font-display);
  font-size: 18px;
  font-weight: 600;
  color: var(--green);
}

.or-error {
  font-family: var(--font-mono);
  font-size: 11px;
  color: var(--red);
  margin-top: 8px;
}

.or-loading {
  margin-top: 8px;
}

.loading-text {
  font-family: var(--font-mono);
  font-size: 10px;
  letter-spacing: 0.15em;
  color: var(--text-faint);
}
</style>
