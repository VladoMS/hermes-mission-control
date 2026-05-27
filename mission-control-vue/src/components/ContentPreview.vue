<template>
  <div class="content-preview panel">
    <!-- Empty state -->
    <div v-if="!contentStore.selectedDoc" class="preview-empty">
      <div class="placeholder-panel">Select a document from the sidebar</div>
    </div>

    <!-- Loading -->
    <div v-else-if="contentStore.isLoading" class="preview-loading mono">Loading...</div>

    <!-- Document content -->
    <template v-else>
      <div class="preview-header">
        <div class="eyebrow">{{ contentStore.selectedDoc.agent }}</div>
        <div class="preview-title mono">{{ contentStore.selectedDoc.title || contentStore.selectedDoc.filename }}</div>
        <div class="preview-actions">
          <span class="preview-meta mono">{{ contentStore.selectedDoc.modified_at || '' }}</span>
          <button class="btn ghost" @click="contentStore.toggleEdit()">
            {{ contentStore.isEditing ? 'VIEW' : 'EDIT' }}
          </button>
        </div>
      </div>

      <!-- View mode -->
      <div v-if="!contentStore.isEditing" class="preview-content" v-html="renderedHtml"></div>

      <!-- Edit mode -->
      <div v-else class="preview-edit">
        <textarea
          v-model="editText"
          class="edit-textarea mono"
          spellcheck="false"
        ></textarea>
        <div class="edit-actions">
          <button class="btn" @click="handleSave">
            SAVE
          </button>
        </div>
      </div>
    </template>
  </div>
</template>

<script setup>
import { computed, ref, watch } from 'vue'
import { useContentStore } from '../stores/content.js'

const contentStore = useContentStore()
const editText = ref('')

// Simple markdown-to-HTML (we have marked but let's do basic rendering)
function renderMd(text) {
  if (!text) return ''
  return text
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/^### (.+)$/gm, '<h3>$1</h3>')
    .replace(/^## (.+)$/gm, '<h2>$1</h2>')
    .replace(/^# (.+)$/gm, '<h1>$1</h1>')
    .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
    .replace(/\*(.+?)\*/g, '<em>$1</em>')
    .replace(/`(.+?)`/g, '<code>$1</code>')
    .replace(/```([\s\S]*?)```/g, '<pre><code>$1</code></pre>')
    .replace(/\n/g, '<br>')
}

const renderedHtml = computed(() => renderMd(contentStore.docContent))

watch(() => contentStore.docContent, (val) => {
  editText.value = val
})

async function handleSave() {
  const doc = contentStore.selectedDoc
  if (!doc) return
  const ok = await contentStore.saveDoc(doc.rel_path, editText.value)
  if (ok) contentStore.toggleEdit()
}
</script>

<style scoped>
.content-preview { padding: 18px; min-height: 400px; }
.preview-empty { display: flex; align-items: center; justify-content: center; min-height: 300px; }
.preview-loading { font-size: 10px; color: var(--text-faint); padding: 20px; }
.preview-header { margin-bottom: 18px; }
.preview-title {
  font-size: 14px;
  color: var(--text-hi);
  margin-top: 6px;
  font-weight: 600;
}
.preview-actions {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-top: 10px;
}
.preview-meta { font-size: 10px; color: var(--text-faint); }
.preview-content {
  font-family: var(--font-body);
  font-size: 13px;
  line-height: 1.7;
  color: var(--text);
}
.preview-content :deep(h1) {
  font-family: var(--font-display);
  font-size: 22px;
  color: var(--text-hi);
  margin: 16px 0 8px;
  text-transform: uppercase;
}
.preview-content :deep(h2) {
  font-family: var(--font-display);
  font-size: 18px;
  color: var(--text-hi);
  margin: 14px 0 6px;
}
.preview-content :deep(h3) {
  font-family: var(--font-display);
  font-size: 14px;
  color: var(--text);
  margin: 12px 0 4px;
}
.preview-content :deep(code) {
  font-family: var(--font-mono);
  font-size: 11px;
  background: var(--bg-deep);
  padding: 1px 4px;
}
.preview-content :deep(pre) {
  background: var(--bg-deep);
  padding: 12px;
  overflow-x: auto;
  margin: 8px 0;
}
.preview-content :deep(pre code) {
  background: transparent;
  padding: 0;
  font-size: 10px;
  color: var(--text-dim);
}
.edit-textarea {
  width: 100%;
  min-height: 300px;
  background: var(--bg-deep);
  border: 1px solid var(--line);
  color: var(--text);
  padding: 12px;
  font-size: 12px;
  line-height: 1.6;
  resize: vertical;
  outline: none;
}
.edit-textarea:focus { border-color: var(--red-line); }
.edit-actions { margin-top: 12px; }
</style>
