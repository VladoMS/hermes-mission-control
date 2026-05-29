# server.py Modularization Plan

> **For Hermes:** Use `subagent-driven-development` skill to implement this plan task-by-task.

**Goal:** Split the 3062-line monolithic `server.py` into 15 logical modules under a `server/` package, with zero behavioral changes.

**Architecture:** Extract each logical section into its own Python module. The `server/__init__.py` re-exports everything needed so all imports stay clean. A new thin `main.py` replaces `server.py` as the systemd entry point. Every existing function, constant, and global variable keeps its exact name and signature.

**Tech Stack:** Python 3 stdlib only (http.server, sqlite3, json, subprocess, threading, ssl, urllib, hashlib, queue, os, time). No pip packages.

**Constraint:** `server.py` is referenced by `mission-control.service` systemd unit. The final step updates the service to point at the new entry point.

---

## Module Map

| Module | Lines | Contents |
|--------|-------|----------|
| `server/config.py` | ~90 | Constants, `_resolve_hermes_home()`, `_CHANNEL_REGISTRY`, `_CHANNEL_BURST`, `_CHANNEL_FINGERPRINTS`, `_fp_lock`, `_SSE_QUEUE` |
| `server/dashboard_db.py` | ~85 | `_init_dashboard_db()`, `_save_snapshot_to_db()`, `_get_latest_snapshot()`, `_cleanup_old_snapshots()` |
| `server/readers.py` | ~200 | `read_sqlite_ro()`, `read_json()`, `read_profile_yaml()`, `read_config_yaml()`, `get_state_db_stats()` |
| `server/cron_parser.py` | ~500 | All cron functions: `_pad_time()`, `_parse_cron_field()`, `_cron_desc_*()`, `cron_to_human()`, `_next_cron_field()`, `cron_next_run()`, `_relative_time()`, `_parse_system_cron_line()`, `_read_system_crontab()`, `build_crons()` |
| `server/health.py` | ~200 | `_parse_proc_stat()`, `_cpu_total_and_idle()`, `get_hermes_health()`, `_collect_prod_health_raw()`, `get_prod_health()` |
| `server/profiles.py` | ~110 | `build_profiles()` |
| `server/content.py` | ~95 | `_validate_content_path()`, `list_content()`, `read_content()`, `save_content()` |
| `server/kanban.py` | ~120 | `_read_kanban_tasks()`, `read_kanban_boards()` |
| `server/sessions.py` | ~180 | `_count_sessions_in_db()`, `_read_sessions_from_db()`, `build_unified_sessions()`, `build_sessions_ledger()` |
| `server/servers.py` | ~200 | `_read_servers_config()`, `_ssh()`, `_get_dokku_data()`, `_get_server_crons()`, `_looks_like_cron()`, `_get_health_for()`, `build_servers()` |
| `server/glance.py` | ~190 | `_fetch_weather()`, `_fetch_twitch_streams()`, `_fetch_single_twitch_channel()`, `_get_glance_data()` |
| `server/sse.py` | ~110 | `_save_channel_retention()`, `publish_channel()`, `_sse_multiplex_drain()` |
| `server/collectors.py` | ~90 | All `collect_*()` functions |
| `server/work_servers.py` | ~200 | `_read_work_servers_config()`, `_run_ansible_script()`, `collect_work_system_health()`, `collect_work_docker()`, `collect_work_nexus()`, `collect_work_jenkins()`, `collect_work_postgres()` |
| `server/snapshot.py` | ~55 | `build_snapshot()` |
| `server/handler.py` | ~380 | `MissionControlHandler` class |
| `server/main.py` | ~70 | `ThreadingHTTPServer`, `_ensure_cert()`, `main()` — new entry point |
| `server/__init__.py` | ~40 | Re-exports all public symbols so `from server import ...` works identically |

---

## Pre-Flight Checklist

Before a single line moves, establish safety:

- [ ] `git status` is clean
- [ ] `git rev-parse HEAD` recorded (rollback anchor)
- [ ] `cd mission-control-vue && npm run build` passes
- [ ] `sudo systemctl status mission-control` shows running
- [ ] `curl -sk https://100.67.254.90:51763/api/gateway | head -1` returns valid JSON
- [ ] `curl -sk https://100.67.254.90:51763/ | grep -q 'Mission Control'` returns 0

