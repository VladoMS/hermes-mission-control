import { ref } from 'vue'

/**
 * PWA install handler — captures the beforeinstallprompt event
 * and exposes a trigger for explicit install.
 *
 * Chrome fires beforeinstallprompt when PWA criteria are met
 * (HTTPS, valid manifest, registered SW). Firefox never fires it.
 */
const installEvent = ref(null)
const installable = ref(false)
const installed = ref(false)

// Listen early, before Vue mounts
if (typeof window !== 'undefined') {
  window.addEventListener('beforeinstallprompt', (e) => {
    e.preventDefault()
    installEvent.value = e
    installable.value = true
  })

  window.addEventListener('appinstalled', () => {
    installed.value = true
    installable.value = false
    installEvent.value = null
  })
}

export function usePwaInstall() {
  async function install() {
    if (!installEvent.value) return
    installEvent.value.prompt()
    const result = await installEvent.value.userChoice
    if (result.outcome === 'accepted') {
      installed.value = true
    }
    installable.value = false
    installEvent.value = null
  }

  return { installable, installed, install }
}
