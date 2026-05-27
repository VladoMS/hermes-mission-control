import { ref } from 'vue'

// Global singleton — one toast queue for the entire app
const toasts = ref([])
let _nextId = 0

/**
 * useToast composable — app-wide toast notifications.
 * Toasts render bottom-right, auto-dismiss, and stack.
 *
 * Usage:
 *   const { toast } = useToast()
 *   toast('Copied to clipboard')
 */
export function useToast() {
  function toast(message, duration = 2500) {
    const id = ++_nextId
    toasts.value.push({ id, message })
    setTimeout(() => {
      toasts.value = toasts.value.filter(t => t.id !== id)
    }, duration)
  }

  return { toasts, toast }
}