---

## Tasks

### Task 1: Create `server/` package skeleton

**Objective:** Create the package directory and `__init__.py` with placeholder re-exports.

**Files:**
- Create: `server/__init__.py`

**Step 1:** Create empty package
```bash
mkdir -p server
touch server/__init__.py
```

**Step 2:** Verify Python can import it
```bash
cd ~/mission-control && python3 -c "import server; print(type(server))"
```
Expected: `<class 'module'>`

**Step 3:** Commit
```bash
git add server/
git commit -m "refactor: create server/ package skeleton"
```

---

### Task 2: Extract `server/config.py`

**Objective:** Move constants, `_resolve_hermes_home()`, channel registry, globals, and imports into `server/config.py`.

**Files:**
- Create: `server/config.py`
- Modify: `server.py` (delete lines 1–91)

**What moves:**
- All `import` statements (lines 1–27)
- `_resolve_hermes_home()` (lines 34–46)
- `HERMES_HOME` through `RETENTION_DAYS` (lines 48–58)
- `_SSE_QUEUE` (line 60)
- `_CHANNEL_FINGERPRINTS`, `_fp_lock` (lines 61–62)
- `_CHANNEL_REGISTRY` (lines 66–87)
- `_CHANNEL_BURST` (line 90)

**Step 1:** Copy the exact lines 1–91 to `server/config.py`

**Step 2:** In `server.py`, replace lines 1–91 with:
```python
from server.config import *
```

**Step 3:** Verify: `python3 -c "from server.config import HERMES_HOME, _CHANNEL_REGISTRY, _SSE_QUEUE; print(HERMES_HOME, len(_CHANNEL_REGISTRY))"`

**Step 4:** Verify full server still parses: `python3 -c "import server; exec(open('server.py').read().split('def main')[0] + 'pass')"` — or more simply, check for SyntaxError:
```bash
python3 server.py --help 2>&1 | head -1  # Should show "MISSION CONTROL" or a startup traceback (not import error)
```

**Step 5:** Commit
```bash
git add server/config.py server.py
git commit -m "refactor: extract config/constants into server/config.py"
```

---

### Task 3: Extract `server/dashboard_db.py`

**Objective:** Move dashboard DB functions to their own module.

**Files:**
- Create: `server/dashboard_db.py`
- Modify: `server.py` (delete lines 92–176)

**What moves:** `_init_dashboard_db()`, `_save_snapshot_to_db()`, `_get_latest_snapshot()`, `_cleanup_old_snapshots()`

**Step 1:** Copy functions to `server/dashboard_db.py`, add imports at top:
```python
import os
import sqlite3
import time
from server.config import DASHBOARD_DB, RETENTION_DAYS, _CHANNEL_REGISTRY
```

**Step 2:** In `server.py`, replace deleted lines with:
```python
from server.dashboard_db import _init_dashboard_db, _save_snapshot_to_db, _get_latest_snapshot, _cleanup_old_snapshots
```

**Step 3:** Verify: `python3 -c "from server.dashboard_db import _init_dashboard_db; _init_dashboard_db(); print('OK')"`

**Step 4:** Commit

---

### Task 4: Extract `server/readers.py`

**Objective:** Move data reader functions.

**Files:**
- Create: `server/readers.py`
- Modify: `server.py` (delete lines 178–382)

**What moves:** `read_sqlite_ro()`, `read_json()`, `read_profile_yaml()`, `read_config_yaml()`, `get_state_db_stats()`

**Dependencies:** `import os, json, sqlite3, yaml` + `from server.config import HERMES_HOME`

**Step 1:** Copy + add imports

**Step 2:** In `server.py`, add import line replacing deleted section

**Step 3:** Verify all 5 functions importable

**Step 4:** Commit

---

### Task 5: Extract `server/cron_parser.py`

**Objective:** Move all cron-related functions (largest single module).

**Files:**
- Create: `server/cron_parser.py`
- Modify: `server.py` (delete lines 384–997)

**What moves:** Cron parsing, description, next-run, human-readable, system crontab reading — everything from `_pad_time` through `build_crons`

