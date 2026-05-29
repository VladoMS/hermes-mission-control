<template>
  <div ref="wrapRef" class="sparkline-wrap">
    <div class="sparkline-canvas">
      <Line v-if="ready" :key="chartKey" :data="chartData" :options="chartOptions" />
    </div>
    <div class="sparkline-peak" v-if="peakLabel">{{ peakLabel }}</div>
  </div>
</template>

<script setup>
import { ref, computed, watch, onMounted, onUnmounted } from 'vue'
import { Line } from 'vue-chartjs'
import {
  Chart as ChartJS,
  LineElement,
  PointElement,
  Filler,
  CategoryScale,
  LinearScale,
  Tooltip,
} from 'chart.js'
import { useProfilesStore } from '../stores/profiles.js'
import { useSessionsStore } from '../stores/sessions.js'

ChartJS.register(LineElement, PointElement, Filler, CategoryScale, LinearScale, Tooltip)

const prof = useProfilesStore()
const sess = useSessionsStore()
const wrapRef = ref(null)
const ready = ref(false)
const peakLabel = ref('')
const chartKey = ref(0)

const days = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat']
const todayIdx = new Date().getDay()

function dayLabels(points) {
  return points.map((_, i) => {
    const idx = (todayIdx - (6 - i) + 7) % 7
    return days[idx]
  })
}

const points = computed(() => {
  const profiles = prof.data || []
  let pts = [0, 0, 0, 0, 0, 0, 0]
  for (const p of profiles) {
    const daily = p.state_db_stats?.daily_sessions_7d || []
    for (let i = 0; i < Math.min(daily.length, 7); i++) pts[i] += daily[i] || 0
  }

  const total = pts.reduce((a, b) => a + b, 0)
  if (total === 0 && sess.sessions?.length > 0) {
    const now = Date.now() / 1000
    pts = [0, 0, 0, 0, 0, 0, 0]
    for (const s of sess.sessions) {
      if (!s.started_at) continue
      const daysAgo = Math.floor((now - s.started_at) / 86400)
      if (daysAgo >= 0 && daysAgo < 7) pts[6 - daysAgo]++
    }
  }
  return pts
})

const chartData = computed(() => {
  const pts = points.value
  const max = Math.max(...pts, 1)
  const peakIdx = pts.indexOf(max)
  peakLabel.value = 'MOST ACTIVE: ' + days[(todayIdx - (6 - peakIdx) + 7) % 7] + ' (' + max + ' sessions)'

  return {
    labels: dayLabels(pts),
    datasets: [{
      data: pts,
      borderColor: '#ff3b1f',
      borderWidth: 2,
      pointRadius: pts.map((_, i) => i === pts.length - 1 ? 4 : 0),
      pointBackgroundColor: '#ff6347',
      pointBorderColor: '#ff6347',
      pointHoverRadius: 5,
      fill: true,
      backgroundColor: (ctx) => {
        const canvas = ctx.chart.ctx
        const grad = canvas.createLinearGradient(0, 0, 0, 80)
        grad.addColorStop(0, 'rgba(255, 59, 31, 0.45)')
        grad.addColorStop(1, 'rgba(255, 176, 32, 0.08)')
        return grad
      },
      tension: 0.35,
    }],
  }
})

const chartOptions = {
  responsive: true,
  maintainAspectRatio: false,
  animation: { duration: 300 },
  interaction: {
    intersect: false,
    mode: 'index',
  },
  plugins: {
    tooltip: {
      backgroundColor: '#111923',
      titleColor: '#e8edf3',
      bodyColor: '#b6c0cb',
      borderColor: 'rgba(255,255,255,0.1)',
      borderWidth: 1,
      titleFont: { family: "'JetBrains Mono'", size: 10, weight: '600' },
      bodyFont: { family: "'JetBrains Mono'", size: 10 },
      cornerRadius: 0,
      displayColors: false,
      callbacks: {
        title: (items) => items[0]?.label,
        label: (item) => item.raw + ' sessions',
      },
    },
    legend: { display: false },
  },
  scales: {
    x: {
      display: true,
      grid: { display: false },
      ticks: {
        color: '#6b7585',
        font: { family: "'JetBrains Mono'", size: 9 },
        maxTicksLimit: 7,
      },
      border: { display: false },
    },
    y: {
      display: true,
      position: 'right',
      grid: {
        color: 'rgba(255,255,255,0.04)',
        drawTicks: false,
      },
      ticks: {
        color: '#404a58',
        font: { family: "'JetBrains Mono'", size: 9 },
        maxTicksLimit: 3,
        callback: (v) => v === 0 ? '' : v,
      },
      border: { display: false },
      beginAtZero: true,
    },
  },
}

// Recreate chart on container resize (key change → full remount)
let ro = null

onMounted(() => {
  ready.value = true
  if (wrapRef.value) {
    ro = new ResizeObserver(() => {
      chartKey.value++
    })
    ro.observe(wrapRef.value)
  }
})

onUnmounted(() => {
  if (ro) {
    ro.disconnect()
    ro = null
  }
})
</script>

<style scoped>
.sparkline-wrap {
  width: 100%;
}
.sparkline-canvas {
  width: 100%;
  height: 80px;
}
.sparkline-peak {
  font-family: var(--font-mono);
  font-size: 9px;
  color: var(--text-dim);
  letter-spacing: 0.1em;
  text-transform: uppercase;
  margin-top: 6px;
}
</style>
