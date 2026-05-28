import { createApp } from 'vue'
import { createPinia } from 'pinia'
import router from './router/index.js'
import App from './App.vue'
import './assets/tokens.css'

const app = createApp(App)
app.use(createPinia())
app.use(router)
app.mount('#app')

// ── PWA: Service Worker registration ─────────────────────────────────────
if ('serviceWorker' in navigator) {
  navigator.serviceWorker.register('/sw.js').catch((err) => {
    console.warn('SW registration failed:', err)
  })
}
