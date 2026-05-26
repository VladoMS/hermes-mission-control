# AGENTS.md — Operator's Manual for Hermes Mission Control

Read this before editing any file in this repo.

## 0. What this is

A single-pilot dashboard for Hermes Agent. Not a multi-agent system. Not "AgentOS." One ADA, six profiles, one operator (Vladislav).

The dashboard reads Hermes data sources read-only. The only writes are to the local `dashboard.db` (retention cache) and `~/.hermes/content/` (document save endpoint).

## 1. Tech constraints (DO NOT CHANGE)

- **No build step.** Single `index.html` + `server.py`. No React, no Babel, no npm, no bundler.
- **Python stdlib only.** `http.server`, `sqlite3`, `json`, `subprocess`, `threading`, `os`, `time`. No pip packages.
- **Vanilla JS only.** No frameworks. No jQuery. Use the patterns already in the file.
- **Vladoms-design** aesthetic. Not generic glassmorphism. Not Material. Not Tailwind.
- **No emoji.** Use geometric glyphs: `◆ ▶ › → ─`
- **SSE + polling.** SSE on `/events` every 5s. Polling fallback every 8s. Both must work.

## 2. File layout

```
server.py              — Backend: HTTP server, data readers, snapshot assembly, SSE
index.html             — Frontend: HTML structure, CSS (vladoms tokens), JS (tab renderers)
dashboard.db           — Auto-created by server.py. 30-day snapshot retention. Never commit.
backups/               — Pre-change backups. Server auto-saves before modifications.
start.sh / stop.sh     — Launch scripts
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

`HERMES_HOME` is resolved by `_resolve_hermes_home()` — handles the case where the server runs under a kanban profile with nested HOME.

## 4. Gotchas (real bugs we hit — don't repeat)

### 4.1 Parallel file editing is forbidden
If multiple kanban tasks need to edit `server.py` or `index.html`, chain them sequentially via parent→child dependencies. Never make them parallel siblings with the same parent. We discovered this when Phases 3-8 all edited the same files simultaneously during the initial build — multiple workers racing on the same files produced merge conflicts, lost code, and syntax errors.

### 4.2 SSE event type mismatch
The server MUST send `event: snapshot\ndata: {json}\n\n`. If it sends only `data: {json}\n\n` (no event field), the frontend's `addEventListener('snapshot', ...)` will never fire — data arrives but `window.__mc.snapshot` stays null.

### 4.3 Script load order matters
`init()` was originally an immediate IIFE that ran before the `Profiles`, `Kanban`, and `ContentTab` variables were defined (they were lower in the file). Changed to a `DOMContentLoaded` listener. Any new top-level render calls MUST follow the same pattern — defer to DOMContentLoaded, or place them at the very end of the script.

### 4.4 Change detection prevents animation spam
Every SSE push triggers render calls. If a renderer replaces DOM content or redraws a canvas unconditionally, it produces visible flicker/reset. Always compare current data with previous before touching DOM. Patterns in use:
- `_activityFeedPrev` — JSON string comparison for activity feed rows
- `_sparklinePrev` — comma-joined point comparison for sparkline canvas
- `tpTotal.textContent !== String(newTotal)` — text-only-updates-when-different

### 4.5 SQLite must be read-only on Hermes DBs
`kanban.db` and all `state.db` files open with `file:path?mode=ro` + `PRAGMA query_only=1`. Never write to these — the running Hermes process owns them. The only writable DB is `dashboard.db` (owned exclusively by this server).

### 4.6 `glm-5.1` model returns `None` timestamps
Some sessions in `state.db` have `model: "glm-5.1"` with `started_at: null`. The sessions renderer must handle null timestamps gracefully (show `—`).

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

Background layers: `.bg-grid` (64px), `.bg-vignette` (red/cyan radial), `.bg-scanlines` (CRT, toggleable). All GPU-promoted with `transform: translateZ(0)` + `contain: paint`.

## 6. Conventions

- **Comments explain.** Server functions have docstrings. JS blocks have section banners.
- **Tone**: dry tactical HUD. Not marketing copy. Not "warm and friendly."
- **CSS is inline** in `index.html` `<style>` block. No external stylesheets.
- **Google Fonts** loaded via CDN `<link>` in `<head>`.
- **Version badge** in TopBar. Increment manually on meaningful changes.
- **Backup before changes.** `./backups/index_v{ver}_{ISO}.html`.
- **Server runs on `0.0.0.0:51763`.** Firewall restricts to Tailscale CGNAT only. Never expose to public internet.
