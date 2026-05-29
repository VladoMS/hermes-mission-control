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
        <div class="eyebrow">{{ isVault ? 'VAULT ► ' + (contentStore.selectedDoc.section || '') : contentStore.selectedDoc.agent }}</div>
        <div class="preview-title mono">{{ contentStore.selectedDoc.title || contentStore.selectedDoc.filename }}</div>
        <div class="preview-actions">
          <span class="preview-meta mono">{{ contentStore.selectedDoc.modified_at || '' }}</span>
          <div class="preview-btns">
            <!-- Edit button (only in view mode, only for agent docs) -->
            <button
              v-if="!contentStore.isEditing && !isVault"
              class="btn ghost"
              @click="contentStore.toggleEdit()"
            >
              EDIT
            </button>
            <!-- Save button (only in edit mode) -->
            <button
              v-if="contentStore.isEditing"
              class="btn"
              @click="handleSave"
            >
              SAVE
            </button>
            <!-- Cancel button (only in edit mode) -->
            <button
              v-if="contentStore.isEditing"
              class="btn ghost"
              @click="cancelEdit"
            >
              CANCEL
            </button>
          </div>
        </div>
      </div>

      <!-- File metadata bar -->
      <div
        v-if="activeAbsPath"
        class="preview-path-meta"
        @click="copyPath"
        :title="'Click to copy full path'"
      >
        <span class="path-label mono">PATH ›</span>
        <span class="path-value mono">{{ activeAbsPath }}</span>
        <span v-if="copied" class="path-copied mono">COPIED</span>
      </div>

      <!-- Render mode (default) -->
      <div v-if="!contentStore.isEditing" class="preview-content" v-html="renderedHtml"></div>

      <!-- Edit mode -->
      <div v-if="contentStore.isEditing" class="preview-edit">
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
import { marked } from 'marked'

// Configure marked for safe rendering
marked.setOptions({
  breaks: true,
  gfm: true,
})

const contentStore = useContentStore()
const editText = ref('')
const copied = ref(false)

/** Whether the selected doc is from the vault. */
const isVault = computed(() =>
  contentStore.selectedDoc?.source === 'vault'
)

/** Content to render (agent or vault). */
const activeContent = computed(() =>
  isVault.value ? contentStore.vaultContent : contentStore.docContent
)

/** Absolute path to show and copy. */
const activeAbsPath = computed(() =>
  isVault.value ? contentStore.vaultAbsPath : contentStore.absPath
)

