# Hermes Mission Control

Tactical HUD dashboard for [Hermes Agent](https://hermes-agent.nousresearch.com) — a single pilot's live ops console built with the vladoms-design aesthetic (EVE Online inspired).

**URL**: `http://100.67.254.90:51763/` (Tailscale only)

## Tabs

| Tab | Data Source | Description |
|-----|------------|-------------|
| **Overview** | gateway_state.json, state.db, kanban.db, /proc | Live ops console with radar, VPS health (hermes + prod), throughput sparkline, activity feed |
| **Profiles** | profiles/*/state.db, profile.yaml, config.yaml | 6 profile cards (default, coder, writer, researcher, devops, creative) with per-profile stats |
| **Kanban** | kanban.db (read-only) | 3-column board: Backlog · In Progress · Done |
| **Cron** | cron/jobs.json, /etc/crontab, /etc/cron.d | All scheduled jobs with human-readable schedules and next-run estimates |
| **Sessions** | state.db (all profiles) | 50-session list, token ledger with per-model/per-profile breakdown, filter bar |
| **Content** | ~/.hermes/content/<profile>/*.md | Document viewer — sidebar by profile, markdown preview with view/edit modes |

## Architecture

```
server.py          — Python stdlib backend (http.server, sqlite3, json)
index.html         — Single-page frontend (vanilla HTML/CSS/JS, no React, no build step)
dashboard.db       — Local SQLite retention DB (30-day snapshot history for instant page load)
```

- **Backend**: `ThreadingHTTPServer` on `0.0.0.0:51763`. SSE on `/events` every 5s, polling fallback every 8s.
- **Frontend**: vladoms-design tokens — `#05080b` void background, `#ff3b1f` primary accent, Saira Condensed + IBM Plex Sans + JetBrains Mono fonts. No emoji, geometric glyphs only (`◆ ▶ › → ─`).
- **Data**: All Hermes data sources read-only. SQLite opens with `file:path?mode=ro` + `PRAGMA query_only=1`. Local `dashboard.db` is the sole writable DB — owned exclusively by the dashboard process.
- **VPS health**: Hermes VPS via `/proc` reads, prod VPS via SSH (cached 30s TTL to avoid hammering).

## Running

```bash
cd /home/hermes/mission-control
./start.sh        # Launches server in background
./stop.sh         # Kills the server
```

## Design

Built to the vladoms-design spec — not generic glassmorphism. The tactical HUD voice is dry and direct: `UPLINK // SYNCED`, `DESIG / ADA-01`, `KANBAN QUEUE`, `TOKEN LEDGER`.
