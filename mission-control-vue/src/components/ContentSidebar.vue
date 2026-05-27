<template>
  <div class="content-sidebar panel">
    <div class="eyebrow">DOCUMENTS</div>
    <div v-if="contentStore.isLoading" class="sb-loading">Loading...</div>
    <div v-else-if="agentList.length === 0" class="sb-empty">No documents</div>
    <div v-for="agent in agentList" :key="agent" class="sb-group">
      <div class="sb-agent" @click="toggleGroup(agent)">
        <span class="sb-arrow" :class="{ open: openGroups[agent] }">▶</span>
        <span class="sb-agent-dot" :style="{ background: accent(agent) }"></span>
        <span class="sb-agent-name">{{ agent }}</span>
        <span class="sb-count">{{ (docsByAgent[agent] || []).length }}</span>
      </div>
      <div v-if="openGroups[agent]" class="sb-docs">
        <div
          v-for="doc in docsByAgent[agent]"
          :key="doc.rel_path"
          class="sb-doc"
          :class="{ active: contentStore.selectedDoc?.rel_path === doc.rel_path }"
          @click="contentStore.selectDocument(doc)"
        >
          {{ doc.title || doc.filename }}
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, reactive, onMounted } from 'vue'
import { useContentStore } from '../stores/content.js'

const contentStore = useContentStore()
const openGroups = reactive({})

const ACCENTS = {
  default: '#ff3b1f', coder: '#1ec8ff', researcher: '#4ade80',
  writer: '#ffb020', devops: '#d946ef', creative: '#fbbf24',
}

function accent(name) { return ACCENTS[name] || '#6b7585' }
function toggleGroup(agent) { openGroups[agent] = !openGroups[agent] }

const agentList = computed(() => contentStore.agentList)
const docsByAgent = computed(() => contentStore.documentsByAgent)

onMounted(() => { contentStore.fetchDocuments() })
</script>

<style scoped>
.content-sidebar {
  padding: 16px;
  height: fit-content;
  position: sticky;
  top: calc(var(--top-h) + 20px);
  max-height: calc(100vh - var(--top-h) - 40px);
  overflow-y: auto;
}
.sb-loading, .sb-empty {
  font-family: var(--font-mono);
  font-size: 10px;
  color: var(--text-faint);
  padding: 10px 0;
}
.sb-group { margin-top: 6px; }
.sb-agent {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 6px 8px;
  cursor: pointer;
  font-family: var(--font-mono);
  font-size: 11px;
  color: var(--text);
  letter-spacing: 0.06em;
  border-bottom: 1px solid var(--line-dim);
  user-select: none;
}
.sb-agent:hover { color: var(--text-hi); }
.sb-arrow { font-size: 7px; color: var(--text-faint); transition: transform 0.2s; }
.sb-arrow.open { transform: rotate(90deg); }
.sb-agent-dot { width: 6px; height: 6px; border-radius: 50%; flex-shrink: 0; }
.sb-agent-name { flex: 1; text-transform: uppercase; }
.sb-count { color: var(--text-faint); font-size: 10px; }
.sb-docs { padding-left: 18px; }
.sb-doc {
  padding: 5px 8px;
  cursor: pointer;
  font-family: var(--font-body);
  font-size: 12px;
  color: var(--text-dim);
  border-left: 2px solid transparent;
  transition: all 0.15s;
}
.sb-doc:hover { color: var(--text); background: rgba(255,255,255,0.03); }
.sb-doc.active {
  color: var(--text-hi);
  border-left-color: var(--red);
  background: var(--red-bg);
}
</style>
