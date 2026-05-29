<template>
  <div class="cost-chart panel">
    <div class="eyebrow">DAILY COSTS</div>
    <div class="chart-header">
      <div class="chart-stat">
        <span class="stat-label">Daily Avg</span>
        <span class="stat-val">{{ fmtCost(dailyAverage) }}</span>
      </div>
      <div class="chart-stat">
        <span class="stat-label">Today So Far</span>
        <span class="stat-val">{{ fmtCost(todaySoFar) }}</span>
      </div>
      <div class="chart-stat projected">
        <span class="stat-label">Est. Monthly</span>
        <span class="stat-val">{{ fmtCost(monthlyProjection) }}</span>
      </div>
      <div class="chart-legend">
        <span class="legend-item"><span class="legend-dot actual"></span> Actual</span>
        <span class="legend-item"><span class="legend-dot predicted"></span> Predicted</span>
        <span class="legend-item"><span class="legend-dot avg"></span> Avg</span>
      </div>
    </div>
    <div class="canvas-wrap">
      <canvas ref="canvas"></canvas>
    </div>
  </div>
</template>

<script setup>
import { ref, watch, onMounted, computed, nextTick } from 'vue'
import { useSessionsStore } from '../stores/sessions.js'

const sessionsStore = useSessionsStore()
const canvas = ref(null)

const dailyCosts = computed(() => sessionsStore.dailyCosts)
const days = computed(() => dailyCosts.value?.days || [])
const dailyAverage = computed(() => dailyCosts.value?.daily_average || 0)
const todaySoFar = computed(() => dailyCosts.value?.today_so_far || 0)
const monthlyProjection = computed(() => dailyCosts.value?.monthly_projection || 0)

function fmtCost(n) {
  if (!n && n !== 0) return '--'
  return '$' + Number(n).toFixed(4)
}

// ── Canvas drawing ─────────────────────────────────────────

const COLORS = {
  actual: '#1ec8ff',
  predicted: '#ffb020',
  avg: '#4ade80',
  grid: '#0c121a',
  text: '#6b7585',
  textHi: '#b6c0cb',
}

function formatDateLabel(dateStr) {
  // Show "Mon DD" — e.g., "May 28"
  try {
    const parts = dateStr.split('-')
    const d = new Date(Number(parts[0]), Number(parts[1]) - 1, Number(parts[2]))
    return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric' })
  } catch {
    return dateStr
  }
}

