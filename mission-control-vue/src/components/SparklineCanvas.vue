<template>
  <div class="sparkline-card panel">
    <canvas ref="canvas" class="sparkline-canvas"></canvas>
    <div class="sparkline-peak" v-if="peakLabel">{{ peakLabel }}</div>
  </div>
</template>

<script setup>
import { ref, watch, onMounted } from 'vue'
import { useProfilesStore } from '../stores/profiles.js'
import { useSessionsStore } from '../stores/sessions.js'

const prof = useProfilesStore()
const sess = useSessionsStore()
const canvas = ref(null)
const peakLabel = ref('')
let lastKey = ''

function draw() {
  const c = canvas.value
  if (!c) return
  const ctx = c.getContext('2d')
  const w = c.parentElement?.offsetWidth || 320
  const h = 80

  if (c.width !== w) c.width = w
  if (c.height !== h) c.height = h

  let points = [0, 0, 0, 0, 0, 0, 0]
  const profiles = prof.data || []
  for (const p of profiles) {
    const daily = p.state_db_stats?.daily_sessions_7d || []
    for (let i = 0; i < Math.min(daily.length, 7); i++) points[i] += daily[i] || 0
  }
  let total = points.reduce((a, b) => a + b, 0)
  if (total === 0 && sess.sessions?.length > 0) {
    const now = Date.now() / 1000
    const buckets = [0, 0, 0, 0, 0, 0, 0]
    for (const s of sess.sessions) {
      if (!s.started_at) continue
      const daysAgo = Math.floor((now - s.started_at) / 86400)
      if (daysAgo >= 0 && daysAgo < 7) buckets[6 - daysAgo]++
    }
    points = buckets
  }

  const newKey = points.join(',') + '|w' + w
  if (newKey === lastKey) return
  lastKey = newKey

  const maxVal = Math.max(...points, 1)
  const padding = 8
  const drawH = h - padding * 2
  const stepX = (w - padding * 2) / (points.length - 1)
  const minRise = 10

  ctx.clearRect(0, 0, w, h)

  // Gradient fill
  const grad = ctx.createLinearGradient(0, 0, 0, h)
  grad.addColorStop(0, 'rgba(255,59,31,0.5)')
  grad.addColorStop(1, 'rgba(255,176,32,0.12)')

  ctx.beginPath()
  ctx.moveTo(padding, h - padding)
  for (let i = 0; i < points.length; i++) {
    const x = padding + i * stepX
    const ratio = points[i] / maxVal
    const y = h - padding - minRise + ratio * (minRise - drawH)
    ctx.lineTo(x, y)
  }
  ctx.lineTo(padding + (points.length - 1) * stepX, h - padding)
  ctx.closePath()
  ctx.fillStyle = grad
  ctx.fill()

  // Line
  ctx.beginPath()
  ctx.strokeStyle = '#ff3b1f'
  ctx.lineWidth = 2
  for (let i = 0; i < points.length; i++) {
    const x = padding + i * stepX
    const ratio = points[i] / maxVal
    const y = h - padding - minRise + ratio * (minRise - drawH)
    if (i === 0) ctx.moveTo(x, y)
    else ctx.lineTo(x, y)
  }
  ctx.stroke()

  // Glow dot at rightmost
  const lastX = padding + (points.length - 1) * stepX
  const lastRatio = points[points.length - 1] / maxVal
  const lastY = h - padding - minRise + lastRatio * (minRise - drawH)
  ctx.beginPath()
  ctx.arc(lastX, lastY, 3.5, 0, Math.PI * 2)
  ctx.fillStyle = '#ff6347'
  ctx.fill()
  ctx.beginPath()
  ctx.arc(lastX, lastY, 7, 0, Math.PI * 2)
  ctx.fillStyle = 'rgba(255,59,31,0.15)'
  ctx.fill()

  // Peak label
  const days = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat']
  const peakIdx = points.indexOf(maxVal)
  const todayIdx = new Date().getDay()
  const peakDay = days[(todayIdx - (6 - peakIdx) + 7) % 7]
  peakLabel.value = 'MOST ACTIVE: ' + peakDay + ' (' + maxVal + ' sessions)'
}

onMounted(() => { draw() })
watch([() => prof.data, () => sess.sessions], () => draw(), { deep: false })
</script>

<style scoped>
.sparkline-card { padding: 18px; }
.sparkline-canvas { width: 100%; height: 80px; display: block; }
.sparkline-peak {
  font-family: var(--font-mono);
  font-size: 9px;
  color: var(--text-dim);
  letter-spacing: 0.1em;
  text-transform: uppercase;
  margin-top: 6px;
}
</style>
