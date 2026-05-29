import { defineStore } from 'pinia'
import { ref, computed } from 'vue'

/**
 * Content store — agent documents + knowledge vault.
 * Agent docs fetched from /api/content, vault from /api/vault.
 */
export const useContentStore = defineStore('content', () => {
  // ── Agent documents ────────────────────────────────────
  const documents = ref([])
  const selectedDoc = ref(null)
  const docContent = ref('')
  const absPath = ref('')
  const isEditing = ref(false)
  const isLoading = ref(false)

  // ── Vault documents ────────────────────────────────────
  const vaultDocuments = ref([])
  const vaultContent = ref('')
  const vaultAbsPath = ref('')

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
      absPath.value = data.abs_path || ''
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

  // ── Vault API ──────────────────────────────────────────

  /** Fetch vault document list from server. */
  async function fetchVaultDocuments() {
    isLoading.value = true
    try {
      const res = await fetch('/api/vault')
      if (!res.ok) throw new Error(`HTTP ${res.status}`)
      const data = await res.json()
      vaultDocuments.value = Array.isArray(data.documents) ? data.documents : []
    } catch (e) {
      console.warn('Vault: fetchVaultDocuments failed:', e.message)
      vaultDocuments.value = []
    } finally {
      isLoading.value = false
    }
  }

  /** Fetch raw content of a vault document. */
  async function fetchVaultDocContent(relPath) {
    isLoading.value = true
    try {
      const url = `/api/vault/get?path=${encodeURIComponent(relPath)}`
      const res = await fetch(url)
      if (!res.ok) throw new Error(`HTTP ${res.status}`)
      const data = await res.json()
      if (data.error) {
        console.warn('Vault: fetchVaultDocContent error:', data.error)
        return null
      }
      vaultContent.value = data.content || ''
      vaultAbsPath.value = data.abs_path || ''
      return data.content
    } catch (e) {
      console.warn('Vault: fetchVaultDocContent failed:', e.message)
      return null
    } finally {
      isLoading.value = false
    }
  }

  // ── Vault selection ───────────────────────────────────

  /** Select a vault document and load its content. */
  function selectVaultDocument(doc) {
    selectedDoc.value = doc   // re-use selectedDoc for preview component
    docContent.value = ''
    absPath.value = ''
    vaultContent.value = ''
    vaultAbsPath.value = ''
    isEditing.value = false
    if (doc?.rel_path) {
      fetchVaultDocContent(doc.rel_path)
    }
  }

  // ── Selection ──────────────────────────────────────────

  /** Select a document and load its content */
  function selectDocument(doc) {
    selectedDoc.value = doc
    docContent.value = ''
    absPath.value = ''
    isEditing.value = false
    if (doc?.rel_path) {
      fetchDocContent(doc.rel_path)
    }
  }

  /** Clear the current selection */
  function clearSelection() {
    selectedDoc.value = null
    docContent.value = ''
    absPath.value = ''
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

  /** Documents grouped by agent, then by year-month. */
  const documentsByAgentAndMonth = computed(() => {
    const groups = {}
    for (const doc of documents.value) {
      const agent = doc.agent || 'unknown'
      if (!groups[agent]) groups[agent] = {}

      let ym = 'unknown'
      if (doc.modified_at) {
        const d = new Date(doc.modified_at * 1000)
        ym = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}`
      }

      if (!groups[agent][ym]) groups[agent][ym] = []
      groups[agent][ym].push(doc)
    }
    return groups
  })

  /** Sorted list of agent names with documents */
  const agentList = computed(() =>
    Object.keys(documentsByAgent.value).sort()
  )

  /** Total document count */
  const documentCount = computed(() => documents.value.length)

  // ── Vault derived ──────────────────────────────────────

  /** Vault docs grouped by section (top-level directory). */
  const vaultBySection = computed(() => {
    const groups = {}
    for (const doc of vaultDocuments.value) {
      const sec = doc.section || 'other'
      if (!groups[sec]) groups[sec] = []
      groups[sec].push(doc)
    }
    return groups
  })

  /** Sorted vault section names. */
  const vaultSections = computed(() =>
    Object.keys(vaultBySection.value).sort()
  )

  /** Total vault document count. */
  const vaultCount = computed(() => vaultDocuments.value.length)

  return {
    // Agent docs
    documents,
    selectedDoc,
    docContent,
    absPath,
    isEditing,
    isLoading,
    documentsByAgent,
    documentsByAgentAndMonth,
    agentList,
    documentCount,
    fetchDocuments,
    fetchDocContent,
    saveDoc,
    selectDocument,
    clearSelection,
    toggleEdit,
    // Vault
    vaultDocuments,
    vaultContent,
    vaultAbsPath,
    vaultBySection,
    vaultSections,
    vaultCount,
    fetchVaultDocuments,
    fetchVaultDocContent,
    selectVaultDocument,
  }
})
