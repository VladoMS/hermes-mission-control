<template>
  <Teleport to="body">
    <div v-if="visible" class="log-overlay" @click.self="$emit('close')">
      <div class="log-viewer panel">
        <!-- Header -->
        <div class="log-header">
          <div class="eyebrow">LOGS: {{ appName }}</div>
          <div class="log-actions">
            <button class="chip" :class="{ amber: paused }" @click="togglePause">
              {{ paused ? 'PAUSED' : 'LIVE' }}
            </button>
            <button class="modal-close" @click="close">✕</button>
          </div>
        </div>

        <!-- Log output -->
        <div ref="logContainer" class="log-output">
          <div v-if="lines.length === 0 && connecting" class="log-wait mono">Connecting...</div>
          <div v-for="(line, i) in lines" :key="i" class="log-line" :class="lineClass(line)">
            <span class="ln-mono">{{ line }}</span>
          </div>
        </div>
      </div>
    </div>
  </Teleport>
</template>

<script setup>
import { ref, watch, onUnmounted, nextTick } from 'vue'

const props = defineProps({
  visible: { type: Boolean, default: false },
  appName: { type: String, default: '' },
  serverName: { type: String, default: 'prod' },
})
const emit = defineEmits(['close'])

const lines = ref([])
const paused = ref(false)
const connecting = ref(false)
const logContainer = ref(null)

let source = null
let pendingLines = []

function lineClass(line) {
  const lower = line.toLowerCase()
  if (/error|fail|fatal|exception|traceback/i.test(lower)) return 'error'
  if (/warn/i.test(lower)) return 'warn'
  if (/info/i.test(lower)) return 'info'
  return ''
}

function togglePause() {
  paused.value = !paused.value
  if (!paused.value) {
    // Flush pending lines
    if (pendingLines.length) {
      lines.value.push(...pendingLines)
      pendingLines = []
      scrollToBottom()
    }
  }
}

function scrollToBottom() {
  nextTick(() => {
    const el = logContainer.value
    if (el) el.scrollTop = el.scrollHeight
  })
}

function connect() {
  if (!props.visible || !props.appName) return
  closeSource()
  connecting.value = true
  lines.value = []
  pendingLines = []

  const url = `/api/dokku/logs?server=${encodeURIComponent(props.serverName)}&app=${encodeURIComponent(props.appName)}&tail=200`
  source = new EventSource(url)

  source.onopen = () => { connecting.value = false }

  source.onmessage = (event) => {
    const data = event.data
    if (data == null || data === '') return
    if (paused.value) {
      pendingLines.push(data)
      if (pendingLines.length > 500) pendingLines.shift()
    } else {
      lines.value.push(data)
      if (lines.value.length > 1000) lines.value.shift()
      scrollToBottom()
    }
  }

  source.onerror = () => {
    closeSource()
    if (props.visible) {
      lines.value.push('--- CONNECTION LOST ---')
    }
  }
}

function closeSource() {
  if (source) {
    source.close()
    source = null
  }
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
  background: rgba(0, 0, 0, 0.7);
  z-index: 100;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 20px;
}
.log-viewer {
  width: 100%;
  max-width: 900px;
  max-height: 80vh;
  display: flex;
  flex-direction: column;
  background: var(--bg-void);
  border: 1px solid var(--line-strong);
  padding: 0;
}
.log-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 12px 16px;
  border-bottom: 1px solid var(--line);
  flex-shrink: 0;
}
.log-actions {
  display: flex;
  align-items: center;
  gap: 8px;
}
.log-actions .chip { cursor: pointer; }
.modal-close {
  background: transparent;
  border: 1px solid var(--line);
  color: var(--text-dim);
  width: 26px;
  height: 26px;
  cursor: pointer;
  font-size: 13px;
  display: flex;
  align-items: center;
  justify-content: center;
}
.modal-close:hover { color: var(--text-hi); border-color: var(--line-strong); }

.log-output {
  flex: 1;
  overflow-y: auto;
  padding: 10px;
  font-family: var(--font-mono);
  font-size: 10px;
  line-height: 1.5;
  background: var(--bg-deep);
  max-height: 60vh;
}
.log-wait {
  color: var(--text-faint);
  padding: 20px;
  text-align: center;
}
.log-line {
  white-space: pre-wrap;
  word-break: break-all;
  padding: 1px 0;
  color: var(--text-dim);
}
.log-line.error { color: var(--red); }
.log-line.warn { color: var(--amber-soft); }
.log-line.info { color: var(--cyan-soft); }
</style>
