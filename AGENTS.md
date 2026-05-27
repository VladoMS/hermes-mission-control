# AGENTS.md — Operator's Manual for Hermes Mission Control

Read this before editing any file in this repo.

## 0. What this is

A single-pilot dashboard for Hermes Agent. Not a multi-agent system. Not "AgentOS." One ADA, six profiles, one operator (Vladislav).

The dashboard reads Hermes data sources read-only. The only writes are to the local `dashboard.db` (retention cache) and `~/.hermes/content/` (document save endpoint).

## 1. Architecture (v2 — Vue 3 migration)

### Backend: Python stdlib only

- `http.server`, `sqlite3`, `json`, `subprocess`, `threading`, `os`, `time`. No pip packages.
- `server.py` — snapshot assembly, SSE streaming, content API, Dokku log streaming.
- Port `0.0.0.0:51763`. Firewall restricts to Tailscale CGNAT only. Never expose to public internet.

### Frontend: Vue 3 + Vite

- **DO NOT** edit `dist/` files directly — they are build output from `mission-control-vue/`.
- Source lives in `mission-control-vue/src/`. Build with `npm run build` from `mission-control-vue/`.
- The old `index.html` (vanilla JS) is archived in `backups/`. Do not restore it.

### Build pipeline

```bash
cd mission-control-vue && npm run build   # → ../dist/
sudo systemctl restart mission-control     # Serve new build
```

## 2. File layout

```
server.py                           — Backend: HTTP server, data readers, snapshot assembly, SSE
dist/                               — Vue 3 production build (served by server.py)
  index.html                        — SPA entry point
  assets/                           — Hashed JS/CSS chunks (6 lazy-loaded page chunks)
mission-control-vue/                — Vue 3 source
  src/
    main.js                         — App bootstrap (Pinia + Router)
    App.vue                         — Root: BackgroundLayers, TopBar, MobileNavDrawer, <router-view>
    router/index.js                 — 6 routes (overview, profiles, kanban, servers, sessions, content)
    stores/                         — 7 Pinia stores (see README)
    composables/useSSE.js           — EventSource connection + polling fallback
    views/                          — 6 page components
    components/                     — 28 reusable components
    assets/tokens.css               — Vladoms CSS custom properties + primitives
  vite.config.js                    — Proxy /events + /api → :51763
dashboard.db                        — Auto-created. 30-day snapshot retention. Never commit.
servers.json                        — Server list config
backups/                            — Pre-change backups of the old index.html
start.sh / stop.sh                  — Convenience launch scripts (systemd is the primary runner)
```

## 3. Data sources (all read-only)

| Source | Path | Access |
|--------|------|--------|
| Gateway state | `{HERMES_HOME}/gateway_state.json` | `read_json()` |
| Cron jobs | `{HERMES_HOME}/cron/jobs.json` | `read_json()` |
| Sessions index | `{HERMES_HOME}/sessions/sessions.json` | `read_json()` |
| Processes | `{HERMES_HOME}/processes.json` | `read_json()` |
| Skills usage | `{HERMES_HOME}/skills/.usage.json` | `read_json()` |
| State DB (root) | `{HERMES_HOME}/state.db` | `read_sqlite_ro()` |
| State DB (profiles) | `{HERMES_HOME}/profiles/{name}/state.db` | `read_sqlite_ro()` |
| Profile config | `{HERMES_HOME}/profiles/{name}/config.yaml` | `yaml.safe_load` |
| Profile description | `{HERMES_HOME}/profiles/{name}/profile.yaml` | `yaml.safe_load` |
| Kanban DB | `{HERMES_HOME}/kanban.db` | `read_kanban_boards()` |
| Content files | `{HERMES_HOME}/content/{profile}/*.md` | `list_content()`, `read_content()` |
| VPS health (hermes) | `/proc/stat`, `/proc/meminfo`, `os.statvfs` | `get_hermes_health()` |
| VPS health (prod) | `ssh prod` + same `/proc` reads | `get_prod_health()` (30s TTL) |
| Dokku apps/containers | `ssh prod dokku apps:list` + `docker ps` | `_get_dokku_data()` |
| Container stats | `ssh prod docker stats --no-stream` | Added to `container_stats` in dokku dict |
| Docker logs (live) | `ssh prod docker logs --follow` | SSE endpoint `/api/dokku/logs` |

