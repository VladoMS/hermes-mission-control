<template>
  <div class="glance-strip panel" :class="{ collapsed: isCollapsed }">
    <!-- Collapsed summary bar -->
    <div v-if="isCollapsed" class="glance-summary" @click="isCollapsed = false">
      <span class="glance-summary-time">{{ fmtTime('Europe/Sofia') }} SOFIA</span>
      <span class="glance-summary-weather" v-if="weather.temperature != null">{{ weather.temperature }}°C {{ weather.weather_label }}</span>
      <span class="glance-summary-hint mono">EXPAND</span>
    </div>

    <!-- Expanded content -->
    <template v-else>
    <!-- SECTION: World Clock -->
    <div class="glance-section clock-section">
      <div class="section-eyebrow">◆ WORLD CLOCK</div>
      <div class="clock-grid">
        <div
          v-for="tz in timezones"
          :key="tz[1]"
          class="clock-cell"
        >
          <div class="clock-label">{{ tz[1] }}</div>
          <div class="clock-time">{{ fmtTime(tz[0]) }}</div>
        </div>
      </div>
    </div>

    <div class="glance-divider"></div>

    <!-- SECTION: Weather -->
    <div class="glance-section weather-section">
      <div class="section-eyebrow">◆ WEATHER</div>
      <div v-if="weatherError" class="weather-error">{{ weatherError }}</div>
      <div v-else class="weather-main">
        <div class="weather-temp">
          {{ weather.temperature != null ? weather.temperature + '°C' : '--' }}
        </div>
        <div class="weather-detail">
          <div class="weather-label">{{ weather.weather_label || 'Loading...' }}</div>
          <div class="weather-location">{{ weather.location }}</div>
        </div>
      </div>
    </div>

    <div class="glance-divider"></div>

    <!-- SECTION: Twitch -->
    <div class="glance-section twitch-section">
      <div class="section-eyebrow">
        ◆ TWITCH
        <span v-if="twitch.live_count > 0" class="live-badge">
          {{ twitch.live_count }} LIVE
        </span>
        <span v-else class="offline-badge">OFFLINE</span>
      </div>
      <div v-if="twitchError" class="twitch-error">{{ twitchError }}</div>
      <div v-else class="twitch-streamers">
        <template v-if="liveChannels.length">
          <a
            v-for="ch in liveChannels"
            :key="ch.login"
            :href="'https://twitch.tv/' + ch.login"
            target="_blank"
            rel="noopener"
            class="streamer-chip live"
            :title="ch.title || ''"
          >
            <span class="streamer-dot live-dot"></span>
            <span class="streamer-name">{{ ch.display_name || ch.login }}</span>
            <span v-if="ch.viewers_count" class="streamer-viewers">{{ fmtViewers(ch.viewers_count) }}</span>
          </a>
        </template>
        <div v-if="liveChannels.length === 0" class="twitch-empty">All channels offline</div>
      </div>
    </div>

    <!-- Collapse button -->
    <button class="glance-collapse-btn" @click="isCollapsed = true" title="Collapse">
      <span class="collapse-arrow">▲</span>
    </button>
    </template>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted } from 'vue'

// --- Reactive state ---
const isCollapsed = ref(true)
const timezones = ref([
  ['Europe/Sofia', 'Sofia'],
  ['UTC', 'UTC'],
  ['Europe/Rome', 'Italy'],
  ['America/Los_Angeles', 'US West'],
  ['America/New_York', 'US East'],
  ['Asia/Singapore', 'Singapore'],
  ['Australia/Sydney', 'Australia'],
])
const weather = ref({})
const weatherError = ref('')
const twitch = ref({ channels: [], live_count: 0 })
const twitchError = ref('')
const nowTick = ref(Date.now())

// --- Computed ---
const liveChannels = computed(() => {
  if (!twitch.value.channels) return []
  return twitch.value.channels.filter(c => c.is_live)
})

// --- Clock tick (every second) ---
let clockTimer = null

function fmtTime(tz) {
  try {
    return new Date(nowTick.value).toLocaleTimeString('en-GB', {
      timeZone: tz,
      hour: '2-digit',
      minute: '2-digit',
      hour12: false,
    })
  } catch {
    return '--:--'
  }
}

// --- Formatting ---
function fmtViewers(n) {
  if (n >= 1000) return (n / 1000).toFixed(1) + 'K'
  return String(n)
}

// --- Data fetching ---
async function fetchGlanceData() {
  try {
    const apiUrl = (typeof window !== 'undefined' ? window.location.origin : '') + '/api/glance-data'
    const res = await fetch(apiUrl)
    if (!res.ok) throw new Error('HTTP ' + res.status)
    const data = await res.json()

    // Timezones from server (refresh if changed)
    if (data.timezones && data.timezones.length) {
      timezones.value = data.timezones
    }

    // Weather
    if (data.weather && !data.weather.error) {
      weather.value = data.weather
      weatherError.value = ''
    } else if (data.weather?.error) {
      weatherError.value = data.weather.error
    }

    // Twitch
    if (data.twitch && !data.twitch.error) {
      twitch.value = data.twitch
      twitchError.value = ''
    } else if (data.twitch?.error) {
      twitchError.value = data.twitch.error
    }
  } catch (e) {
    console.error('[GlanceStrip] fetch failed:', e.message || e)
  }
}

// --- Lifecycle ---
let fetchTimer = null

onMounted(() => {
  clockTimer = setInterval(() => { nowTick.value = Date.now() }, 1000)
  fetchGlanceData()
  fetchTimer = setInterval(fetchGlanceData, 60000) // refresh every 60s
})

