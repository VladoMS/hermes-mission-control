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
        <span v-for="k in keyList" :key="k.key_name" class="legend-item">
          <span class="legend-dot" :style="{ background: k.color }"></span>
          {{ k.key_name }}
          <span class="key-usage">{{ fmtCost(k.usage) }}</span>
        </span>
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
const allDays = computed(() => dailyCosts.value?.days || [])
const dailyAverage = computed(() => dailyCosts.value?.daily_average || 0)
const todaySoFar = computed(() => dailyCosts.value?.today_so_far || 0)
const monthlyProjection = computed(() => dailyCosts.value?.monthly_projection || 0)

const KEY_COLORS = ['#1ec8ff', '#d946ef', '#4ade80', '#ffb020', '#ff3b1f', '#22d3ee']

const byKey = computed(() => dailyCosts.value?.by_key || {})
const keyNames = computed(() => Object.keys(byKey.value))

const keyList = computed(() =>
  keyNames.value.map((kn, i) => {
    const kd = byKey.value[kn]
    const totalUsage = (kd.days || []).reduce((s, d) => s + (d.cost || 0) + (d.prediction || 0), 0)
    return {
      key_name: kn,
      color: KEY_COLORS[i % KEY_COLORS.length],
      usage: totalUsage,
      daily_average: kd.daily_average || 0,
    }
  })
)

function getKeyColor(keyName) {
  const idx = keyNames.value.indexOf(keyName)
  return KEY_COLORS[idx >= 0 ? idx % KEY_COLORS.length : 0]
}

function today() {
  const d = new Date()
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
}

const windowStart = computed(() => {
  const d = new Date()
  d.setDate(d.getDate() - 30)
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
})

const windowEnd = computed(() => {
  const d = new Date()
  d.setDate(d.getDate() + 30)
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
})

const groupSize = 3

const days = computed(() => {
  const filtered = allDays.value.filter(d => d.date >= windowStart.value && d.date <= windowEnd.value)
  const buckets = []
  for (let i = 0; i < filtered.length; i += groupSize) {
    const group = filtered.slice(i, i + groupSize)
    buckets.push({
      date: group[0].date,
      cost: group.reduce((s, e) => s + (e.cost || 0), 0),
      prediction: group.some(e => e.prediction !== null)
        ? group.reduce((s, e) => s + (e.prediction || 0), 0)
        : null,
    })
  }
  return buckets
})

const keyBuckets = computed(() => {
  const result = {}
  for (const kn of keyNames.value) {
    const kd = byKey.value[kn]
    const filtered = (kd.days || []).filter(d => d.date >= windowStart.value && d.date <= windowEnd.value)
    const buckets = []
    for (let i = 0; i < filtered.length; i += groupSize) {
      const group = filtered.slice(i, i + groupSize)
      buckets.push({
        date: group[0].date,
        cost: group.reduce((s, e) => s + (e.cost || 0), 0),
        prediction: group.some(e => e.prediction !== null)
          ? group.reduce((s, e) => s + (e.prediction || 0), 0)
          : null,
      })
    }
    result[kn] = buckets
  }
  return result
})

function fmtCost(n) {
  if (!n && n !== 0) return '--'
  return '$' + Number(n).toFixed(2)
}

// ── Canvas drawing ─────────────────────────────────────────

const COLORS = {
  grid: '#0c121a',
  text: '#6b7585',
  textHi: '#b6c0cb',
}

