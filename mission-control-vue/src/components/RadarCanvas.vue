<template>
  <div class="radar-card panel">
    <div class="radar-header">
      <div class="eyebrow">RADAR</div>
      <div class="radar-stats">
        <span class="radar-stat"><span class="dot" style="background:var(--red)"></span> Active</span>
        <span class="radar-stat"><span class="dot" style="background:var(--cyan)"></span> Dormant</span>
      </div>
    </div>
    <canvas ref="canvas" width="200" height="200" class="radar-canvas"></canvas>
    <div class="radar-sweep-text">{{ sweepLabel }}</div>
  </div>
</template>

<script setup>
import { ref, onMounted, onUnmounted, computed } from 'vue'
import { useSnapshotStore } from '../stores/snapshotStore.js'

const snap = useSnapshotStore()
const canvas = ref(null)
const sweepLabel = ref('')
let rafId = null
let sweepAngle = 0
let lastDataKey = ''

const labels = computed(() => {
  const d = snap.data
  if (!d) return []
  const profiles = d.profiles || []
  const kanban = d.kanban?.boards || {}
  const gw = d.gateway || {}
  const items = []
  if (gw.gateway_state) items.push(gw.gateway_state.toUpperCase())
  items.push((profiles.length || 0) + ' PROFILES')
  let blocked = 0
  for (const b of Object.values(kanban)) blocked += (b.columns?.blocked || []).length
  if (blocked) items.push(blocked + ' BLOCKED')
  const errCount = (d.errors || []).length
  if (errCount) items.push(errCount + ' ERRORS')
  return items
})

function draw() {
  const c = canvas.value
  if (!c) return
  const ctx = c.getContext('2d')
  const w = c.width, h = c.height
  const cx = w / 2, cy = h / 2, r = 75

  ctx.clearRect(0, 0, w, h)

  // Hexagon
  ctx.strokeStyle = 'rgba(255,255,255,0.12)'
  ctx.lineWidth = 1
  for (let ring = 1; ring <= 3; ring++) {
    ctx.beginPath()
    for (let i = 0; i < 6; i++) {
      const angle = (Math.PI / 3) * i - Math.PI / 2
      const x = cx + (r * ring / 3) * Math.cos(angle)
      const y = cy + (r * ring / 3) * Math.sin(angle)
      if (i === 0) ctx.moveTo(x, y)
      else ctx.lineTo(x, y)
    }
    ctx.closePath()
    ctx.stroke()
  }

  // Spokes
  for (let i = 0; i < 6; i++) {
    const angle = (Math.PI / 3) * i - Math.PI / 2
    ctx.beginPath()
    ctx.moveTo(cx, cy)
    ctx.lineTo(cx + r * Math.cos(angle), cy + r * Math.sin(angle))
    ctx.stroke()
  }

  // Profile dots
  const profiles = snap.data?.profiles || []
  let totalSessions = 0
  for (const p of profiles) {
    totalSessions += p.state_db_stats?.session_count || 0
  }
  totalSessions = Math.max(totalSessions, 1)
  for (let i = 0; i < profiles.length; i++) {
    const share = (profiles[i].state_db_stats?.session_count || 0) / totalSessions
    const angle = (i / profiles.length) * Math.PI * 2 - Math.PI / 2
    const dist = r * 0.3 + share * r * 0.65
    const px = cx + dist * Math.cos(angle)
    const py = cy + dist * Math.sin(angle)
    ctx.beginPath()
    ctx.arc(px, py, 3, 0, Math.PI * 2)
    ctx.fillStyle = share > 0.3 ? '#ff3b1f' : share > 0.1 ? '#ffb020' : '#1ec8ff'
    ctx.fill()
    ctx.fillStyle = 'rgba(255,255,255,0.55)'
    ctx.font = '9px "JetBrains Mono"'
    ctx.textAlign = 'center'
    ctx.fillText((profiles[i].name || '').slice(0, 4), px, py - 9)
  }

  // Sweep
  sweepAngle = (sweepAngle + 0.006) % (Math.PI * 2)
  ctx.save()
  ctx.globalAlpha = 0.15
  ctx.beginPath()
  ctx.moveTo(cx, cy)
  ctx.arc(cx, cy, r, sweepAngle, sweepAngle + 0.6)
  ctx.closePath()
  ctx.fillStyle = '#ff3b1f'
  ctx.fill()
  ctx.restore()
}

function animate() {
  const d = snap.data
  const key = d ? JSON.stringify([d.profiles?.length, d.errors?.length]) : ''
  if (key !== lastDataKey) {
    lastDataKey = key
    sweepLabel.value = labels.value[0] || 'SCANNING'
  }
  draw()
  // Cycle label every ~2.6s (roughly 43 frames at 60fps)
  const lblIdx = Math.floor((sweepAngle / (Math.PI * 2)) * labels.value.length) % labels.value.length
  sweepLabel.value = labels.value[lblIdx] || 'SCANNING'
  rafId = requestAnimationFrame(animate)
}

onMounted(() => { rafId = requestAnimationFrame(animate) })
onUnmounted(() => { if (rafId) cancelAnimationFrame(rafId) })
</script>

<style scoped>
.radar-card {
  padding: 18px;
  display: flex;
  flex-direction: column;
  align-items: center;
}
.radar-header {
  width: 100%;
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
}
.radar-stats {
  display: flex;
  gap: 14px;
  font-family: var(--font-mono);
  font-size: 9px;
  color: var(--text-dim);
  letter-spacing: 0.1em;
}
.radar-stat { display: flex; align-items: center; gap: 5px; }
.dot { width: 5px; height: 5px; border-radius: 50%; flex-shrink: 0; box-shadow: 0 0 4px currentColor; }
.radar-canvas {
  width: 200px;
  height: 200px;
}
.radar-sweep-text {
  font-family: var(--font-mono);
  font-size: 10px;
  color: var(--red);
  letter-spacing: 0.22em;
  margin-top: 4px;
  text-transform: uppercase;
}
</style>
