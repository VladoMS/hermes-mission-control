import { defineStore } from 'pinia'
import { ref, computed } from 'vue'

/**
 * Content store — document list, selection, and edit mode.
 * Data is fetched from /api/content endpoints (not in SSE snapshot).
 */
export const useContentStore = defineStore('content', () => {
  /** All discovered markdown documents */
  const documents = ref([])

  /** Currently selected document metadata */
  const selectedDoc = ref(null)

  /** Raw markdown content of the selected document */
  const docContent = ref('')

  /** Whether the editor is active */
  const isEditing = ref(false)

  /** Loading state for API calls */
  const isLoading = ref(false)

  // ── API ────────────────────────────────────────────────

  /**
   * Fetch the document list from the server.
   * Each doc: { agent, filename, rel_path, title, modified_at, size }
   */
  async function fetchDocuments() {
    isLoading.value = true
    try {
      const res = await fetch('/api/content')
      if (!res.ok) throw new Error(`HTTP ${res.status}`)
      const data = await res.json()
      documents.value = Array.isArray(data) ? data : (data.documents || [])
    } catch (e) {
      console.warn('Content: fetchDocuments failed:', e.message)
    } finally {
      isLoading.value = false
    }
  }

  /**
   * Fetch the raw content of a specific document.
   * Returns the content string, or null on failure.
   */
  async function fetchDocContent(relPath) {
    isLoading.value = true
    try {
      const url = `/api/content/get?path=${encodeURIComponent(relPath)}`
      const res = await fetch(url)
      if (!res.ok) throw new Error(`HTTP ${res.status}`)
      const data = await res.json()
      if (data.error) {
        console.warn('Content: fetchDocContent error:', data.error)
        return null
      }
      docContent.value = data.content || ''
      return data.content
    } catch (e) {
      console.warn('Content: fetchDocContent failed:', e.message)
      return null
    } finally {
      isLoading.value = false
    }
  }

  /**
   * Save document content back to the server.
   * Returns true on success.
   */
  async function saveDoc(relPath, content) {
    try {
      const res = await fetch('/api/content/save', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ path: relPath, content }),
      })
      if (!res.ok) throw new Error(`HTTP ${res.status}`)
      const data = await res.json()
      if (data.error) {
        console.warn('Content: saveDoc error:', data.error)
        return false
      }
      // Refresh the in-memory content
      docContent.value = content
      return true
    } catch (e) {
      console.warn('Content: saveDoc failed:', e.message)
      return false
    }
  }

  // ── Selection ──────────────────────────────────────────

  /** Select a document and load its content */
  function selectDocument(doc) {
    selectedDoc.value = doc
    docContent.value = ''
    isEditing.value = false
    if (doc?.rel_path) {
      fetchDocContent(doc.rel_path)
    }
  }

  /** Clear the current selection */
  function clearSelection() {
    selectedDoc.value = null
    docContent.value = ''
    isEditing.value = false
  }

  /** Toggle edit mode on/off */
  function toggleEdit() {
    isEditing.value = !isEditing.value
  }

  // ── Derived ────────────────────────────────────────────

  /** Documents grouped by agent (profile) name */
  const documentsByAgent = computed(() => {
    const groups = {}
    for (const doc of documents.value) {
      const agent = doc.agent || 'unknown'
      if (!groups[agent]) groups[agent] = []
      groups[agent].push(doc)
    }
    return groups
  })

  /** Sorted list of agent names with documents */
  const agentList = computed(() =>
    Object.keys(documentsByAgent.value).sort()
  )

  /** Total document count */
  const documentCount = computed(() => documents.value.length)

  return {
    documents,
    selectedDoc,
    docContent,
    isEditing,
    isLoading,
    documentsByAgent,
    agentList,
    documentCount,
    fetchDocuments,
    fetchDocContent,
    saveDoc,
    selectDocument,
    clearSelection,
    toggleEdit,
  }
})