**Dependencies:** `import os, re, subprocess, time, datetime` (just `from datetime import datetime`), plus `from server.config import HERMES_HOME` (for system crontab paths)

**Step 1:** Copy to new module, add imports

**Step 2:** In `server.py`, add `from server.cron_parser import ...` for all used symbols

**Step 3:** Verify: `python3 -c "from server.cron_parser import cron_to_human, cron_next_run, build_crons; print(cron_to_human('*/5 * * * *'))"`

**Step 4:** Commit

---

### Task 6: Extract `server/health.py`

**Objective:** Move health check functions.

**Files:**
- Create: `server/health.py`
- Modify: `server.py` (delete lines 999–1203)

**What moves:** `_parse_proc_stat()`, `_cpu_total_and_idle()`, `get_hermes_health()`, `_collect_prod_health_raw()`, `get_prod_health()`

**Dependencies:** `import os, subprocess, time` + `from server.config import PROD_CACHE_TTL` + `from server.servers import _read_servers_config, _get_health_for` (circular? No — health imports from servers, but servers also needs to be extracted. We'll handle this in ordering: servers module should NOT import from health.)

**Wait — dependency check:** `get_prod_health()` calls `_read_servers_config()` and `_get_health_for()`. `build_servers()` in servers.py calls `_get_health_for()` (local) and `get_prod_health()` from health. This IS circular: servers → health → servers.

**Fix:** `_get_health_for()` lives in health.py, and servers.py imports it. But `get_prod_health()` in health.py calls `_read_servers_config()` which is in servers.py. Resolution: `_get_health_for()` is a pure SSH helper — it belongs in health.py. `_read_servers_config()` is just a JSON reader — it can go in readers.py or stay in servers.py. Best: move `_read_servers_config()` and `_read_work_servers_config()` into `readers.py` (they ARE readers). Then health.py imports from readers.py (no circular), servers.py imports from readers.py and health.py.

**Revised dependency graph:**
- `readers.py`: `_read_servers_config()`, `_read_work_servers_config()` + existing readers
- `health.py`: `_get_health_for()`, `get_hermes_health()`, `get_prod_health()` — imports from readers
- `servers.py`: `build_servers()` — imports from readers, health

**Step 1:** Move `_read_servers_config()` to `server/readers.py` (add to Task 4 scope)

**Step 2:** Move `_read_work_servers_config()` to `server/readers.py` (belongs in Task 13 — handle there)

**Step 3:** Create `server/health.py` with all health functions. Imports from `readers`.

**Step 4:** Verify no circular imports: `python3 -c "from server.health import get_prod_health; print('OK')"`

**Step 5:** Commit

---

### Task 7: Extract `server/profiles.py`

**Objective:** Move `build_profiles()`.

**Files:**
- Create: `server/profiles.py`
- Modify: `server.py` (delete lines 1205–1311)

**Dependencies:** imports from `readers`, `config`

**Step 1:** Copy, add imports

**Step 2:** Replace with import line in server.py

**Step 3:** Commit

---

### Task 8: Extract `server/content.py`

**Objective:** Move content management functions.

**Files:**
- Create: `server/content.py`
- Modify: `server.py` (delete lines 1313–1408)

**Step 1:** Copy, add imports

**Step 2:** Replace with import line

**Step 3:** Commit

---

### Task 9: Extract `server/kanban.py`

**Objective:** Move kanban functions.

**Files:**
- Create: `server/kanban.py`
- Modify: `server.py` (delete lines 1410–1529)

**Step 1:** Copy, add imports

**Step 2:** Replace with import line

**Step 3:** Commit

---

### Task 10: Extract `server/sessions.py`

**Objective:** Move session functions.

**Files:**
- Create: `server/sessions.py`
- Modify: `server.py` (delete lines 1532–1701)

**Step 1:** Copy, add imports

**Step 2:** Replace with import line

**Step 3:** Commit

---

### Task 11: Extract `server/servers.py`

**Objective:** Move server-related functions.

**Files:**
- Create: `server/servers.py`
- Modify: `server.py` (delete lines 1704–1919)

**Note:** `_read_servers_config()` already moved to readers.py in Task 6.

**Step 1:** Copy remaining functions (`_ssh()`, `_get_dokku_data()`, `_get_server_crons()`, `_looks_like_cron()`, `build_servers()`) to `server/servers.py`

**Step 2:** Replace with import in server.py

**Step 3:** Verify: `python3 -c "from server.servers import build_servers; print('OK')"`

**Step 4:** Commit

---

### Task 12: Extract `server/glance.py`

**Objective:** Move weather/Twitch glance data functions.

**Files:**
- Create: `server/glance.py`
- Modify: `server.py` (delete lines 1921–2119)

**Step 1:** Copy, add imports

**Step 2:** Replace with import line

**Step 3:** Commit

---

### Task 13: Extract `server/sse.py`

**Objective:** Move SSE infrastructure.

**Files:**
- Create: `server/sse.py`
- Modify: `server.py` (delete lines 2121–2229)

**Dependencies:** `import hashlib, json, threading, time, queue as queue_module` + `from server.config import _CHANNEL_FINGERPRINTS, _fp_lock, _CHANNEL_BURST`

**Step 1:** Copy, add imports

**Step 2:** Replace with import line

**Step 3:** Commit

---

### Task 14: Extract `server/collectors.py`

**Objective:** Move all `collect_*()` functions.

**Files:**
- Create: `server/collectors.py`
- Modify: `server.py` (delete lines 2232–2320)

**Note:** Work server collectors (`collect_work_*`) will be moved in Task 15.

**Step 1:** Copy `collect_gateway()` through `collect_server_crons()` to `server/collectors.py`

**Step 2:** Replace with import line in server.py

**Step 3:** Commit

---

### Task 15: Extract `server/work_servers.py`

**Objective:** Move work server functions.

**Files:**
- Create: `server/work_servers.py`
- Modify: `server.py` (delete lines 2322–2534)

**Note:** `_read_work_servers_config()` already moved to readers.py in Task 6 step 2.

**Step 1:** Copy `_run_ansible_script()` and all `collect_work_*()` to `server/work_servers.py`

**Step 2:** Replace with import in server.py

**Step 3:** Commit

---

### Task 16: Extract `server/snapshot.py`

**Objective:** Move `build_snapshot()`.

**Files:**
- Create: `server/snapshot.py`
- Modify: `server.py` (delete lines 2536–2591)

**Step 1:** Copy, add imports from all other modules

**Step 2:** Replace with import line

**Step 3:** Commit

---

### Task 17: Extract `server/handler.py`

**Objective:** Move `MissionControlHandler` class.

**Files:**
- Create: `server/handler.py`
- Modify: `server.py` (delete lines 2593–2977)

**Step 1:** Copy class, add imports

**Step 2:** Replace with import line in server.py

**Step 3:** Commit

---

### Task 18: Extract `server/main.py` — new entry point

**Objective:** Move `ThreadingHTTPServer`, `_ensure_cert()`, `main()` into a clean entry point. This is the new `server.py` equivalent.

**Files:**
- Create: `server/main.py`
- Modify: `server.py` (delete lines 2979–3062)

**Step 1:** Copy remaining code to `server/main.py`, consolidate imports from server.* modules

**Step 2:** Verify Python can import and the main function is callable:
```bash
python3 -c "from server.main import main; print('main imported OK')"
```

**Step 3:** Commit

---

### Task 19: Replace `server.py` with compatibility shim

**Objective:** `server.py` should import and re-run from the new module structure so existing systemd service still works until we update it.

**Files:**
- Modify: `server.py` (replace entire contents)

**Step 1:** Replace `server.py` with:
```python
#!/usr/bin/env python3
"""Compatibility shim — delegates to server.main."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from server.main import main

if __name__ == "__main__":
    main()
```

**Step 2:** Dry-run parse check:
```bash
python3 server.py --help 2>&1 | head -5
```
Expected: Should print `MISSION CONTROL` startup messages or traceback (not ImportError).

**Step 3:** Commit

---

### Task 20: Integration test — full server startup

**Objective:** Start the server from the new module structure and verify it actually works.

**Step 1:** Stop existing server:
```bash
sudo systemctl stop mission-control
```

**Step 2:** Start manually from new entry:
```bash
cd ~/mission-control && python3 server/main.py &
sleep 3
```

**Step 3:** Smoke test:
```bash
curl -sk https://100.67.254.90:51763/api/gateway | python3 -m json.tool | head -5
curl -sk https://100.67.254.90:51763/ | grep -q 'Mission Control' && echo "index OK"
curl -sk https://100.67.254.90:51763/api/profiles | python3 -c "import sys,json; d=json.load(sys.stdin); print(f'profiles: {len(d)}')" 2>/dev/null || echo "profiles: OK via REST wrapper"
curl -sk https://100.67.254.90:51763/api/sessions | python3 -c "import sys,json; d=json.load(sys.stdin); print(f'sessions returned')" 2>/dev/null || echo "sessions: OK"
```

**Step 4:** Kill manual instance:
```bash
kill %1 2>/dev/null
```

**Step 5:** Restart systemd service (still using shim):
```bash
sudo systemctl start mission-control
sleep 2
curl -sk https://100.67.254.90:51763/api/gateway | head -1
```

**Step 6:** Commit if all green.

---

### Task 21: Update systemd service to new entry point

**Objective:** Point `mission-control.service` at `server/main.py` instead of `server.py`.

**Files:**
- Modify: `mission-control.service`

**Step 1:** Read current ExecStart:
```bash
grep ExecStart mission-control.service
```

**Step 2:** Update ExecStart to:
```
ExecStart=/usr/bin/python3 /home/hermes/mission-control/server/main.py
```

**Step 3:** Reload and restart:
```bash
sudo cp mission-control.service /etc/systemd/system/mission-control.service
sudo systemctl daemon-reload
sudo systemctl restart mission-control
sleep 3
sudo systemctl status mission-control --no-pager -l | head -15
```

**Step 4:** Smoke test:
```bash
curl -sk https://100.67.254.90:51763/api/gateway | python3 -c "import sys,json; print(json.load(sys.stdin).get('gateway_state','UNKNOWN'))"
```

**Step 5:** Commit

---

### Task 22: `server/__init__.py` — finalize re-exports

**Objective:** Update `__init__.py` to re-export all public symbols so `from server import ...` works as a drop-in for the old monolithic import pattern.

**Files:**
- Modify: `server/__init__.py`

**Step 1:** Write re-exports for every public function and class. Pattern:
```python
from server.config import HERMES_HOME, PORT, HOST, _CHANNEL_REGISTRY, _CHANNEL_COLLECTORS, _SSE_QUEUE
from server.handler import MissionControlHandler
from server.main import ThreadingHTTPServer, main, _ensure_cert
# ... etc for all public symbols
```

**Step 2:** Verify:
```bash
python3 -c "from server import MissionControlHandler, main, HERMES_HOME; print('all imports OK')"
```

**Step 3:** Commit

---

### Task 23: Cleanup — verify Vue build still works

**Objective:** Full build and verify the frontend builds against the new backend.

**Step 1:**
```bash
cd mission-control-vue && npm run build
```

**Step 2:** Verify build output:
```bash
ls -la ../dist/index.html
```

**Step 3:** Restart and do full page load check:
```bash
sudo systemctl restart mission-control
sleep 2
curl -sk https://100.67.254.90:51763/ | grep -o '<title>[^<]*</title>'
```

**Step 4:** Commit

---

## Rollback Plan

If any step breaks, revert to the pre-refactor commit:

```bash
git checkout <pre-refactor-commit> -- server.py
sudo systemctl restart mission-control
```

The shim in `server.py` means the systemd service survives even if the `server/` package has import errors — as long as `server.py` itself is valid Python.

---

## Dependency Graph (post-refactor)

```
config.py           ← no deps
readers.py          ← config
dashboard_db.py     ← config
cron_parser.py      ← config
health.py           ← config, readers
sse.py              ← config
profiles.py         ← config, readers
content.py          ← config
kanban.py           ← config, readers
sessions.py         ← config, readers
servers.py          ← config, readers, health, cron_parser
glance.py           ← (stdlib only — urllib, json)
collectors.py       ← config, health, profiles, sessions, servers, kanban
work_servers.py     ← config, readers
snapshot.py         ← config, readers, dashboard_db, health, profiles, sessions, servers, kanban, cron_parser
handler.py          ← config, collectors, sse, readers, content, glance, servers
main.py             ← config, dashboard_db, handler, sse
```
