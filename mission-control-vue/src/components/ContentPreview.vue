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
      <div v-if="!contentStore.isEditing" class="preview-content" v-html="renderedHtml" @click="handleVaultLinkClick"></div>

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

  // ── Obsidian callouts ──
  // Convert > [!TYPE] Title\n> Content into styled divs
  // Must run BEFORE marked.parse so blockquotes don't double-process
  text = renderCallouts(text)

  // Convert wikilinks with alias: [[path|Alias]] → [Alias](vault://path)
  // Preserve heading anchors: [[path#heading|Alias]] → [Alias](vault://path#heading)
  text = text.replace(/\[\[([^\]|]+)\|([^\]]+)\]\]/g, (_m, path, alias) => {
    return `[${alias.trim()}](vault://${path.trim()})`
  })

  // Convert bare wikilinks: [[path#heading]] → [path](vault://path#heading)
  // (after aliased ones so we don't double-match)
  text = text.replace(/\[\[([^\]]+)\]\]/g, (_m, path) => {
    // Strip block references: note^block → note
    let clean = path.replace(/\^[a-zA-Z0-9-]+$/, '').trim()
    // Display text: strip heading anchor for cleaner link text
    const display = clean.replace(/#.+$/, '')
    return `[${display}](vault://${clean})`
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

// ── Vault wikilink navigation ──

/**
 * Intercept clicks on vault:// links and navigate within the Content browser.
 * Prevents the "scheme does not have a registered handler" browser error.
 */
function handleVaultLinkClick(event) {
  // Find the vault:// link element (could be the link itself or a child)
  let target = event.target
  while (target && target !== event.currentTarget) {
    if (target.tagName === 'A' && target.href && target.href.startsWith('vault://')) {
      event.preventDefault()
      navigateToVaultDoc(target.href)
      return
    }
    target = target.parentElement
  }
}

/**
 * Resolve a vault://path to an actual vault document and select it.
 * Supports heading anchors: vault://path#heading
 */
function navigateToVaultDoc(vaultUrl) {
  const rawPath = vaultUrl.replace('vault://', '')
  const [linkPath, headingAnchor] = rawPath.split('#')

  if (!linkPath) return

  // Search vault documents for a filename match
  // Fuzzy: [[azahar-room-server]] should match .../azahar-room-server.md
  const searchName = linkPath.toLowerCase().replace(/\.md$/, '')
  const docs = contentStore.vaultDocuments

  // Try exact rel_path match first, then filename match, then partial match
  let match = docs.find(d => d.rel_path === linkPath)
    || docs.find(d => d.rel_path === linkPath + '.md')
    || docs.find(d => d.filename.toLowerCase() === searchName + '.md')
    || docs.find(d => d.filename.toLowerCase().includes(searchName))
    || docs.find(d => d.rel_path.toLowerCase().includes(searchName))

  if (match) {
    contentStore.selectVaultDocument(match)
    // After content loads, scroll to the heading anchor if present
    if (headingAnchor) {
      // Wait for content to render, then scroll
      setTimeout(() => {
        const el = document.getElementById(headingAnchor)
        if (el) {
          el.scrollIntoView({ behavior: 'smooth', block: 'start' })
        }
      }, 300)
    }
  }
}

// ── Obsidian Callout Rendering ──

// Obsidian callout type → CSS class mapping
const CALLOUT_MAP = {
  'note': 'callout-note',
  'abstract': 'callout-abstract', 'summary': 'callout-abstract', 'tldr': 'callout-abstract',
  'info': 'callout-info',
  'tip': 'callout-tip', 'hint': 'callout-tip', 'important': 'callout-tip',
  'success': 'callout-success', 'check': 'callout-success', 'done': 'callout-success',
  'question': 'callout-question', 'help': 'callout-question', 'faq': 'callout-question',
  'warning': 'callout-warning', 'caution': 'callout-warning', 'attention': 'callout-warning',
  'failure': 'callout-failure', 'fail': 'callout-failure', 'missing': 'callout-failure',
  'danger': 'callout-danger', 'error': 'callout-danger',
  'bug': 'callout-bug',
  'example': 'callout-example',
  'quote': 'callout-quote', 'cite': 'callout-quote',
}

/**
 * Convert Obsidian callout blocks ("> [!TYPE] Title\n> Content") into styled HTML divs.
 * Handles multi-line callout bodies, nested content, and foldable callouts ([!TYPE]+ / [!TYPE]-).
 * Runs before marked.parse to prevent double blockquote rendering.
 */
function renderCallouts(text) {
  // Match callout blocks: lines starting with "> [!TYPE]" optionally followed by +/-
  // Body lines start with ">" and optional space
  const calloutRegex = /^(> \[!(\w+)\](\+|-)?\s*(.*)\n)((?:>.*\n?)*)/gm

  return text.replace(calloutRegex, (match, header, type, foldable, title, body) => {
    const cssClass = CALLOUT_MAP[type.toLowerCase()] || 'callout-note'
    const displayTitle = title.trim() || type.charAt(0).toUpperCase() + type.slice(1)
    const isFoldable = foldable === '+' || foldable === '-'
    const isOpen = foldable !== '-' // [+] means open, [-] means closed, no foldable = always open

    // Strip "> " prefix from body lines, preserve content after
    const bodyLines = body
      .split('\n')
      .filter(line => line.trim())
      .map(line => line.replace(/^>\s?/, ''))
      .join('\n')

    // Build the HTML
    const foldClass = isFoldable ? ' callout-foldable' : ''
    const stateClass = isFoldable && !isOpen ? ' callout-collapsed' : ''

    let html = `<div class="obsidian-callout ${cssClass}${foldClass}${stateClass}">`
    html += `<div class="callout-title">`
    if (isFoldable) {
      html += `<span class="callout-fold-icon">${isOpen ? '▼' : '▶'}</span> `
    }
    html += `${displayTitle}</div>`
    if (bodyLines) {
      // Re-process body through marked for rich content (lists, code, etc.)
      html += `<div class="callout-body">${marked.parse(bodyLines)}</div>`
    }
    html += `</div>`

    return html
  })
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
/* Obsidian callout styling */
.preview-content :deep(.obsidian-callout) {
  margin: 10px 0;
  padding: 10px 14px;
  border-left: 3px solid var(--text-faint);
  background: var(--bg-deep);
  border-radius: 0 4px 4px 0;
}
.preview-content :deep(.callout-title) {
  font-family: var(--font-display);
  font-size: 13px;
  font-weight: 600;
  margin-bottom: 4px;
  text-transform: uppercase;
  letter-spacing: 0.05em;
}
.preview-content :deep(.callout-fold-icon) {
  font-size: 10px;
  margin-right: 2px;
  cursor: default;
}
.preview-content :deep(.callout-body) {
  font-size: 12px;
  line-height: 1.6;
}
.preview-content :deep(.callout-body p) { margin: 4px 0; }
.preview-content :deep(.callout-body ul),
.preview-content :deep(.callout-body ol) { padding-left: 16px; margin: 4px 0; }

/* Callout type colors */
.preview-content :deep(.callout-note) { border-left-color: var(--cyan); }
.preview-content :deep(.callout-note .callout-title) { color: var(--cyan); }

.preview-content :deep(.callout-abstract) { border-left-color: var(--cyan); background: rgba(30,200,255,0.04); }
.preview-content :deep(.callout-abstract .callout-title) { color: var(--cyan); }

.preview-content :deep(.callout-info) { border-left-color: var(--cyan); }
.preview-content :deep(.callout-info .callout-title) { color: var(--cyan); }

.preview-content :deep(.callout-tip) { border-left-color: var(--green); background: rgba(74,222,128,0.04); }
.preview-content :deep(.callout-tip .callout-title) { color: var(--green); }

.preview-content :deep(.callout-success) { border-left-color: var(--green); }
.preview-content :deep(.callout-success .callout-title) { color: var(--green); }

.preview-content :deep(.callout-question) { border-left-color: var(--magenta); background: rgba(217,70,239,0.04); }
.preview-content :deep(.callout-question .callout-title) { color: var(--magenta); }

.preview-content :deep(.callout-warning) { border-left-color: var(--amber); background: rgba(255,176,32,0.04); }
.preview-content :deep(.callout-warning .callout-title) { color: var(--amber); }

.preview-content :deep(.callout-failure) { border-left-color: var(--red); background: rgba(255,59,31,0.04); }
.preview-content :deep(.callout-failure .callout-title) { color: var(--red); }

.preview-content :deep(.callout-danger) { border-left-color: var(--red); border-left-width: 4px; }
.preview-content :deep(.callout-danger .callout-title) { color: var(--red); }

.preview-content :deep(.callout-bug) { border-left-color: var(--red); }
.preview-content :deep(.callout-bug .callout-title) { color: var(--red); }

.preview-content :deep(.callout-example) { border-left-color: var(--magenta); }
.preview-content :deep(.callout-example .callout-title) { color: var(--magenta); }

.preview-content :deep(.callout-quote) { border-left-color: var(--text-dim); background: rgba(182,192,203,0.04); }
.preview-content :deep(.callout-quote .callout-title) { color: var(--text-dim); }

/* Foldable states */
.preview-content :deep(.callout-collapsed .callout-body) { display: none; }
.preview-content :deep(.callout-foldable .callout-title) { cursor: pointer; user-select: none; }
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
  cursor: pointer;
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
