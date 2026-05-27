# Hermes Mission Control

Tactical HUD dashboard for [Hermes Agent](https://hermes-agent.nousresearch.com) — a single pilot's live ops console built with the vladoms-design aesthetic (EVE Online inspired).

**URL**: `http://100.67.254.90:51763/` (Tailscale only)

## Stack

| Layer | Tech |
|---|---|
| **Frontend** | Vue 3 (Composition API), Vue Router 4, Pinia, Vite 6 |
| **Backend** | Python stdlib — `http.server`, `sqlite3`, `json`, `subprocess` |
| **Styling** | Vladoms-design CSS tokens (custom property system) |
| **Fonts** | Saira Condensed, IBM Plex Sans, JetBrains Mono (Google Fonts CDN) |

## Tabs

| Tab | Components | Description |
|---|---|---|
| **Overview** | StatsStrip, RadarCanvas, SparklineCanvas, ThroughputCard, DirectiveCycler, SystemStatus, VpsHealth, ActivityFeed | Live ops console — 5-stat strip, animated radar with profile dots, 7-day session sparkline, directive text cycler, VPS health for hermes + prod, activity feed, ops footer |
| **Profiles** | ProfileCard, ActivityLogTable | 6 agent profile cards with accent dots/badges, per-profile stats, status filters (all/active/idle/dormant), recent activity log |
| **Kanban** | KanbanCard, KanbanBoard, TaskModal | 7-column board (triage→cancelled), board selector, priority-colored task cards, teleported detail modal |
| **Servers** | HealthBar, ServerCard, DokkuGrid, LogViewer | Dynamic server cards — collapsible health/crons/dokku sections, 3-column Dokku app grid with per-container CPU/MEM bars, live log viewer with pause/resume |
| **Sessions** | TokenLedger, PieChart, SessionsTable | Token ledger aggregate, canvas donut pie chart, session table with profile/model dropdown filters, token breakdown (in/out/cache) |
| **Content** | ContentSidebar, ContentPreview | Documents grouped by agent (collapsible sidebar), markdown preview, view/edit toggle, save via POST /api/content/save |

## Architecture

```
server.py                  — Python backend (http.server, snapshot assembly, SSE, content API, Dokku log streaming)
mission-control-vue/       — Vue 3 source
  src/
    stores/                — 7 Pinia stores (snapshot, ui, profiles, kanban, sessions, servers, content)
    composables/           — useSSE (EventSource + polling fallback)
    views/                 — 6 page components (Overview, Profiles, Kanban, Servers, Sessions, Content)
    components/            — 28 reusable components
    router/                — Vue Router with lazy-loaded page chunks
    assets/tokens.css      — Vladoms-design CSS custom properties + primitives + responsive breakpoints
  vite.config.js           — Vite config with proxy to backend on :51763
dist/                      — Production build (served by server.py)
dashboard.db               — Local SQLite retention DB (30-day snapshot history)
servers.json               — Server list config — add new servers by editing this file
```

### Data flow

```
Hermes data sources (read-only)
  → server.py build_snapshot() every 5s
    → SSE /events → useSSE composable → snapshotStore
      → all 6 page stores derive reactive state from snapshot
    → GET /api/snapshot (polling fallback every 8s)
  → GET /api/content, POST /api/content/save (Content tab)
  → GET /api/dokku/logs?server=X&app=Y (live Docker logs via SSE)
```

### Stores (Pinia)

| Store | Derives from | Provides |
|---|---|---|
| `snapshotStore` | SSE `snapshot` event | `data`, `connected`, `lastUpdated`, fingerprint-based hydrate |
| `ui` | Local state | `activeTab`, `mobileMenuOpen`, `clock` (UTC), `navigateTo()` |
| `profiles` | `snapshot.data.profiles` | `profiles`, `activeCount`, `idleCount`, `dormantCount`, `getStatus()`, `getAccent()`, `getBadge()` |
| `kanban` | `snapshot.data.kanban` | `boards`, `boardNames`, `columns`, `tasks`, `selectedTask`, `selectTask()` |
| `sessions` | `snapshot.data.sessions`, `sessions_ledger` | `filteredSessions`, `filterProfile`, `filterModel`, `pieByModel`, `totalTokens`, `totalCost` |
| `servers` | `snapshot.data.servers` | `servers`, `getHealth()`, `getCrons()`, `getDokku()`, `allDokkuApps` |
| `content` | `fetch()` to content API | `documents`, `selectedDoc`, `docContent`, `isEditing`, `fetchDocuments()`, `saveDoc()` |

### Backend endpoints

| Method | Path | Description |
|---|---|---|
| GET | `/` | Serves `dist/index.html` (Vue SPA) |
| GET | `/assets/*` | Static files from `dist/assets/` with MIME types + 1h cache |
| GET | `/profiles`, `/kanban`, etc. | SPA fallback — serves `dist/index.html` for client-side routing |
| GET | `/api/snapshot` | Full JSON snapshot of all Hermes data sources |
| GET | `/api/content` | List markdown documents under `~/.hermes/content/` |
| GET | `/api/content/get?path=...` | Read a single document |
| POST | `/api/content/save` | Save document content back to disk |
| GET | `/events` | SSE stream — snapshot push every 5 seconds |
| GET | `/api/dokku/logs?server=X&app=Y&tail=N` | SSE stream of `docker logs --follow` for a Dokku app container |

## Running

The server runs as a systemd service — auto-starts on boot, auto-restarts on crash.

```bash
sudo systemctl status mission-control   # Check status
sudo systemctl restart mission-control  # Restart
journalctl -u mission-control -f        # Live logs
```

### Development

```bash
cd mission-control-vue
npm install
npm run dev          # Vite dev server on :5173, proxies API to :51763
```

### Production build

```bash
cd mission-control-vue
npm run build        # Outputs to ../dist/
sudo systemctl restart mission-control
```

## Mobile

Responsive design with breakpoints at 900px, 720px, and 480px. At ≤720px, top-bar tabs collapse into a hamburger drawer menu. The Content tab stacks vertically (sidebar above preview). DokkuGrid collapses from 3→2→1 column. Kanban board collapses from 7→4→2 columns.

## Adding a Server

Edit `servers.json`:

```json
{
  "servers": [
    {
      "name": "my-new-vps",
      "display": "My New VPS",
      "host": "my-vps-hostname",
      "type": "vps",
      "has_dokku": false,
      "health_source": "ssh",
      "cron_label": "MY JOBS",
      "notes": "Optional description"
    }
  ]
}
```

Restart the service. The Servers tab picks up the new entry automatically.

## Design

Vladoms-design — dark tactical HUD aesthetic. Not generic glassmorphism. Not Material. Not Tailwind.

- **Surfaces**: `#05080b` void → `#111923` elevated
- **Primary accent**: `#ff3b1f` (red)
- **Tone**: dry, tactical — `UPLINK // SYNCED`, `MISSION CONTROL`, `TOKEN LEDGER`
- **Glyphs**: `◆ ▶ › → ─` — no emoji
- **Background**: CSS grid layer (64px), red/cyan radial vignette, CRT scanlines