function formatDateLabel(dateStr) {
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

  // Compute max value across ALL keys
  let maxVal = 0
  for (const e of entries) {
    const v = Math.max(e.cost || 0, e.prediction || 0)
    if (v > maxVal) maxVal = v
  }
  if (dailyAverage.value > maxVal) maxVal = dailyAverage.value
  if (maxVal === 0) maxVal = 0.01
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
    ctx.fillText('$' + val.toFixed(2), pad.left - 6, y)
  }

  // X-axis positions
  const total = entries.length
  const xStep = total > 1 ? plotW / (total - 1) : plotW / 2
  function xPos(i) { return pad.left + i * xStep }

  // Fallback: if no per-key data, draw combined totals
  if (keyNames.value.length === 0) {
    const actuals = entries.filter(e => e.prediction === null && e.cost > 0)
    const predictions = entries.filter(e => e.prediction !== null)

    // Avg ref line (dotted)
    if (dailyAverage.value > 0 && maxVal > 0) {
      const avgY = yBaseline - (dailyAverage.value / maxVal) * plotH
      ctx.strokeStyle = '#4ade80'
      ctx.lineWidth = 1
      ctx.setLineDash([2, 4])
      ctx.beginPath()
      ctx.moveTo(pad.left, avgY)
      ctx.lineTo(w - pad.right, avgY)
      ctx.stroke()
      ctx.setLineDash([])
    }

    // Prediction line (dashed)
    if (predictions.length > 0) {
      ctx.strokeStyle = '#ffb020'
      ctx.lineWidth = 1.5
      ctx.setLineDash([5, 4])
      ctx.beginPath()
      if (actuals.length > 0) {
        const lastIdx = entries.indexOf(actuals[actuals.length - 1])
        const ly = yBaseline - ((actuals[actuals.length - 1].cost || 0) / maxVal) * plotH
        ctx.moveTo(xPos(lastIdx), ly)
      }
      for (const p of predictions) {
        const idx = entries.indexOf(p)
        const py = yBaseline - ((p.prediction || 0) / maxVal) * plotH
        ctx.lineTo(xPos(idx), py)
      }
      ctx.stroke()
      ctx.setLineDash([])
    }

    // Actual line (solid)
    if (actuals.length > 0) {
      ctx.strokeStyle = '#1ec8ff'
      ctx.lineWidth = 1.5
      ctx.beginPath()
      for (let i = 0; i < actuals.length; i++) {
        const idx = entries.indexOf(actuals[i])
        const y = yBaseline - ((actuals[i].cost || 0) / maxVal) * plotH
        if (i === 0) ctx.moveTo(xPos(idx), y)
        else ctx.lineTo(xPos(idx), y)
      }
      ctx.stroke()
      for (const a of actuals) {
        const idx = entries.indexOf(a)
        const y = yBaseline - ((a.cost || 0) / maxVal) * plotH
        ctx.fillStyle = '#1ec8ff'
        ctx.beginPath()
        ctx.arc(xPos(idx), y, 3.5, 0, Math.PI * 2)
        ctx.fill()
      }
    }
  } else {
    // Per-key lines
    for (const kn of keyNames.value) {
      const color = getKeyColor(kn)
      const kBuckets = keyBuckets.value[kn] || []
      if (kBuckets.length === 0) continue

      const actuals = kBuckets.filter(e => e.prediction === null && e.cost > 0)
      const predictions = kBuckets.filter(e => e.prediction !== null)
      const kAvg = byKey.value[kn]?.daily_average || 0

      // ── Average reference line (dotted) ──
      if (kAvg > 0 && maxVal > 0) {
        const avgY = yBaseline - (kAvg / maxVal) * plotH
        ctx.strokeStyle = color
        ctx.globalAlpha = 0.4
        ctx.lineWidth = 1
        ctx.setLineDash([2, 4])
        ctx.beginPath()
        ctx.moveTo(pad.left, avgY)
        ctx.lineTo(w - pad.right, avgY)
        ctx.stroke()
        ctx.setLineDash([])
        ctx.globalAlpha = 1.0
      }

      // ── Prediction line (dashed) ──
      if (predictions.length > 0) {
        const predStart = entries.indexOf(predictions[0])
        ctx.strokeStyle = color
        ctx.lineWidth = 1.5
        ctx.setLineDash([5, 4])
        ctx.beginPath()

        // Bridge from last actual point
        if (actuals.length > 0) {
          const lastAct = actuals[actuals.length - 1]
          const lastActEntry = entries.find(e => e.date === lastAct.date)
          const lastActIdx = lastActEntry ? entries.indexOf(lastActEntry) : predStart
          const ly = yBaseline - ((lastAct.cost || 0) / maxVal) * plotH
          ctx.moveTo(xPos(lastActIdx), ly)
        }

        for (let pi = 0; pi < predictions.length; pi++) {
          const p = predictions[pi]
          const entry = entries.find(e => e.date === p.date)
          if (!entry) continue
          const idx = entries.indexOf(entry)
          const py = yBaseline - ((p.prediction || 0) / maxVal) * plotH
          ctx.lineTo(xPos(idx), py)
        }
        ctx.stroke()
        ctx.setLineDash([])
      }

      // ── Actual line (solid) ──
      if (actuals.length > 0) {
        ctx.strokeStyle = color
        ctx.lineWidth = 1.5
        ctx.setLineDash([])
        ctx.beginPath()
        for (let i = 0; i < actuals.length; i++) {
          const a = actuals[i]
          const entry = entries.find(e => e.date === a.date)
          if (!entry) continue
          const idx = entries.indexOf(entry)
          const y = yBaseline - ((a.cost || 0) / maxVal) * plotH
          if (i === 0) ctx.moveTo(xPos(idx), y)
          else ctx.lineTo(xPos(idx), y)
        }
        ctx.stroke()

        // Actual dots
        for (const a of actuals) {
          const entry = entries.find(e => e.date === a.date)
          if (!entry) continue
          const idx = entries.indexOf(entry)
          const y = yBaseline - ((a.cost || 0) / maxVal) * plotH
          ctx.fillStyle = color
          ctx.beginPath()
          ctx.arc(xPos(idx), y, 3.5, 0, Math.PI * 2)
          ctx.fill()
        }
      }
    }
  }

  // X-axis date labels
  const labelMod = Math.max(1, Math.floor(entries.length / 8))
  ctx.textAlign = 'center'
  ctx.textBaseline = 'top'
  ctx.font = '9px "JetBrains Mono"'
  ctx.fillStyle = COLORS.text
  for (let i = 0; i < entries.length; i++) {
    if (i % labelMod !== 0 && i !== entries.length - 1) continue
    ctx.fillText(formatDateLabel(entries[i].date), xPos(i), yBaseline + 6)
  }
}

watch(() => sessionsStore.dailyCosts, () => nextTick(draw), { deep: true })
onMounted(() => nextTick(draw))

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
.key-usage {
  color: var(--text-hi);
  font-weight: 600;
}
.legend-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  flex-shrink: 0;
}
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
