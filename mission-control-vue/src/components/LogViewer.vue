<template>
  <Teleport to="body">
    <div v-if="visible" class="log-overlay" @click.self="$emit('close')">
      <div class="log-viewer panel">
        <!-- Header -->
        <div class="log-header">
          <div class="log-title-row">
            <div class="eyebrow">LOGS</div>
            <span class="log-app mono">{{ appName }}</span>
            <span class="log-container mono" v-if="containerName">{{ containerName }}</span>
          </div>
          <div class="log-actions">
            <button class="chip" :class="{ amber: paused }" @click="togglePause">
              {{ paused ? 'PAUSED' : 'LIVE' }}
            </button>
            <button class="chip" @click="clearLogs">CLEAR</button>
            <button class="modal-close" @click="close">✕</button>
          </div>
        </div>

        <!-- Log output -->
        <div ref="logContainer" class="log-output" @click="handleLineClick">
          <div v-if="lines.length === 0 && connecting" class="log-wait mono">Connecting to {{ containerName || (appName + '.web.1') }}...</div>
          <div
            v-for="(entry, i) in lines"
            :key="i"
            class="log-line"
            :class="entry.css"
            :data-line="i"
          >
            <span class="ln-mono">{{ entry.text }}</span>
          </div>
        </div>

        <!-- Line count -->
        <div class="log-footer mono">{{ lines.length }} lines{{ paused ? ' (paused)' : '' }}</div>
      </div>
    </div>
  </Teleport>
</template>

<script setup>
import { ref, watch, onUnmounted, nextTick, computed } from 'vue'
import { useToast } from '../composables/useToast.js'

const props = defineProps({
  visible: { type: Boolean, default: false },
  appName: { type: String, default: '' },
  serverName: { type: String, default: 'prod' },
  containerName: { type: String, default: '' },
})
const emit = defineEmits(['close'])

const lines = ref([])
const paused = ref(false)
const connecting = ref(false)
const logContainer = ref(null)
const { toast } = useToast()

let source = null
let pending = []

const activeContainer = computed(() => props.containerName || props.appName + '.web.1')

function lineClass(line) {
  const lower = line.toLowerCase()
  if (/error|fail|fatal|exception|traceback/i.test(lower)) return 'error'
  if (/warn/i.test(lower)) return 'warn'
  if (/info/i.test(lower)) return 'info'
  return ''
}

function togglePause() {
  paused.value = !paused.value
  if (!paused.value && pending.length) {
    lines.value.push(...pending)
    pending = []
    if (lines.value.length > 2000) lines.value = lines.value.slice(-2000)
    scrollToBottom()
  }
}

function clearLogs() {
  lines.value = []
  pending = []
}

function scrollToBottom() {
  nextTick(() => {
    const el = logContainer.value
    if (el) el.scrollTop = el.scrollHeight
  })
}

async function handleLineClick(e) {
  const lineEl = e.target.closest('.log-line')
  if (!lineEl) return
  const text = lineEl.textContent || ''
  try {
    await navigator.clipboard.writeText(text)
    toast('Copied to clipboard')
  } catch {
    // Fallback for non-HTTPS or older browsers
    const ta = document.createElement('textarea')
    ta.value = text
    ta.style.position = 'fixed'
    ta.style.opacity = '0'
    document.body.appendChild(ta)
    ta.select()
    document.execCommand('copy')
    document.body.removeChild(ta)
    toast('Copied to clipboard')
  }
}

function connect() {
  if (!props.visible || !props.appName) return
  closeSource()
  connecting.value = true
  lines.value = []
  pending = []

  const url = `/api/dokku/logs?server=${encodeURIComponent(props.serverName)}&app=${encodeURIComponent(props.appName)}&tail=300`
  source = new EventSource(url)

  source.onopen = () => { connecting.value = false }
  source.onmessage = (event) => {
    const data = event.data
    if (data == null || data === '') return
    const entry = {
      text: data,
      css: lineClass(data),
    }
    if (paused.value) {
      pending.push(entry)
      if (pending.length > 1000) pending.shift()
    } else {
      lines.value.push(entry)
      if (lines.value.length > 2000) lines.value = lines.value.slice(-2000)
      scrollToBottom()
    }
  }
  source.onerror = () => {
    closeSource()
    if (props.visible) {
      lines.value.push({ text: '--- CONNECTION LOST ---', css: 'error' })
    }
  }
}

function closeSource() {
  if (source) { source.close(); source = null }
  connecting.value = false
}

function close() {
  closeSource()
  emit('close')
}

watch(() => props.visible, (v) => {
  if (v) connect()
  else closeSource()
})

onUnmounted(() => closeSource())
</script>

<style scoped>
.log-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.75);
  z-index: 100;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 32px;
}
.log-viewer {
  width: 100%;
  max-width: 1100px;
  height: 85vh;
  max-height: 85vh;
  display: flex;
  flex-direction: column;
  background: var(--bg-void);
  border: 1px solid var(--line-strong);
  padding: 0;
}
.log-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  padding: 14px 18px;
  border-bottom: 1px solid var(--line);
  flex-shrink: 0;
}
.log-title-row {
  display: flex;
  flex-direction: column;
  gap: 3px;
}
.log-app {
  font-size: 13px;
  color: var(--text-hi);
  font-weight: 600;
  letter-spacing: 0.04em;
}
.log-container {
  font-size: 10px;
  color: var(--text-faint);
  letter-spacing: 0.08em;
}
.log-actions {
  display: flex;
  align-items: center;
  gap: 6px;
}
.log-actions .chip { cursor: pointer; font-size: 9px; }
.modal-close {
  background: transparent;
  border: 1px solid var(--line);
  color: var(--text-dim);
  width: 28px;
  height: 28px;
  cursor: pointer;
  font-size: 14px;
  display: flex;
  align-items: center;
  justify-content: center;
}
.modal-close:hover { color: var(--text-hi); border-color: var(--line-strong); }

.log-output {
  flex: 1;
  overflow-y: auto;
  padding: 14px 18px;
  font-family: var(--font-mono);
  font-size: 11px;
  line-height: 1.6;
  background: var(--bg-deep);
}
.log-wait {
  color: var(--text-faint);
  padding: 40px;
  text-align: center;
  font-size: 11px;
}
.log-line {
  white-space: pre-wrap;
  word-break: break-all;
  padding: 2px 6px;
  color: var(--text-dim);
  cursor: pointer;
  border-radius: 2px;
  transition: background 0.1s;
}
.log-line:hover {
  background: rgba(255, 255, 255, 0.03);
}
.log-line.error { color: var(--red); }
.log-line.warn { color: var(--amber-soft); }
.log-line.info { color: var(--cyan-soft); }

.log-footer {
  padding: 8px 18px;
  font-size: 9px;
  color: var(--text-faint);
  border-top: 1px solid var(--line-dim);
  flex-shrink: 0;
}

@media (max-width: 720px) {
  .log-overlay { padding: 0; }
  .log-viewer {
    max-width: 100%;
    height: 100vh;
    max-height: 100vh;
  }
}
</style>