const renderedHtml = computed(() => {
  let text = activeContent.value
  if (!text) return ''

  // ── Obsidian markdown pre-processing ──

  // Strip YAML frontmatter (--- at start of file)
  text = text.replace(/^---[\s\S]*?---\n*/, '')

  // Convert wikilinks with alias: [[path|Alias]] → [Alias](vault://path)
  text = text.replace(/\[\[([^\]|#]+)\|([^\]]+)\]\]/g, (_m, path, alias) => {
    return `[${alias.trim()}](vault://${path.trim()})`
  })

  // Convert bare wikilinks: [[path]] → [path](vault://path)
  // (after aliased ones so we don't double-match)
  text = text.replace(/\[\[([^\]]+)\]\]/g, (_m, path) => {
    // Strip block references: note^block → note
    const clean = path.replace(/\^[a-zA-Z0-9-]+$/, '').trim()
    return `[${clean}](vault://${clean})`
  })

  // Convert inline #tags to styled spans (skip headings # like # H1)
  text = text.replace(/(^|[ \t])#([a-zA-Z][a-zA-Z0-9_-]+)/g, '$1<span class="obsidian-tag">#$2</span>')

  return marked.parse(text)
})

// Sync editText when doc content loads or changes
watch(activeContent, (val) => {
  editText.value = val
})

function copyPath() {
  const text = activeAbsPath.value
  if (!text) return

  // Try modern Clipboard API first (secure contexts only)
  if (navigator.clipboard && window.isSecureContext) {
    navigator.clipboard.writeText(text).then(() => {
      copied.value = true
      setTimeout(() => { copied.value = false }, 1500)
    }).catch(() => fallbackCopy(text))
    return
  }

  // Fallback for plain HTTP (Tailscale, etc.)
  fallbackCopy(text)
}

function fallbackCopy(text) {
  const ta = document.createElement('textarea')
  ta.value = text
  ta.style.position = 'fixed'
  ta.style.left = '-9999px'
  ta.style.top = '-9999px'
  document.body.appendChild(ta)
  ta.focus()
  ta.select()
  try {
    document.execCommand('copy')
    copied.value = true
    setTimeout(() => { copied.value = false }, 1500)
  } catch {
    // Copy failed silently
  }
  document.body.removeChild(ta)
}

async function handleSave() {
  const doc = contentStore.selectedDoc
  if (!doc) return
  const ok = await contentStore.saveDoc(doc.rel_path, editText.value)
  if (ok) contentStore.toggleEdit()
}

function cancelEdit() {
  editText.value = contentStore.docContent
  contentStore.toggleEdit()
}
</script>

<style scoped>
.content-preview { padding: 18px; min-height: 400px; overflow: hidden; min-width: 0; }
.preview-empty { display: flex; align-items: center; justify-content: center; min-height: 300px; }
.preview-loading { font-size: 10px; color: var(--text-faint); padding: 20px; }
.preview-header { margin-bottom: 18px; overflow: hidden; }
.preview-title {
  font-size: 14px;
  color: var(--text-hi);
  margin-top: 6px;
  font-weight: 600;
  overflow-wrap: break-word;
  word-break: break-word;
}
.preview-actions {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-top: 10px;
  flex-wrap: wrap;
  gap: 8px;
}
.preview-meta { font-size: 10px; color: var(--text-faint); }
.preview-btns {
  display: flex;
  gap: 8px;
  flex-shrink: 0;
}

/* File path metadata bar */
.preview-path-meta {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 14px;
  padding: 6px 10px;
  background: var(--bg-deep);
  border-left: 2px solid var(--cyan);
  cursor: pointer;
  transition: border-color 0.2s;
  overflow: hidden;
  user-select: none;
}
.preview-path-meta:hover {
  border-left-color: var(--red);
}
.path-label {
  font-size: 10px;
  color: var(--text-dim);
  flex-shrink: 0;
  letter-spacing: 0.5px;
}
.path-value {
  font-size: 11px;
  color: var(--text);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.path-copied {
  font-size: 10px;
  color: var(--green);
  flex-shrink: 0;
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

.preview-content {
  font-family: var(--font-body);
  font-size: 13px;
  line-height: 1.7;
  color: var(--text);
  overflow-wrap: break-word;
  word-break: break-word;
  overflow-x: hidden;
}
.preview-content :deep(h1) {
  font-family: var(--font-display);
  font-size: 22px;
  color: var(--text-hi);
  margin: 16px 0 8px;
  text-transform: uppercase;
  overflow-wrap: break-word;
  word-break: break-word;
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
  max-width: 100%;
}
.preview-content :deep(pre code) {
  background: transparent;
  padding: 0;
  font-size: 10px;
  color: var(--text-dim);
  white-space: pre-wrap;
  word-break: break-all;
}
.preview-content :deep(ul) {
  padding-left: 20px;
  margin: 6px 0;
}
.preview-content :deep(ol) {
  padding-left: 20px;
  margin: 6px 0;
}
.preview-content :deep(li) {
  margin: 2px 0;
}
.preview-content :deep(a) {
  color: var(--cyan);
  text-decoration: none;
}
.preview-content :deep(a:hover) {
  text-decoration: underline;
}
/* Obsidian tag styling */
.preview-content :deep(.obsidian-tag) {
  color: var(--magenta);
  background: rgba(217, 70, 239, 0.1);
  padding: 1px 4px;
  border-radius: 3px;
  font-size: 11px;
  font-family: var(--font-mono);
}
/* Vault wikilinks (converted from [[ ]]) */
.preview-content :deep(a[href^="vault://"]) {
  color: var(--green);
  text-decoration: none;
  border-bottom: 1px dashed var(--green);
}
.preview-content :deep(a[href^="vault://"]:hover) {
  color: var(--green);
  border-bottom-style: solid;
}
.preview-content :deep(hr) {
  border: none;
  border-top: 1px solid var(--line);
  margin: 12px 0;
}
.preview-content :deep(blockquote) {
  border-left: 2px solid var(--red-line);
  padding: 4px 0 4px 14px;
  margin: 8px 0;
  color: var(--text-dim);
}
.preview-content :deep(table) {
  border-collapse: collapse;
  max-width: 100%;
  table-layout: auto;
  margin: 10px 0;
  font-size: 12px;
}
.preview-content :deep(th) {
  text-align: left;
  padding: 6px 10px;
  border-bottom: 1px solid var(--line);
  color: var(--text-hi);
  font-family: var(--font-mono);
  text-transform: uppercase;
  font-size: 10px;
}
.preview-content :deep(td) {
  padding: 4px 10px;
  border-bottom: 1px solid var(--bg-elevated);
}
.preview-content :deep(tr:nth-child(even) td) {
  background: rgba(255,255,255,0.01);
}
.preview-content :deep(img) {
  max-width: 100%;
  height: auto;
}
.preview-content :deep(del) {
  text-decoration: line-through;
  color: var(--text-dim);
}
.preview-content :deep(input[type="checkbox"]) {
  margin-right: 6px;
  accent-color: var(--cyan);
}

/* Edit mode */
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
  font-family: var(--font-mono);
}
.edit-textarea:focus { border-color: var(--red-line); }
.edit-actions { margin-top: 12px; display: flex; gap: 8px; }
</style>