`HERMES_HOME` is resolved by `_resolve_hermes_home()` — handles the case where the server runs under a kanban profile with nested HOME.

## 4. Gotchas (real bugs we hit — don't repeat)

### 4.1 Don't edit dist/ directly
`dist/` is build output. All UI changes go in `mission-control-vue/src/`, followed by `npm run build`. Editing dist files will be clobbered on the next build.

### 4.2 SSE event type is critical
The snapshot SSE stream MUST send `event: snapshot\ndata: {json}\n\n`. The frontend's EventSource listener is registered with `addEventListener('snapshot', ...)`. If the event field is missing, the listener never fires.

### 4.3 Dokku log SSE uses default message event
`/api/dokku/logs` sends plain `data: ...\n\n` (no event field). The frontend listens via `source.onmessage`. This is intentional to keep the payload simple for line-by-line streaming.

### 4.4 Vue reactivity replaces imperative change detection
The vanilla JS dashboard used fingerprint-based change detection (JSON diffs before touching DOM). In Vue, Pinia computed properties + `watch()` with deep comparison handle this. Canvas components (RadarCanvas, SparklineCanvas, PieChart) still do their own key-based skip-redraw checks to avoid 60fps canvas repaints on every SSE push.

### 4.5 Canvas lifecycle
Canvas components use `onMounted` + `watch(snapshot.data)` to draw. RadarCanvas uses `requestAnimationFrame` for the animated sweep — the loop is self-sustaining after initial boot and reads fresh data from the store on every frame. Always cancelAnimationFrame in `onUnmounted`.

### 4.6 SSR is not used
Vite builds this as a pure client-side SPA (`createWebHistory`). There is no SSR, no hydration mismatch issues. All data arrives via SSE after mount.

### 4.7 SQLite must be read-only on Hermes DBs
`kanban.db` and all `state.db` files open with `file:path?mode=ro` + `PRAGMA query_only=1`. Never write to these — the running Hermes process owns them. The only writable DB is `dashboard.db` (owned exclusively by this server).

### 4.8 `glm-5.1` model returns `None` timestamps
Some sessions in `state.db` have `model: "glm-5.1"` with `started_at: null`. The sessions renderer must handle null timestamps gracefully (show `—`).

### 4.9 Dokku container name pattern
Dokku containers follow `APPNAME.PROCESS.N` naming (e.g., `vladislavstoyanov.web.1`, `mh-fashion.scheduler.1`). The DokkuGrid component groups containers by app name prefix. The log viewer assumes `.web.1` — if an app uses a different process type, logs won't stream.

## 5. Design tokens (vladoms)

```css
/* Surfaces */
--bg-void: #05080b;  --bg-deep: #080c11;  --bg-surface: #0c121a;  --bg-elevated: #111923;

/* Accents */
--red: #ff3b1f;      --amber: #ffb020;      --cyan: #1ec8ff;
--green: #4ade80;     --magenta: #d946ef;

/* Text */
--text-hi: #e8edf3;   --text: #b6c0cb;   --text-dim: #6b7585;   --text-faint: #404a58;

/* Type */
--font-display: "Saira Condensed";  --font-body: "IBM Plex Sans";  --font-mono: "JetBrains Mono";
```

Background layers: `.bg-grid` (64px), `.bg-vignette` (red/cyan radial), `.bg-scanlines` (CRT). All GPU-promoted with `transform: translateZ(0)` + `contain: paint`.

## 6. Vue conventions

- **Composition API only.** All components use `<script setup>`. No Options API.
- **Scoped styles.** Every component has `<style scoped>`. Global primitives live in `tokens.css`.
- **Composables for shared logic.** `useSSE` is the pattern. New shared behavior goes in `src/composables/`.
- **Stores derive from snapshot.** All domain stores (profiles, sessions, etc.) use `useSnapshotStore().data` via `computed()`. They do not fetch data independently.
- **Lazy-loaded routes.** All page views except Overview use dynamic `() => import()`. Vite code-splits them into separate chunks.
- **Tone**: dry tactical HUD. Not marketing copy. Not "warm and friendly."
- **No emoji.** Use geometric glyphs: `◆ ▶ › → ─`
