// ADA/Mission Control — Service Worker
// Cache-first for app shell, network-first for API, network-only for SSE.

const CACHE = 'mc-v2'

// ── Install: precache the app shell ──────────────────────────────────────
self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE).then((cache) => {
      return cache.addAll([
        '/',
        '/manifest.webmanifest',
        '/icons/icon-192x192.png',
        '/icons/icon-512x512.png',
        '/icons/apple-touch-icon.png',
      ])
    })
  )
  self.skipWaiting()
})

// ── Activate: purge old caches ───────────────────────────────────────────
self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((keys) => {
      return Promise.all(
        keys.filter((k) => k !== CACHE).map((k) => caches.delete(k))
      )
    })
  )
  self.clients.claim()
})

// ── Fetch: routing strategy ──────────────────────────────────────────────
self.addEventListener('fetch', (event) => {
  const { pathname } = new URL(event.request.url)

  // SSE stream + CA cert download — bypass cache entirely
  if (pathname === '/events' || pathname === '/ca-cert.pem') return

  // API endpoints — network first, fallback to cache
  if (pathname.startsWith('/api/')) {
    event.respondWith(networkFirst(event.request))
    return
  }

  // Static assets (hashed by Vite) — cache first
  if (pathname.startsWith('/assets/')) {
    event.respondWith(cacheFirst(event.request))
    return
  }

  // App shell + icons — network first (so updates propagate)
  event.respondWith(networkFirst(event.request))
})

// ── Strategies ────────────────────────────────────────────────────────────

async function networkFirst(request) {
  try {
    const response = await fetch(request)
    // Cache a clone for offline fallback
    const cache = await caches.open(CACHE)
    cache.put(request, response.clone())
    return response
  } catch (_err) {
    const cached = await caches.match(request)
    return cached || new Response('Offline', { status: 503 })
  }
}

async function cacheFirst(request) {
  const cached = await caches.match(request)
  if (cached) return cached
  try {
    const response = await fetch(request)
    const cache = await caches.open(CACHE)
    cache.put(request, response.clone())
    return response
  } catch (_err) {
    return new Response('Offline', { status: 503 })
  }
}