onUnmounted(() => {
  clearInterval(clockTimer)
  clearInterval(fetchTimer)
})
</script>

<style scoped>
/* --- Strip layout --- */
.glance-strip {
  display: flex;
  align-items: stretch;
  padding: 14px 18px;
  margin-bottom: 28px;
  gap: 0;
  position: relative;
}
.glance-strip.collapsed {
  padding: 8px 18px;
}
.glance-section {
  flex: 1;
  min-width: 0;
}
.glance-divider {
  width: 1px;
  background: var(--line);
  margin: 0 18px;
  align-self: stretch;
}

/* --- Collapsed summary --- */
.glance-summary {
  display: flex;
  align-items: center;
  gap: 16px;
  width: 100%;
  cursor: pointer;
  font-family: var(--font-mono);
  font-size: 11px;
  color: var(--text-dim);
  letter-spacing: 0.06em;
  user-select: none;
}
.glance-summary:hover { color: var(--text); }
.glance-summary-time { color: var(--cyan); font-weight: 600; }
.glance-summary-weather { color: var(--amber); }
.glance-summary-hint {
  margin-left: auto;
  font-size: 9px;
  color: var(--text-faint);
  letter-spacing: 0.12em;
}

/* --- Collapse button --- */
.glance-collapse-btn {
  position: absolute;
  top: 4px;
  right: 10px;
  background: transparent;
  border: none;
  cursor: pointer;
  padding: 2px 6px;
  opacity: 0.4;
  transition: opacity 0.2s;
}
.glance-collapse-btn:hover { opacity: 1; }
.collapse-arrow {
  font-size: 8px;
  color: var(--text-dim);
}

/* --- Eyebrow --- */
.section-eyebrow {
  font-family: var(--font-mono);
  font-size: 9px;
  letter-spacing: 0.18em;
  color: var(--text-dim);
  text-transform: uppercase;
  margin-bottom: 10px;
  display: flex;
  align-items: center;
  gap: 8px;
}

/* --- World Clock --- */
.clock-section { flex: 1.4; }
.clock-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 3px 14px;
}
.clock-cell {
  display: flex;
  justify-content: space-between;
  align-items: baseline;
}
.clock-label {
  font-family: var(--font-mono);
  font-size: 9px;
  color: var(--text-dim);
  text-transform: uppercase;
}
.clock-time {
  font-family: var(--font-mono);
  font-size: 13px;
  font-weight: 500;
  color: var(--cyan);
  letter-spacing: 0.06em;
}

/* --- Weather --- */
.weather-section { flex: 0.8; }
.weather-main {
  display: flex;
  align-items: baseline;
  gap: 12px;
}
.weather-temp {
  font-family: var(--font-display);
  font-size: 28px;
  font-weight: 700;
  color: var(--text-hi);
  letter-spacing: 0.02em;
  line-height: 1;
}
.weather-detail {
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.weather-label {
  font-family: var(--font-body);
  font-size: 12px;
  color: var(--amber);
  font-weight: 500;
}
.weather-location {
  font-family: var(--font-mono);
  font-size: 9px;
  color: var(--text-dim);
  text-transform: uppercase;
}
.weather-error {
  font-family: var(--font-mono);
  font-size: 11px;
  color: var(--text-dim);
}

/* --- Twitch --- */
.twitch-section { flex: 1.6; }
.live-badge {
  font-family: var(--font-mono);
  font-size: 9px;
  color: var(--red);
  background: color-mix(in srgb, var(--red) 15%, transparent);
  padding: 1px 6px;
  border-radius: 2px;
}
.offline-badge {
  font-family: var(--font-mono);
  font-size: 9px;
  color: var(--text-dim);
}
.twitch-streamers {
  display: flex;
  flex-wrap: wrap;
  gap: 4px 8px;
  max-height: 52px;
  overflow: hidden;
}
.streamer-chip {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  font-family: var(--font-mono);
  font-size: 10px;
  color: var(--text-dim);
  white-space: nowrap;
  text-decoration: none;
  cursor: pointer;
  transition: color 0.15s;
}
.streamer-chip.live {
  color: var(--text-hi);
}
.streamer-chip.live:hover {
  color: var(--cyan);
}
.streamer-dot {
  width: 5px;
  height: 5px;
  border-radius: 50%;
  background: var(--text-dim);
  flex-shrink: 0;
}
.live-dot {
  background: var(--red);
  box-shadow: 0 0 4px var(--red);
  animation: pulse-dot 2s ease-in-out infinite;
}
@keyframes pulse-dot {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.4; }
}
.streamer-name {
  font-weight: 500;
}
.streamer-viewers {
  color: var(--text-dim);
  font-size: 9px;
}
.twitch-empty {
  font-family: var(--font-mono);
  font-size: 10px;
  color: var(--text-faint);
}
.twitch-error {
  font-family: var(--font-mono);
  font-size: 10px;
  color: var(--text-dim);
}

/* --- Responsive --- */
@media (max-width: 900px) {
  .glance-strip { flex-direction: column; gap: 12px; }
  .glance-divider { width: auto; height: 1px; margin: 0; }
  .clock-grid { grid-template-columns: repeat(3, 1fr); }
  .twitch-streamers { max-height: none; }
}
@media (max-width: 480px) {
  .clock-grid { grid-template-columns: repeat(2, 1fr); }
  .weather-temp { font-size: 22px; }
}
</style>
