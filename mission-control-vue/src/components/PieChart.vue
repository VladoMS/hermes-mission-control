<template>
  <div class="pie-chart panel">
    <div class="eyebrow">TOKEN DISTRIBUTION</div>
    <div class="pie-wrap">
      <canvas ref="canvas" width="200" height="200"></canvas>
      <div class="pie-legend">
        <div v-for="e in legend" :key="e.name" class="legend-item">
          <span class="legend-dot" :style="{ background: e.color }"></span>
          <span class="legend-name">{{ e.name }}</span>
          <span class="legend-val">{{ fmtTokens(e.tokens) }}</span>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, watch, onMounted, computed } from 'vue'
import { useSessionsStore } from '../stores/sessions.js'

const sessionsStore = useSessionsStore()
const canvas = ref(null)

const COLORS = ['#ff3b1f', '#1ec8ff', '#ffb020', '#4ade80', '#d946ef', '#fbbf24', '#5cd9ff', '#ffc657']

function fmtTokens(n) {
  if (!n && n !== 0) return '--'
  if (n >= 1e6) return (n / 1e6).toFixed(1) + 'M'
  if (n >= 1e3) return (n / 1e3).toFixed(1) + 'K'
  return String(n)
}

const legend = computed(() => {
  const pie = sessionsStore.pieByModel
  return pie.slice(0, 8).map((e, i) => ({ ...e, color: COLORS[i] || '#6b7585' }))
})

function draw() {
  const c = canvas.value
  if (!c) return
  const ctx = c.getContext('2d')
  const w = c.width, h = c.height
  const cx = w / 2, cy = h / 2, r = 70
  ctx.clearRect(0, 0, w, h)

  const entries = legend.value
  const grandTotal = entries.reduce((s, e) => s + e.tokens, 0)
  if (grandTotal === 0) {
    ctx.fillStyle = 'var(--text-faint)'
    ctx.font = '10px "JetBrains Mono"'
    ctx.textAlign = 'center'
    ctx.fillText('NO DATA', cx, cy)
    return
  }

  let angle = -Math.PI / 2
  for (let i = 0; i < entries.length; i++) {
    const slice = (entries[i].tokens / grandTotal) * Math.PI * 2
    ctx.beginPath()
    ctx.moveTo(cx, cy)
    ctx.arc(cx, cy, r, angle, angle + slice)
    ctx.closePath()
    ctx.fillStyle = entries[i].color
    ctx.fill()
    ctx.strokeStyle = 'rgba(0,0,0,0.3)'
    ctx.lineWidth = 1
    ctx.stroke()
    angle += slice
  }

  // Center dot
  ctx.beginPath()
  ctx.arc(cx, cy, 16, 0, Math.PI * 2)
  ctx.fillStyle = 'var(--bg-void)'
  ctx.fill()
}

watch(() => sessionsStore.pieByModel, draw, { deep: true })
onMounted(draw)
</script>

<style scoped>
.pie-chart { padding: 18px; }
.pie-wrap {
  display: flex;
  align-items: center;
  gap: 20px;
  margin-top: 12px;
}
.pie-legend { flex: 1; }
.legend-item {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 3px 0;
  font-family: var(--font-mono);
  font-size: 10px;
}
.legend-dot { width: 8px; height: 8px; border-radius: 50%; flex-shrink: 0; }
.legend-name { color: var(--text-dim); flex: 1; }
.legend-val { color: var(--text-faint); }
@media (max-width: 720px) {
  .pie-wrap { flex-direction: column; }
}
</style>