function draw() {
  const c = canvas.value
  if (!c) return
  const ctx = c.getContext('2d')

  // Responsive sizing
  const container = c.parentElement
  const width = container?.clientWidth || 600
  c.width = width
  c.height = 180

  const w = c.width
  const h = c.height
  const pad = { top: 16, right: 16, bottom: 32, left: 48 }
  const plotW = w - pad.left - pad.right
  const plotH = h - pad.top - pad.bottom

  ctx.clearRect(0, 0, w, h)

  const entries = days.value
  if (!entries || entries.length === 0) {
    ctx.fillStyle = '#586573'
    ctx.font = '10px "JetBrains Mono"'
    ctx.textAlign = 'center'
    ctx.fillText('NO DATA', w / 2, h / 2)
    return
  }

  // Compute value range
  let maxVal = 0
  for (const e of entries) {
    const v = Math.max(e.cost || 0, e.prediction || 0)
    if (v > maxVal) maxVal = v
  }
  if (dailyAverage.value > maxVal) maxVal = dailyAverage.value
  if (maxVal === 0) maxVal = 0.01
  // Round up to a nice ceiling
  const ceil = Math.pow(10, Math.floor(Math.log10(maxVal)))
  maxVal = Math.ceil(maxVal / ceil) * ceil

  // Y-axis grid lines
  const ySteps = 4
  const yBaseline = pad.top + plotH
  ctx.strokeStyle = COLORS.grid
  ctx.lineWidth = 0.5
  ctx.font = '9px "JetBrains Mono"'
  ctx.textAlign = 'right'
  ctx.textBaseline = 'middle'
  ctx.fillStyle = COLORS.text

  for (let i = 0; i <= ySteps; i++) {
    const y = yBaseline - (plotH * i / ySteps)
    const val = (maxVal * i / ySteps)

    ctx.beginPath()
    ctx.moveTo(pad.left, y)
    ctx.lineTo(w - pad.right, y)
    ctx.stroke()

    ctx.fillText('$' + val.toFixed(4), pad.left - 6, y)
  }

  // Daily average reference line
  if (dailyAverage.value > 0) {
    const avgY = yBaseline - (dailyAverage.value / maxVal) * plotH
    ctx.strokeStyle = COLORS.avg
    ctx.lineWidth = 1
    ctx.setLineDash([4, 6])
    ctx.beginPath()
    ctx.moveTo(pad.left, avgY)
    ctx.lineTo(w - pad.right, avgY)
    ctx.stroke()
    ctx.setLineDash([])

    ctx.fillStyle = COLORS.avg
    ctx.textAlign = 'right'
    ctx.font = '9px "JetBrains Mono"'
    ctx.fillText('$' + dailyAverage.value.toFixed(4), pad.left - 6, avgY - 6)
  }

  // Separate actual and predicted entries
  const actuals = entries.filter(e => e.prediction === null && e.cost > 0)
  const predictions = entries.filter(e => e.prediction !== null)

  // X-axis positions
  const total = entries.length
  const xStep = total > 1 ? plotW / (total - 1) : plotW / 2

  function xPos(i) { return pad.left + i * xStep }

  // Draw prediction line first (behind actual)
  if (predictions.length > 0) {
    const predStart = entries.indexOf(predictions[0])
    ctx.strokeStyle = COLORS.predicted
    ctx.lineWidth = 1.5
    ctx.setLineDash([5, 4])
    ctx.beginPath()

    // Bridge from last actual point to first prediction
    if (actuals.length > 0) {
      const lastActIdx = entries.indexOf(actuals[actuals.length - 1])
      const ly = yBaseline - ((actuals[actuals.length - 1].cost || 0) / maxVal) * plotH
      ctx.moveTo(xPos(lastActIdx), ly)
    }

    for (let pi = 0; pi < predictions.length; pi++) {
      const idx = entries.indexOf(predictions[pi])
      const py = yBaseline - ((predictions[pi].prediction || 0) / maxVal) * plotH
      ctx.lineTo(xPos(idx), py)
    }
    ctx.stroke()
    ctx.setLineDash([])

    // Prediction dots
    for (const p of predictions) {
      const idx = entries.indexOf(p)
      const py = yBaseline - ((p.prediction || 0) / maxVal) * plotH
      ctx.fillStyle = '#05080b'
      ctx.strokeStyle = COLORS.predicted
      ctx.lineWidth = 1.5
      ctx.beginPath()
      ctx.arc(xPos(idx), py, 3.5, 0, Math.PI * 2)
      ctx.fill()
      ctx.stroke()
    }
  }

  // Draw actual line
  if (actuals.length > 0) {
    ctx.strokeStyle = COLORS.actual
    ctx.lineWidth = 1.5
    ctx.setLineDash([])
    ctx.beginPath()
    for (let i = 0; i < actuals.length; i++) {
      const idx = entries.indexOf(actuals[i])
      const y = yBaseline - ((actuals[i].cost || 0) / maxVal) * plotH
      if (i === 0) ctx.moveTo(xPos(idx), y)
      else ctx.lineTo(xPos(idx), y)
    }
    ctx.stroke()

    // Actual dots
    for (const a of actuals) {
      const idx = entries.indexOf(a)
      const y = yBaseline - ((a.cost || 0) / maxVal) * plotH
      ctx.fillStyle = COLORS.actual
      ctx.beginPath()
      ctx.arc(xPos(idx), y, 3.5, 0, Math.PI * 2)
      ctx.fill()
    }
  }

  // X-axis date labels (show every Nth to avoid clutter)
  const labelMod = Math.max(1, Math.floor(entries.length / 8))
  ctx.textAlign = 'center'
  ctx.textBaseline = 'top'
  ctx.font = '9px "JetBrains Mono"'
  ctx.fillStyle = COLORS.text
  for (let i = 0; i < entries.length; i++) {
    if (i % labelMod !== 0 && i !== entries.length - 1) continue
    const label = formatDateLabel(entries[i].date)
    // Truncate overlapping
    ctx.fillText(label, xPos(i), yBaseline + 6)
  }
}

watch(() => sessionsStore.dailyCosts, () => nextTick(draw), { deep: true })
onMounted(() => nextTick(draw))

// Redraw on resize
if (typeof window !== 'undefined') {
  window.addEventListener('resize', draw)
}
</script>

<style scoped>
.cost-chart { padding: 18px; margin-bottom: 28px; }
.chart-header {
  display: flex;
  align-items: center;
  gap: 20px;
  margin-top: 10px;
  margin-bottom: 4px;
}
.chart-stat {
  display: flex;
  flex-direction: column;
}
.stat-label {
  font-family: var(--font-mono);
  font-size: 10px;
  letter-spacing: 0.08em;
  color: var(--text-dim);
  text-transform: uppercase;
}
.stat-val {
  font-family: var(--font-display);
  font-size: 18px;
  font-weight: 600;
  color: var(--text-hi);
}
.chart-stat.projected .stat-val {
  color: #ffb020;
}
.chart-legend {
  margin-left: auto;
  display: flex;
  gap: 14px;
}
.legend-item {
  font-family: var(--font-mono);
  font-size: 9px;
  color: var(--text-dim);
  display: flex;
  align-items: center;
  gap: 4px;
}
.legend-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  flex-shrink: 0;
}
.legend-dot.actual { background: #1ec8ff; }
.legend-dot.predicted { background: #ffb020; }
.legend-dot.avg { background: #4ade80; }
.canvas-wrap {
  position: relative;
  width: 100%;
  min-height: 180px;
}
canvas {
  display: block;
  width: 100%;
  height: auto;
}
</style>
