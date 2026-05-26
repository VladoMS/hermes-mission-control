# Hermes Mission Control

Tactical HUD dashboard for [Hermes Agent](https://hermes-agent.nousresearch.com) — a single pilot's live ops console built with the vladoms-design aesthetic (EVE Online inspired).

**URL**: `http://100.67.254.90:51763/` (Tailscale only)

## Tabs

| Tab | Data Source | Description |
|-----|------------|-------------|
| **Overview** | gateway_state.json, state.db, kanban.db, /proc | Live ops console with radar, throughput sparkline, activity feed |
| **Profiles** | profiles/*/state.db, profile.yaml, config.yaml | 6 profile cards (default, coder, writer, researcher, devops, creative) with per-profile stats |
| **Kanban** | kanban.db (read-only) | 7-column board: Triage · To Do · Ready · Running · Blocked · Done · Archived |
| **Servers** | servers.json, /proc, SSH, dokku, crontabs | Dynamic server cards with CPU/RAM/Disk health bars, collapsible cron jobs, Dokku apps and containers |
| **Sessions** | state.db (all profiles) | 50-session list, token ledger with per-model/per-profile breakdown, pie chart, filter bar |
| **Content** | ~/.hermes/content/<profile>/*.md | Document viewer — sidebar by profile, markdown preview with view/edit modes |

## Architecture

```
server.py          — Python stdlib backend (http.server, sqlite3, json)
index.html         — Single-page frontend (vanilla HTML/CSS/JS, no React, no build step)
dashboard.db       — Local SQLite retention DB (30-day snapshot history for instant page load)
servers.json       — Server list config — add new servers by editing this file
```

- **Backend**: `ThreadingHTTPServer` on `0.0.0.0:51763`. SSE on `/events` every 5s, polling fallback every 8s.
- **Frontend**: vladoms-design tokens — `#05080b` void background, `#ff3b1f` primary accent, Saira Condensed + IBM Plex Sans + JetBrains Mono fonts. No emoji, geometric glyphs only (`◆ ▶ › → ─`).
- **Data**: All Hermes data sources read-only. SQLite opens with `file:path?mode=ro` + `PRAGMA query_only=1`. Local `dashboard.db` is the sole writable DB — owned exclusively by the dashboard process.
- **Servers tab**: Per-server health from `/proc` (local) or SSH (remote). Cron jobs from crontabs. Dokku data via `dokku apps:list` + `docker ps`. Server list driven by `servers.json` — add a new server by adding an entry and restarting.
- **Change detection**: Fingerprint-based — tabs skip DOM rebuild when data hasn't changed. Health bars update in-place without touching the rest of the UI.

## Running

The server runs as a systemd service — auto-starts on boot, auto-restarts on crash.

```bash
sudo systemctl status mission-control   # Check status
sudo systemctl restart mission-control  # Restart
journalctl -u mission-control -f        # Live logs
```

## Mobile

Responsive design with breakpoints at 900px, 720px, and 480px. At ≤720px, tabs collapse into a hamburger (☰) menu. The Content tab stacks vertically (sidebar above preview).

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
      "sort_order": 2,
      "has_dokku": false,
      "health_source": "ssh",
      "cron_label": "MY JOBS",
      "notes": "Optional description"
    }
  ]
}
```

Restart the service. The Servers tab will pick up the new entry automatically.

## Design

Built to the vladoms-design spec — not generic glassmorphism. The tactical HUD voice is dry and direct: `UPLINK // SYNCED`, `DESIG / ADA-01`, `KANBAN QUEUE`, `TOKEN LEDGER`.
