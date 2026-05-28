# Mission Control — Modular SSE Architecture Implementation Plan

> **For Hermes:** Use subagent-driven-development skill to implement this plan phase-by-phase.

**Goal:** Replace the monolithic 5s SSE pipeline with independent per-channel background threads, each publishing only when its data changes, at its own cadence. Add per-channel REST endpoints for the polling fallback.

**Architecture:** 10 background publisher threads → shared `queue.Queue` → SSE multiplexer drain loop. Frontend `snapshotStore` gains `patch(key, value)` for per-channel fingerprint-gated updates. Existing domain stores derive from the same reactive `data` unchanged.

**Tech Stack:** Python stdlib (`threading`, `queue`, `sqlite3`), Vue 3 (Composition API, Pinia), no new dependencies.

**Confirmed design decisions:**
- 10 individual threads (not pooled)
- Per-channel retention DB tables
- Per-channel REST endpoints for polling fallback
- Progressive load: Tier 1 bursts on connect, Tier 2-3 arrive on cadence
- Current Vue 3 codebase (migration complete)

---

## Phase 1: Backend — Publisher Framework

### Task 1.1: Add queue and channel registry to server.py

**Objective:** Create the shared `queue.Queue` and the channel registry that defines each channel's event type, interval, and collection function.

**Files:**
- Modify: `/home/hermes/mission-control/server.py` (top section, after line 51)

**Steps:**

**Step 1: Add imports and constants**

After line 23 (`from http import HTTPStatus`), add:

```python
import hashlib
import queue as queue_module
```

After line 47 (the `PROD_CACHE_TTL` line), add:

```python
# ── SSE Multiplexer ──────────────────────────────────────────────────────
_SSE_QUEUE = queue_module.Queue(maxsize=64)
_CHANNEL_FINGERPRINTS = {}   # {event_type: md5_hex}, guarded by _fp_lock
_fp_lock = threading.Lock()

# Channel registry: (event_type, interval_seconds, tier)
# Tier 1 = burst on connect, Tier 2-3 = arrive on cadence
_CHANNEL_REGISTRY = [
    # Tier 1 — Fast, frequent
    ("gateway",          5,   1),
    ("processes",        5,   1),
    ("hermes-health",    5,   1),
    ("sessions-ledger", 15,   1),
    # Tier 2 — Medium, moderate
    ("profiles",        60,   2),
    ("sessions",        30,   2),
    ("kanban",          30,   2),
    # Tier 3 — Slow, cached
    ("prod-health",     30,   3),
    ("dokku",           60,   3),
    ("server-crons",   300,   3),
]
```

**Step 2: Verify imports work**

```bash
cd /home/hermes/mission-control && python3 -c "
import hashlib
import queue
print('queue.Queue maxsize test:', queue.Queue(maxsize=64).maxsize)
# Import server to check no syntax errors
exec(open('server.py').read().split('def main')[0] + 'pass')
print('server.py top section: OK')
"
```

**Step 3: Commit**

```bash
cd /home/hermes/mission-control
git add server.py
git commit -m "feat: add SSE multiplexer queue and channel registry"
```

---

### Task 1.2: Add generic publisher function

**Objective:** Create `publish_channel()` — the template function all 10 publisher threads will use. Handles collection, fingerprint comparison, queue push, and retention DB save.

**Files:**
- Modify: `/home/hermes/mission-control/server.py` (insert before the `build_snapshot` section)

**Steps:**

**Step 1: Add the publisher template**

Insert the following function before `build_snapshot()` (before line 2059):

```python
def publish_channel(event_type, collect_fn, interval, queue, retention_db_path=None):
    """
    Generic channel publisher — runs in its own thread.
    
    Each cycle:
      1. Collect data via collect_fn() (must be thread-safe)
      2. MD5-fingerprint the JSON output
      3. If changed → push to queue + optionally save to retention DB
      4. Sleep for interval seconds
    
    Thread-safe: only touches its own fingerprint entry (guarded by _fp_lock)
    and the shared queue (thread-safe by design).
    """
    global _CHANNEL_FINGERPRINTS
    last_fp = None
    while True:
        try:
            data = collect_fn()
            payload = json.dumps(data, default=str, sort_keys=True)
            fp = hashlib.md5(payload.encode()).hexdigest()
            
            with _fp_lock:
                if fp != _CHANNEL_FINGERPRINTS.get(event_type):
                    _CHANNEL_FINGERPRINTS[event_type] = fp
                    changed = True
                else:
                    changed = False
            
            if changed:
                # Push to SSE queue (non-blocking — drops if queue full)
                try:
                    queue.put_nowait((event_type, payload))
                except queue_module.Full:
                    pass  # Client too slow, drop this push — next cycle will catch up
                
                # Save to retention DB (best-effort, non-blocking)
                if retention_db_path:
                    try:
                        _save_channel_retention(event_type, payload, retention_db_path)
                    except Exception:
                        pass
        except Exception:
            # Log but don't crash the publisher thread
            pass
        time.sleep(interval)
```

**Step 2: Add retention DB helper for per-channel saves**

Insert after `publish_channel()`:

```python
def _save_channel_retention(event_type, payload, db_path):
    """Save a single channel's data to its retention table. Creates table if needed."""
    import sqlite3 as _sql
    table_name = f"retention_{event_type.replace('-', '_')}"
    db = _sql.connect(db_path)
    db.execute("PRAGMA journal_mode=WAL")
    db.execute(f"""
        CREATE TABLE IF NOT EXISTS {table_name} (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp REAL NOT NULL,
            payload TEXT NOT NULL
        )
    """)
    db.execute(
        f"INSERT INTO {table_name} (timestamp, payload) VALUES (?, ?)",
        (time.time(), payload)
    )
    # Keep only last 1000 entries per channel
    db.execute(f"""
        DELETE FROM {table_name} WHERE id NOT IN (
            SELECT id FROM {table_name} ORDER BY id DESC LIMIT 1000
        )
    """)
    db.commit()
    db.close()
```

**Step 3: Verify the function compiles**

```bash
cd /home/hermes/mission-control && python3 -c "
import ast
with open('server.py') as f:
    tree = ast.parse(f.read())
print('server.py compiles OK,', len([n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)]), 'functions')
"
```

**Step 4: Commit**

```bash
cd /home/hermes/mission-control
git add server.py
git commit -m "feat: add publish_channel() template and per-channel retention"
```

---

### Task 1.3: Add SSE drain loop for multiplexed events

**Objective:** Create `_sse_multiplex_drain()` — the function the SSE handler calls instead of the old `build_snapshot()` + sleep loop. It drains the shared queue and writes named events.

**Files:**
- Modify: `/home/hermes/mission-control/server.py` (insert before `MissionControlHandler` class)

**Steps:**

**Step 1: Add the drain function**

Insert before the `MissionControlHandler` class definition (before line 2120):

```python
def _sse_multiplex_drain(wfile, flush_fn, queue, timeout=0.5):
    """
    Drain the shared SSE queue, writing named events to the client.
    Called from _serve_sse() in a loop.
    
    Blocks up to `timeout` seconds waiting for the next event.
    Returns True if at least one event was written, False if timeout elapsed.
    
    Handles BrokenPipeError/ConnectionResetError by re-raising to caller.
    """
    try:
        event_type, payload = queue.get(timeout=timeout)
        msg = f"event: {event_type}\ndata: {payload}\n\n"
        wfile.write(msg.encode("utf-8"))
        flush_fn()
        return True
    except queue_module.Empty:
        # Send a heartbeat comment to keep the connection alive
        wfile.write(b": heartbeat\n\n")
        flush_fn()
        return False
```

**Step 2: Verify the function compiles**

```bash
cd /home/hermes/mission-control && python3 -c "
import ast
with open('server.py') as f:
    tree = ast.parse(f.read())
print('server.py compiles OK')
"
```

**Step 3: Commit**

```bash
cd /home/hermes/mission-control
git add server.py
git commit -m "feat: add _sse_multiplex_drain() for queue-based SSE"
```

---

## Phase 2: Backend — Extract All Channels

### Task 2.1: Extract `collect_gateway()` 

**Objective:** Pull the gateway state reader out of `build_snapshot()` into a standalone function.

**Files:**
- Modify: `/home/hermes/mission-control/server.py`

**Steps:**

**Step 1: Add `collect_gateway()` function**

Insert before `publish_channel()`:

```python
def collect_gateway():
    """Collect gateway state. Returns dict, never raises."""
    gw = read_json(os.path.join(HERMES_HOME, "gateway_state.json"))
    if gw is None:
        return {"error": "gateway_state.json: read failed", "data": {}}
    return {"data": gw}
```

**Step 2: Verify it works**

```bash
cd /home/hermes/mission-control && python3 -c "
import json, sys
sys.path.insert(0, '.')
exec(open('server.py').read().split('def main')[0])
result = collect_gateway()
print('gateway version:', result.get('data', {}).get('version', 'unknown'))
print('OK')
"
```

**Step 3: Commit**

```bash
cd /home/hermes/mission-control
git add server.py
git commit -m "feat: extract collect_gateway() channel"
```

---

### Task 2.2: Extract `collect_processes()`

**Objective:** Pull the processes reader out of `build_snapshot()`.

**Files:**
- Modify: `/home/hermes/mission-control/server.py`

**Steps:**

**Step 1: Add `collect_processes()` function**

```python
def collect_processes():
    """Collect managed process list. Returns list, never raises."""
    procs = read_json(os.path.join(HERMES_HOME, "processes.json"))
    return {"processes": procs if procs is not None else []}
```

**Step 2: Verify**

```bash
cd /home/hermes/mission-control && python3 -c "
exec(open('server.py').read().split('def main')[0])
result = collect_processes()
print('process count:', len(result.get('processes', [])))
print('OK')
"
```

**Step 3: Commit**

```bash
cd /home/hermes/mission-control
git add server.py
git commit -m "feat: extract collect_processes() channel"
```

---

### Task 2.3: Extract `collect_hermes_health()`

**Objective:** Wrap the existing `get_hermes_health()` into a channel-compatible collector.

**Files:**
- Modify: `/home/hermes/mission-control/server.py`

**Steps:**

**Step 1: Add `collect_hermes_health()` wrapper**

```python
def collect_hermes_health():
    """Collect local VPS health. Returns dict, never raises."""
    errors = []
    result = get_hermes_health(errors)
    return {"health": result, "errors": errors}
```

**Step 2: Verify**

```bash
cd /home/hermes/mission-control && python3 -c "
exec(open('server.py').read().split('def main')[0])
result = collect_hermes_health()
print('hermes cpu_pct:', result['health'].get('cpu_pct'))
print('OK')
"
```

**Step 3: Commit**

```bash
cd /home/hermes/mission-control
git add server.py
git commit -m "feat: extract collect_hermes_health() channel"
```

---

### Task 2.4: Extract `collect_sessions_ledger()`

**Objective:** Pull the sessions ledger (COUNT queries + token totals) into a standalone collector. This is the aggregate — separate from the session list.

**Files:**
- Modify: `/home/hermes/mission-control/server.py`

**Steps:**

**Step 1: Add `collect_sessions_ledger()` function**

```python
def collect_sessions_ledger():
    """Collect aggregated session counts and token totals from all state.dbs.
    Returns the same structure as build_sessions_ledger() but collected independently."""
    profiles = build_profiles([])  # silent — errors go to a discard list
    unified, total_count = build_unified_sessions(profiles, [])
    ledger = build_sessions_ledger(unified, total_count)
    return ledger
```

**Step 2: Verify**

```bash
cd /home/hermes/mission-control && python3 -c "
exec(open('server.py').read().split('def main')[0])
result = collect_sessions_ledger()
print('session_count:', result.get('session_count'))
print('total_tokens:', result.get('total_tokens'))
print('OK')
"
```

**Step 3: Commit**

```bash
cd /home/hermes/mission-control
git add server.py
git commit -m "feat: extract collect_sessions_ledger() channel"
```

---

### Task 2.5: Extract `collect_profiles()`

**Objective:** Wrap the existing `build_profiles()` into a channel-compatible collector.

**Files:**
- Modify: `/home/hermes/mission-control/server.py`

**Steps:**

**Step 1: Add `collect_profiles()` function**

```python
def collect_profiles():
    """Collect profile list with state_db_stats. Returns dict."""
    errors = []
    profiles = build_profiles(errors)
    return {"profiles": profiles, "errors": errors}
```

**Step 2: Verify**

```bash
cd /home/hermes/mission-control && python3 -c "
exec(open('server.py').read().split('def main')[0])
result = collect_profiles()
print('profile count:', len(result.get('profiles', [])))
for p in result['profiles']:
    print(f'  {p[\"name\"]}: active={p.get(\"state_db_stats\",{}).get(\"active_sessions\",\"?\")}')
print('OK')
"
```

**Step 3: Commit**

```bash
cd /home/hermes/mission-control
git add server.py
git commit -m "feat: extract collect_profiles() channel"
```

---

### Task 2.6: Extract `collect_sessions()`

**Objective:** Pull the session list (top 50) into a standalone collector. This is separate from the ledger — the ledger has COUNTS, this has the actual rows.

**Files:**
- Modify: `/home/hermes/mission-control/server.py`

**Steps:**

**Step 1: Add `collect_sessions()` function**

```python
def collect_sessions():
    """Collect unified session list (top 50 across all profiles).
    Returns the capped list — the uncapped count is in sessions_ledger."""
    profiles = build_profiles([])
    unified, _ = build_unified_sessions(profiles, [])
    return {"sessions": unified}
```

**Step 2: Verify**

```bash
cd /home/hermes/mission-control && python3 -c "
exec(open('server.py').read().split('def main')[0])
result = collect_sessions()
print('session list length:', len(result.get('sessions', [])))
print('OK')
"
```

**Step 3: Commit**

```bash
cd /home/hermes/mission-control
git add server.py
git commit -m "feat: extract collect_sessions() channel"
```

---

### Task 2.7: Extract `collect_kanban()`

**Objective:** Wrap the existing `read_kanban_boards()` into a channel collector.

**Files:**
- Modify: `/home/hermes/mission-control/server.py`

**Steps:**

**Step 1: Add `collect_kanban()` function**

```python
def collect_kanban():
    """Collect kanban boards. Returns dict with boards key."""
    errors = []
    boards = read_kanban_boards(errors)
    return {"boards": boards, "errors": errors}
```

**Step 2: Verify**

```bash
cd /home/hermes/mission-control && python3 -c "
exec(open('server.py').read().split('def main')[0])
result = collect_kanban()
boards = result.get('boards', {})
print('board count:', len(boards))
for name, b in boards.items():
    print(f'  {name}: {b.get(\"task_count\", 0)} tasks')
print('OK')
"
```

**Step 3: Commit**

```bash
cd /home/hermes/mission-control
git add server.py
git commit -m "feat: extract collect_kanban() channel"
```

---

### Task 2.8: Extract `collect_prod_health()`

**Objective:** Wrap the existing `get_prod_health()` (already TTL-cached) into a channel collector.

**Files:**
- Modify: `/home/hermes/mission-control/server.py`

**Steps:**

**Step 1: Add `collect_prod_health()` function**

```python
def collect_prod_health():
    """Collect prod VPS health (SSH, TTL-cached). Returns dict."""
    errors = []
    health = get_prod_health(errors)
    return {"health": health, "errors": errors}
```

**Step 2: Verify**

```bash
cd /home/hermes/mission-control && python3 -c "
exec(open('server.py').read().split('def main')[0])
result = collect_prod_health()
print('ssh_ok:', result['health'].get('ssh_ok'))
print('cpu_pct:', result['health'].get('cpu_pct'))
print('OK')
"
```

**Step 3: Commit**

```bash
cd /home/hermes/mission-control
git add server.py
git commit -m "feat: extract collect_prod_health() channel"
```

---

### Task 2.9: Extract `collect_dokku()` and `collect_server_crons()`

**Objective:** Wrap the existing `_get_dokku_data()` and `_get_server_crons()` into channel collectors.

**Files:**
- Modify: `/home/hermes/mission-control/server.py`

**Steps:**

**Step 1: Add both collector functions**

```python
def collect_dokku():
    """Collect Dokku app/container data from prod (SSH). Returns dict."""
    servers_cfg = _read_servers_config()
    for srv in servers_cfg:
        if srv.get("has_dokku"):
            data = _get_dokku_data(srv["host"])
            if data:
                return {"server": srv["name"], "dokku": data}
    return {"server": None, "dokku": None}


def collect_server_crons():
    """Collect server cron jobs. Returns dict."""
    servers_cfg = _read_servers_config()
    crons_by_server = {}
    errors = []
    for srv in servers_cfg:
        crons_by_server[srv["name"]] = _get_server_crons(srv["host"], errors)
    return {"crons": crons_by_server, "errors": errors}
```

**Step 2: Verify**

```bash
cd /home/hermes/mission-control && python3 -c "
exec(open('server.py').read().split('def main')[0])
# These may be slow (SSH) but should not crash
dokku = collect_dokku()
print('dokku server:', dokku.get('server'))
print('dokku apps:', len(dokku.get('dokku', {}).get('apps', [])) if dokku.get('dokku') else 'N/A')

crons = collect_server_crons()
print('cron servers:', list(crons.get('crons', {}).keys()))
print('OK')
" 2>&1 | head -10
```

**Step 3: Commit**

```bash
cd /home/hermes/mission-control
git add server.py
git commit -m "feat: extract collect_dokku() and collect_server_crons() channels"
```

---

## Phase 3: Backend — SSE Multiplexer + REST Endpoints

### Task 3.1: Wire publisher threads in main()

**Objective:** Start all 10 publisher threads from `main()`, passing the correct collector function and interval.

**Files:**
- Modify: `/home/hermes/mission-control/server.py` (`main()` function near line 2397)

**Steps:**

**Step 1: Build the channel-to-collector mapping**

Add this dictionary after the `_CHANNEL_REGISTRY` list:

```python
_CHANNEL_COLLECTORS = {
    "gateway":          collect_gateway,
    "processes":        collect_processes,
    "hermes-health":    collect_hermes_health,
    "sessions-ledger":  collect_sessions_ledger,
    "profiles":         collect_profiles,
    "sessions":         collect_sessions,
    "kanban":           collect_kanban,
    "prod-health":      collect_prod_health,
    "dokku":            collect_dokku,
    "server-crons":     collect_server_crons,
}
```

**Step 2: Modify `main()` to start publisher threads**

Replace the current `main()` body (lines 2397-2416) with:

```python
def main():
    _init_dashboard_db()
    _cleanup_old_snapshots()
    
    # Start channel publisher threads
    _publisher_threads = []
    for event_type, interval, tier in _CHANNEL_REGISTRY:
        collector = _CHANNEL_COLLECTORS.get(event_type)
        if collector is None:
            print(f"  WARNING: no collector for channel '{event_type}' — skipping")
            continue
        t = threading.Thread(
            target=publish_channel,
            args=(event_type, collector, interval, _SSE_QUEUE, DASHBOARD_DB),
            daemon=True,
            name=f"ch-{event_type}"
        )
        t.start()
        _publisher_threads.append(t)
        print(f"  ▶ publisher: {event_type} every {interval}s (tier {tier})")
    
    print(f"  ▶ {len(_publisher_threads)} channel publishers started")
    
    # Start HTTP server
    server = ThreadingHTTPServer((HOST, PORT), MissionControlHandler)
    print(f"\n▶ MISSION CONTROL listening on {HOST}:{PORT}")
    print(f"  GET /                → index.html")
    print(f"  GET /api/snapshot    → legacy full snapshot (polling fallback)")
    print(f"  GET /api/gateway     → per-channel REST endpoints")
    print(f"  GET /api/sessions    → ... (all 10 channels)")
    print(f"  GET /api/content     → document list")
    print(f"  GET /api/content/get → read document")
    print(f"  POST /api/content/save → save document")
    print(f"  GET /events          → SSE multiplexed stream")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n▼ Shutting down.")
        server.shutdown()
```

**Step 3: Verify startup**

```bash
cd /home/hermes/mission-control && timeout 5 python3 server.py 2>&1 || true
# Should show 10 publisher threads starting, then the HTTP server
```

Expected output shows all 10 publishers starting, then the server listening message.

**Step 4: Commit**

```bash
cd /home/hermes/mission-control
git add server.py
git commit -m "feat: wire 10 publisher threads in main()"
```

---

### Task 3.2: Replace `_serve_sse()` with multiplexed drain

**Objective:** Modify the SSE handler to drain the shared queue instead of calling `build_snapshot()` in a loop. Keep the old monolithic event for backward compat during migration.

**Files:**
- Modify: `/home/hermes/mission-control/server.py` (`_serve_sse()` method near line 2229)

**Steps:**

**Step 1: Replace `_serve_sse()` body**

Replace lines 2229-2246 with:

```python
    def _serve_sse(self):
        """SSE stream — multiplexed via shared queue.
        Each channel publishes independently; this handler drains the queue.
        Also sends a heartbeat comment every 0.5s if the queue is empty.
        """
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "keep-alive")
        self._cors_headers()
        self.end_headers()

        # ── Initial burst: trigger all Tier 1 publishers to push once ──
        # Clear fingerprints for Tier 1 channels so they push on next cycle
        with _fp_lock:
            for event_type, interval, tier in _CHANNEL_REGISTRY:
                if tier == 1:
                    _CHANNEL_FINGERPRINTS.pop(event_type, None)
        
        try:
            while True:
                _sse_multiplex_drain(
                    self.wfile,
                    self.wfile.flush,
                    _SSE_QUEUE,
                    timeout=0.5
                )
        except (BrokenPipeError, ConnectionResetError, OSError):
            pass
```

**Step 2: Verify the handler compiles and the route is wired**

```bash
cd /home/hermes/mission-control && python3 -c "
import ast
with open('server.py') as f:
    tree = ast.parse(f.read())
# Find MissionControlHandler class
for node in ast.walk(tree):
    if isinstance(node, ast.ClassDef) and node.name == 'MissionControlHandler':
        methods = [n.name for n in node.body if isinstance(n, ast.FunctionDef)]
        print('Handler methods:', methods)
        assert '_serve_sse' in methods, '_serve_sse not found!'
        assert 'do_GET' in methods, 'do_GET not found!'
        print('OK')
        break
"
```

**Step 3: Commit**

```bash
cd /home/hermes/mission-control
git add server.py
git commit -m "feat: replace _serve_sse() with multiplexed queue drain"
```

---

### Task 3.3: Add per-channel REST endpoints

**Objective:** Add 10 REST endpoints (`GET /api/gateway`, `GET /api/profiles`, etc.) for the polling fallback path. These call the same `collect_*()` functions.

**Files:**
- Modify: `/home/hermes/mission-control/server.py` (`do_GET()` method near line 2125)

**Steps:**

**Step 1: Add per-channel routes to `do_GET()`**

After the existing `/api/snapshot` route (line 2131), insert:

```python
        # Per-channel REST endpoints (polling fallback + direct debug access)
        elif path == "/api/gateway":
            self._serve_channel("gateway", collect_gateway)
        elif path == "/api/processes":
            self._serve_channel("processes", collect_processes)
        elif path == "/api/hermes-health":
            self._serve_channel("hermes-health", collect_hermes_health)
        elif path == "/api/sessions-ledger":
            self._serve_channel("sessions-ledger", collect_sessions_ledger)
        elif path == "/api/profiles":
            self._serve_channel("profiles", collect_profiles)
        elif path == "/api/sessions":
            self._serve_channel("sessions", collect_sessions)
        elif path == "/api/kanban":
            self._serve_channel("kanban", collect_kanban)
        elif path == "/api/prod-health":
            self._serve_channel("prod-health", collect_prod_health)
        elif path == "/api/dokku":
            self._serve_channel("dokku", collect_dokku)
        elif path == "/api/server-crons":
            self._serve_channel("server-crons", collect_server_crons)
```

**Step 2: Add `_serve_channel()` helper method**

Add to `MissionControlHandler` class:

```python
    def _serve_channel(self, event_type, collect_fn):
        """Serve a single channel as JSON. Calls collect_fn() and returns the result."""
        try:
            data = collect_fn()
            body = json.dumps(data, default=str).encode("utf-8")
        except Exception as e:
            body = json.dumps({"error": str(e)}).encode("utf-8")
            self.send_response(HTTPStatus.INTERNAL_SERVER_ERROR)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", len(body))
            self._cors_headers()
            self.end_headers()
            self.wfile.write(body)
            return
        
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", len(body))
        self.send_header("Cache-Control", "no-cache")
        self._cors_headers()
        self.end_headers()
        self.wfile.write(body)
```

**Step 3: Verify all routes are wired**

```bash
cd /home/hermes/mission-control && python3 -c "
import ast
with open('server.py') as f:
    tree = ast.parse(f.read())

for node in ast.walk(tree):
    if isinstance(node, ast.ClassDef) and node.name == 'MissionControlHandler':
        for n in ast.walk(node):
            if isinstance(n, ast.FunctionDef) and n.name == 'do_GET':
                # Find all /api/ paths
                source = ast.get_source_segment(open('server.py').read(), n)
                paths = [l.strip() for l in source.split('\n') if '/api/' in l and 'elif path' in l]
                print(f'do_GET has {len(paths)} /api/ route branches')
                break
        break
print('OK')
"
```

**Step 4: Commit**

```bash
cd /home/hermes/mission-control
git add server.py
git commit -m "feat: add 10 per-channel REST endpoints + _serve_channel()"
```

---

## Phase 4: Frontend — Multi-Channel SSE + Per-Channel Polling

### Task 4.1: Add `patch()` method to snapshotStore

**Objective:** Add `patch(key, value)` to the Pinia snapshot store — per-key fingerprint comparison, shallow merge into `data`.

**Files:**
- Modify: `/home/hermes/mission-control/mission-control-vue/src/stores/snapshotStore.js`

**Steps:**

**Step 1: Add `patch()` method and fingerprint cache**

Replace the current `snapshotStore.js` content:

```javascript
import { defineStore } from 'pinia'
import { ref, reactive } from 'vue'

/**
 * Snapshot store — holds the latest data from the backend.
 * Supports two update paths:
 *   1. hydrate(snap) — full snapshot replacement (legacy, polling fallback)
 *   2. patch(key, value) — per-channel update (new SSE multiplexer)
 *
 * Per-key fingerprint comparison skips unnecessary reactive updates.
 * Domain stores derive from `data` via computed() — unchanged.
 */
export const useSnapshotStore = defineStore('snapshot', () => {
  const data = ref(null)
  const connected = ref(false)
  const lastUpdated = ref(null)
  
  /** Per-key MD5-like fingerprints — compared on each patch() */
  const _fingerprints = reactive({})

  /**
   * Legacy: full snapshot replacement (fingerprint-gated).
   * Returns true if data changed, false if identical.
   */
  function hydrate(snap) {
    const fp = JSON.stringify(snap)
    if (data.value && JSON.stringify(data.value) === fp) {
      return false
    }
    data.value = snap
    lastUpdated.value = snap.timestamp || Date.now() / 1000
    connected.value = true
    return true
  }

  /**
   * New: per-channel patch (fingerprint-gated per-key).
   * Merges `value` into `data.value[key]`.
   * Skips update if this channel's fingerprint hasn't changed.
   * Returns true if this channel's data changed.
   */
  function patch(key, value) {
    const fp = JSON.stringify(value)
    if (_fingerprints[key] === fp) {
      return false  // this channel didn't change
    }
    _fingerprints[key] = fp
    
    if (!data.value) {
      // First data — initialize with just this channel
      data.value = { [key]: value }
    } else {
      // Merge — shallow replace this key
      data.value = { ...data.value, [key]: value }
    }
    
    lastUpdated.value = Date.now() / 1000
    connected.value = true
    return true
  }

  /** Mark connection as lost (SSE error). Data is preserved. */
  function setDisconnected() {
    connected.value = false
  }

  return { data, connected, lastUpdated, hydrate, patch, setDisconnected }
})
```

**Step 2: Verify the file is syntactically valid**

```bash
cd /home/hermes/mission-control/mission-control-vue && node -e "
const fs = require('fs');
const src = fs.readFileSync('src/stores/snapshotStore.js', 'utf8');
// Basic syntax check: no obvious errors
if (src.includes('export const useSnapshotStore') && src.includes('function patch(')) {
    console.log('snapshotStore.js: patch() method present, OK');
} else {
    console.error('MISSING: patch method');
    process.exit(1);
}
"
```

**Step 3: Commit**

```bash
cd /home/hermes/mission-control
git add mission-control-vue/src/stores/snapshotStore.js
git commit -m "feat: add patch(key, value) to snapshotStore for per-channel updates"
```

---

### Task 4.2: Add per-channel SSE listeners to useSSE.js

**Objective:** Register event listeners for all 10 channel event types. Each listener calls `store.patch(channelKey, JSON.parse(data))`. Keep the old `snapshot` listener for backward compat.

**Files:**
- Modify: `/home/hermes/mission-control/mission-control-vue/src/composables/useSSE.js`

**Steps:**

**Step 1: Define the channel-to-store-key mapping and registered listeners**

Replace `useSSE.js` content:

```javascript
import { ref } from 'vue'
import { useSnapshotStore } from '../stores/snapshotStore.js'

// ── Module-level singletons ──
let source = null
let pollTimer = null
let channelPollTimers = {}  // { channelKey: intervalId }

const uplink = ref('disconnected')
const sseActive = ref(false)

// ── Channel event type → store key mapping ──
// SSE event name → snapshotStore.data key (and REST endpoint path)
const CHANNELS = {
  'gateway':          { key: 'gateway',          tier: 1, interval: 5000 },
  'processes':        { key: 'processes',        tier: 1, interval: 5000 },
  'hermes-health':    { key: 'vps',              tier: 1, interval: 5000 },
  'sessions-ledger':  { key: 'sessions_ledger',  tier: 1, interval: 15000 },
  'profiles':         { key: 'profiles',         tier: 2, interval: 60000 },
  'sessions':         { key: 'sessions',         tier: 2, interval: 30000 },
  'kanban':           { key: 'kanban',           tier: 2, interval: 30000 },
  'prod-health':      { key: 'vps_prod',         tier: 3, interval: 30000 },
  'dokku':            { key: 'servers',          tier: 3, interval: 60000 },
  'server-crons':     { key: 'server_crons',     tier: 3, interval: 300000 },
}

/**
 * useSSE composable — manages EventSource connection to /events
 * with per-channel SSE listeners and per-channel polling fallback.
 */
export function useSSE() {
  let store = null

  function _getStore() {
    if (!store) store = useSnapshotStore()
    return store
  }

  // ── Stop all polling ──
  function _stopAllPolling() {
    for (const [key, id] of Object.entries(channelPollTimers)) {
      clearInterval(id)
    }
    channelPollTimers = {}
  }

  // ── Per-channel polling fallback ──
  function startChannelPolling(channelName, channelConfig) {
    if (channelPollTimers[channelName]) return  // already polling
    
    channelPollTimers[channelName] = setInterval(async () => {
      try {
        const r = await fetch(`/api/${channelName}`)
        if (!r.ok) throw new Error(`HTTP ${r.status}`)
        const data = await r.json()
        
        // Special handling for hermes-health → stores under vps.hermes
        if (channelName === 'hermes-health') {
          const store = _getStore()
          const currentVps = store.data?.vps || {}
          store.patch('vps', { ...currentVps, hermes: data.health || data })
        }
        // Special handling for prod-health → stores under vps.prod
        else if (channelName === 'prod-health') {
          const store = _getStore()
          const currentVps = store.data?.vps || {}
          store.patch('vps', { ...currentVps, prod: data.health || data })
        }
        else {
          _getStore().patch(channelConfig.key, data)
        }
      } catch (err) {
        console.warn(`Poll ${channelName} failed:`, err)
      }
    }, channelConfig.interval)
  }

  // ── SSE connection ──
  function connect() {
    if (source) return

    uplink.value = 'connecting'
    source = new EventSource('/events')

    source.onopen = () => {
      sseActive.value = true
      uplink.value = 'synced'
      _stopAllPolling()
    }

    // ── Register per-channel event listeners ──
    for (const [eventType, config] of Object.entries(CHANNELS)) {
      source.addEventListener(eventType, (event) => {
        try {
          const data = JSON.parse(event.data)
          
          if (eventType === 'hermes-health') {
            const store = _getStore()
            const currentVps = store.data?.vps || {}
            store.patch('vps', { ...currentVps, hermes: data.health || data })
          } else if (eventType === 'prod-health') {
            const store = _getStore()
            const currentVps = store.data?.vps || {}
            store.patch('vps', { ...currentVps, prod: data.health || data })
          } else {
            _getStore().patch(config.key, data)
          }
        } catch (err) {
          console.warn(`SSE ${eventType} parse error:`, err)
        }
      })
    }

    // ── Legacy: full snapshot event (backward compat during migration) ──
    source.addEventListener('snapshot', (event) => {
      try {
        const snap = JSON.parse(event.data)
        _getStore().hydrate(snap)
      } catch (err) {
        console.warn('SSE snapshot parse error:', err)
      }
    })

    // ── Heartbeat ──
    source.addEventListener('heartbeat', () => {})

    source.onerror = () => {
      sseActive.value = false
      uplink.value = 'degraded'
      source.close()
      source = null
      // Start per-channel polling for all channels
      for (const [name, config] of Object.entries(CHANNELS)) {
        startChannelPolling(name, config)
      }
    }
  }

  return { uplink, sseActive, connect }
}
```

**Step 2: Verify the file is syntactically valid**

```bash
cd /home/hermes/mission-control/mission-control-vue && node -e "
const src = require('fs').readFileSync('src/composables/useSSE.js', 'utf8');
const checks = [
  'CHANNELS',
  'addEventListener',
  'startChannelPolling',
  'patch(',
  'snapshot',    // legacy listener still present
];
for (const c of checks) {
  if (!src.includes(c)) {
    console.error('MISSING:', c);
    process.exit(1);
  }
}
console.log('useSSE.js: all required patterns present, OK');
"
```

**Step 3: Commit**

```bash
cd /home/hermes/mission-control
git add mission-control-vue/src/composables/useSSE.js
git commit -m "feat: add per-channel SSE listeners + per-channel polling fallback to useSSE"
```

---

### Task 4.3: Update domain stores for new data shape

**Objective:** Ensure all domain stores correctly derive from the new per-channel data keys. The `patch()` method merges into `data.value`, so `computed()` already works — but we need to verify each store's key mapping.

**Files to review (no changes expected, but verify):**
- `mission-control-vue/src/stores/profiles.js` — checks `data.profiles`
- `mission-control-vue/src/stores/kanban.js` — checks `data.kanban`
- `mission-control-vue/src/stores/sessions.js` — checks `data.sessions` + `data.sessions_ledger`
- `mission-control-vue/src/stores/servers.js` — checks `data.servers`
- `mission-control-vue/src/stores/content.js` — fetches independently (no change)
- `mission-control-vue/src/views/OverviewPage.vue` — checks `data.vps.hermes` + `data.errors` + `data.kanban.boards` + `data.sessions_ledger`

**Channel → store key mapping to verify:**

| SSE Event | `patch()` key | Domain store | Existing computed |
|-----------|--------------|--------------|-------------------|
| `gateway` | `gateway` | None (used directly in Overview/SystemStatus) | `snap.data?.gateway` ✓ |
| `processes` | `processes` | None (used directly) | `snap.data?.processes` ✓ |
| `hermes-health` | `vps` (merged: `{hermes: {...}}`) | None (OverviewPage) | `snap.data?.vps?.hermes` ✓ |
| `sessions-ledger` | `sessions_ledger` | sessions.js | `snap.data?.sessions_ledger` ✓ |
| `profiles` | `profiles` | profiles.js | `snap.data?.profiles` ✓ |
| `sessions` | `sessions` | sessions.js | `snap.data?.sessions` ✓ |
| `kanban` | `kanban` | kanban.js | `snap.data?.kanban` ✓ |
| `prod-health` | `vps` (merged: `{prod: {...}}`) | None (OverviewPage/VpsHealth) | `snap.data?.vps?.prod` ✓ |
| `dokku` | `servers` | servers.js | `snap.data?.servers` ✓ |
| `server-crons` | `server_crons` | None (servers page) | `snap.data?.server_crons` ✓ |

**Step 1: Verify key mappings**

```bash
cd /home/hermes/mission-control/mission-control-vue
# Check every domain store's computed() references
for f in src/stores/profiles.js src/stores/kanban.js src/stores/sessions.js src/stores/servers.js; do
    echo "=== $(basename $f) ==="
    grep -n "snap.data" "$f" | head -5
done

echo ""
echo "=== OverviewPage.vue ==="
grep -n "snap.data\|d\.vps\|d\.kanban\|d\.sessions_ledger\|d\.errors" src/views/OverviewPage.vue
```

**Step 2: If any key mismatch is found, adjust the CHANNELS mapping in useSSE.js**

(Expected: all keys match — the channel names were chosen to align with existing `snapshot.data` keys.)

**Step 3: Commit**

```bash
cd /home/hermes/mission-control
git add -A
git commit -m "feat: verify domain store key mappings for per-channel data"
```

---

## Phase 5: Retention DB — Per-Channel Tables

### Task 5.1: Update dashboard.db schema to support per-channel retention

**Objective:** Modify `_init_dashboard_db()` to create per-channel retention tables alongside the legacy `snapshots` table (kept for backward compat).

**Files:**
- Modify: `/home/hermes/mission-control/server.py` (`_init_dashboard_db()` near line 56)

**Steps:**

**Step 1: Add per-channel table creation**

After the existing `CREATE TABLE IF NOT EXISTS snapshots` statement in `_init_dashboard_db()`, add:

```python
    # Per-channel retention tables (one per event type)
    for event_type, _, _ in _CHANNEL_REGISTRY:
        table_name = f"retention_{event_type.replace('-', '_')}"
        db.execute(f"""
            CREATE TABLE IF NOT EXISTS {table_name} (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp REAL NOT NULL,
                payload TEXT NOT NULL
            )
        """)
        db.execute(f"""
            CREATE INDEX IF NOT EXISTS idx_{table_name}_ts
            ON {table_name}(timestamp)
        """)
```

**Step 2: Add cleanup for per-channel tables**

In `_cleanup_old_snapshots()`, after the existing cleanup of `snapshots` table, add:

```python
    # Per-channel retention cleanup (keep last 1000 entries per channel)
    for event_type, _, _ in _CHANNEL_REGISTRY:
        table_name = f"retention_{event_type.replace('-', '_')}"
        try:
            db.execute(f"""
                DELETE FROM {table_name} WHERE id NOT IN (
                    SELECT id FROM {table_name} ORDER BY id DESC LIMIT 1000
                )
            """)
        except Exception:
            pass
```

**Step 3: Verify the schema after init**

```bash
cd /home/hermes/mission-control && python3 -c "
import sqlite3, os
exec(open('server.py').read().split('def main')[0])
# Force re-init
_init_dashboard_db()
db = sqlite3.connect(DASHBOARD_DB)
tables = db.execute(\"SELECT name FROM sqlite_master WHERE type='table' ORDER BY name\").fetchall()
print('Tables in dashboard.db:')
for t in tables:
    print(f'  {t[0]}')
db.close()
"
```

Expected: at least `snapshots` + 10 `retention_*` tables.

**Step 4: Commit**

```bash
cd /home/hermes/mission-control
git add server.py
git commit -m "feat: add per-channel retention tables to dashboard.db"
```

---

## Phase 6: Cleanup — Remove Monolithic Path

### Task 6.1: Remove monolithic snapshot event from SSE

**Objective:** After verifying the multiplexed path works, remove the old `snapshot` event from the SSE stream. Keep `build_snapshot()` for `/api/snapshot` (polling fallback) but stop pushing it over SSE.

**Files:**
- Modify: `/home/hermes/mission-control/server.py` (`_serve_sse()` method)

**Steps:**

**Step 1: The monolithic snapshot is already NOT being pushed**

Review `_serve_sse()` — it now calls `_sse_multiplex_drain()` which only drains the queue. The old `build_snapshot()` call was already removed in Task 3.2. No additional changes needed if the multiplexer is working.

**Step 2: Remove legacy snapshot listener from frontend**

In `useSSE.js`, remove the `source.addEventListener('snapshot', ...)` block (lines that handle the full snapshot event).

**Step 3: Commit**

```bash
cd /home/hermes/mission-control
git add mission-control-vue/src/composables/useSSE.js
git commit -m "feat: remove legacy snapshot SSE listener — fully multiplexed"
```

---

### Task 6.2: Keep `build_snapshot()` for `/api/snapshot` polling fallback

**Objective:** `/api/snapshot` stays as-is for backward compatibility and debugging. It continues to use `build_snapshot()` which assembles all sources — but this is now only called on explicit HTTP GET, not pushed every 5s.

**Files:**
- No changes. `build_snapshot()` is preserved. `_serve_snapshot()` continues to call it.

**Step 1: Verify `/api/snapshot` still works**

```bash
# After restarting the server:
curl -s http://localhost:51763/api/snapshot | python3 -c "
import json, sys
snap = json.load(sys.stdin)
print('keys:', list(snap.keys()))
print('timestamp:', snap.get('timestamp_iso'))
print('OK')
"
```

**Step 2: Commit (no code changes — verification only)**

```bash
cd /home/hermes/mission-control
# Nothing to commit — build_snapshot() is preserved
echo "build_snapshot() preserved for /api/snapshot — no changes needed"
```

---

## Phase 7: Progressive Load + Polish

### Task 7.1: Implement progressive load — Tier 1 burst on connect

**Objective:** When a new SSE client connects, Tier 1 publishers push immediately (not waiting for their next interval). Tier 2-3 arrive on their normal cadence. The frontend shows placeholders until each channel arrives.

**Files:**
- Modify: `/home/hermes/mission-control/server.py` (`_serve_sse()`)

**Step 1: Burst mechanism**

The burst was already implemented in Task 3.2 — `_serve_sse()` clears Tier 1 fingerprints on connect, causing the next `publish_channel()` cycle for those channels to detect a "change" and push. Verify this logic is correct.

In `_serve_sse()`, the burst section:

```python
# ── Initial burst: trigger all Tier 1 publishers to push once ──
with _fp_lock:
    for event_type, interval, tier in _CHANNEL_REGISTRY:
        if tier == 1:
            _CHANNEL_FINGERPRINTS.pop(event_type, None)
```

This clears the fingerprint, so on each Tier 1 publisher's next cycle (within 5-15s), it will detect a "change" and push. For a faster burst (immediate push on connect), we need to signal the publisher threads.

**Step 2: Enhanced burst — signal threads to collect immediately**

Add a `threading.Event` per channel for burst signaling:

Add after the `_CHANNEL_REGISTRY`:

```python
# Burst signals — set on new SSE client connect, cleared after one push
_CHANNEL_BURST = {event_type: threading.Event() for event_type, _, _ in _CHANNEL_REGISTRY}
```

In `publish_channel()`, before the `time.sleep(interval)`:

```python
        # Burst mode: if signaled, skip sleep and collect immediately
        burst_event = _CHANNEL_BURST.get(event_type)
        if burst_event and burst_event.is_set():
            burst_event.clear()
            continue  # skip sleep, collect again now
        time.sleep(interval)
```

In `_serve_sse()`, the burst section becomes:

```python
        # ── Initial burst: signal Tier 1 publishers to push immediately ──
        with _fp_lock:
            for event_type, interval, tier in _CHANNEL_REGISTRY:
                if tier == 1:
                    _CHANNEL_FINGERPRINTS.pop(event_type, None)
                    burst = _CHANNEL_BURST.get(event_type)
                    if burst:
                        burst.set()
```

**Step 3: Commit**

```bash
cd /home/hermes/mission-control
git add server.py
git commit -m "feat: add burst signaling for immediate Tier 1 push on SSE connect"
```

---

### Task 7.2: Add loading states — distinguish "loading" from "empty"

**Objective:** During progressive load, widgets that are **configured** (have a data source set up) but haven't received their first channel data yet show "Loading…" instead of their blank/initial-state text. Widgets that are genuinely **unconfigured** (e.g., no servers in `servers.json`, no profiles found) keep their existing empty-state text.

**Design rule:**
| State | What the widget shows |
|-------|----------------------|
| Configured + data not yet arrived | `Loading…` (progressive load — channel hasn't fired yet) |
| Configured + data arrived (possibly empty) | The real data, even if zero/empty |
| Not configured | Existing blank/initial-state text (e.g., "No servers defined") |

**Pattern:** Each widget checks whether it's "configured" independently of whether data has arrived. Configuration is known from static sources (files on disk, detected profiles). Data arrival is tracked per-channel in `snapshotStore`.

**Files:**
- Modify: `/home/hermes/mission-control/mission-control-vue/src/stores/snapshotStore.js` (add per-channel loaded tracking)
- Modify: `/home/hermes/mission-control/mission-control-vue/src/components/StatsStrip.vue`
- Modify: `/home/hermes/mission-control/mission-control-vue/src/components/SystemStatus.vue`
- Modify: `/home/hermes/mission-control/mission-control-vue/src/components/VpsHealth.vue`
- Modify: `/home/hermes/mission-control/mission-control-vue/src/components/ActivityFeed.vue`
- Modify: `/home/hermes/mission-control/mission-control-vue/src/views/OverviewPage.vue`

**Step 1: Add per-channel loaded tracking to snapshotStore**

In `snapshotStore.js`, add a `_loaded` reactive set that tracks which channels have delivered their first payload:

```javascript
/** Per-channel loaded flags — true once the first payload for this channel arrives */
const _loaded = reactive({})

function patch(key, value) {
  const fp = JSON.stringify(value)
  if (_fingerprints[key] === fp) return false
  _fingerprints[key] = fp
  
  _loaded[key] = true  // mark this channel as loaded
  
  if (!data.value) {
    data.value = { [key]: value }
  } else {
    data.value = { ...data.value, [key]: value }
  }
  
  lastUpdated.value = Date.now() / 1000
  connected.value = true
  return true
}

/** Check if a channel has delivered its first payload yet */
function isChannelLoaded(key) {
  return !!_loaded[key]
}
```

Export `isChannelLoaded` from the store.

**Step 2: Update each widget to distinguish loading vs empty**

For each widget:

1. **Identify the "configured" condition** — what makes this widget know it's supposed to have data?
2. **Check `isChannelLoaded()`** — has the relevant channel delivered yet?
3. **Three-way render:**

```javascript
// Example pattern for a widget
const isConfigured = computed(() => {
  // Check static configuration
  // e.g., snap.data?.servers?.length > 0 for servers
  // e.g., d.gateway !== undefined for gateway (always configured)
  // e.g., d.profiles?.length > 0 for profiles
})
const isLoaded = computed(() => store.isChannelLoaded('relevant_key'))

// Template:
// <template v-if="!isConfigured">  ← blank/initial state
//   No servers defined
// </template>
// <template v-else-if="!isLoaded"> ← loading state (configured but no data yet)
//   Loading…
// </template>
// <template v-else>               ← live data
//   Actual widget content
// </template>
```

**Widget-by-widget mapping:**

| Widget | Configured condition | Channel key |
|--------|---------------------|-------------|
| StatsStrip (gateway values) | Always configured (gateway exists if Hermes is running) | `gateway` |
| StatsStrip (profile count) | Always configured (at least default profile) | `profiles` |
| StatsStrip (session count) | Always configured (state.db exists) | `sessions_ledger` |
| StatsStrip (kanban count) | Always configured (kanban dir exists, may be empty) | `kanban` |
| SystemStatus | Always configured | `gateway` |
| VpsHealth (hermes) | Always configured (local /proc) | `vps` (from hermes-health) |
| VpsHealth (prod) | `servers.json` has a "prod" entry | `vps` (from prod-health) |
| ActivityFeed | Profiles exist | `profiles` |
| Ops footer (Queue/Tasks) | Kanban boards exist | `kanban` |
| Ops footer (Sessions) | Always configured | `sessions_ledger` |
| Ops footer (Errors) | Always configured | (derived from snapshot errors array) |
| Ops footer (Uptime) | Always configured (local /proc) | `vps` (from hermes-health) |

**Step 3: Add CSS for loading text**

```css
/* In tokens.css or component scoped styles */
.loading-text {
  font-family: var(--font-mono);
  font-size: 11px;
  letter-spacing: 0.12em;
  color: var(--text-faint);
  animation: pulse-faint 1.5s ease-in-out infinite;
}
@keyframes pulse-faint {
  0%, 100% { opacity: 0.4; }
  50% { opacity: 0.8; }
}
```

**Step 4: Build and verify**

```bash
cd /home/hermes/mission-control/mission-control-vue && npm run build
```

**Step 5: Commit**

```bash
cd /home/hermes/mission-control
git add mission-control-vue/src/stores/snapshotStore.js
git add mission-control-vue/src/components/StatsStrip.vue
git add mission-control-vue/src/components/SystemStatus.vue
git add mission-control-vue/src/components/VpsHealth.vue
git add mission-control-vue/src/components/ActivityFeed.vue
git add mission-control-vue/src/views/OverviewPage.vue
git add mission-control-vue/src/assets/tokens.css
git add mission-control-vue/dist/
git commit -m "feat: distinguish loading vs empty states in progressive widgets"
```

---

### Task 7.3: Build, restart, and smoke test

**Objective:** Build the Vue frontend, restart the Mission Control service, and verify the multiplexed SSE stream works end-to-end.

**Steps:**

**Step 1: Build the frontend**

```bash
cd /home/hermes/mission-control/mission-control-vue && npm run build 2>&1
```

Expected: build succeeds, output in `../dist/`.

**Step 2: Restart the service**

```bash
sudo systemctl restart mission-control && sleep 3 && sudo systemctl status mission-control --no-pager -l | head -15
```

Expected: Active: active (running).

**Step 3: Verify SSE stream has per-channel events**

```bash
timeout 8 curl -sN http://localhost:51763/events 2>&1 | head -30
```

Expected: see `event: gateway`, `event: hermes-health`, etc. — not a single `event: snapshot`.

**Step 4: Verify per-channel REST endpoints**

```bash
for ep in gateway processes hermes-health sessions-ledger; do
    echo "=== /api/$ep ==="
    curl -s http://localhost:51763/api/$ep | python3 -c "import json,sys; d=json.load(sys.stdin); print(list(d.keys())[:5])" 2>&1
done
```

**Step 5: Verify dashboard loads**

Open http://100.67.254.90:51763/ in browser. Check:
- Top bar shows "UPLINK // SYNCED" (SSE connected)
- Overview page fills in progressively (gateway, health first, then sessions, kanban, profiles)
- Switching tabs works (all 6 pages render)
- Content tab still loads documents
- No console errors

**Step 6: Commit**

```bash
cd /home/hermes/mission-control
git add dist/
git commit -m "feat: build and verify multiplexed SSE end-to-end"
```

---

## Summary: Files Changed

| File | Changes |
|------|---------|
| `server.py` | +~250 lines: queue, channel registry, 10 `collect_*()` functions, `publish_channel()`, `_sse_multiplex_drain()`, `_serve_channel()`, modified `_serve_sse()`, modified `main()`, per-channel retention tables |
| `mission-control-vue/src/stores/snapshotStore.js` | Rewritten: added `patch(key, value)` with per-key fingerprint cache |
| `mission-control-vue/src/composables/useSSE.js` | Rewritten: per-channel SSE listeners + per-channel polling fallback |
| `mission-control-vue/src/components/StatsStrip.vue` | Minor: three-way loading/empty/live states |
| `mission-control-vue/src/components/SystemStatus.vue` | Minor: three-way loading/empty/live states |
| `mission-control-vue/src/components/VpsHealth.vue` | Minor: three-way loading/empty/live states |
| `mission-control-vue/src/components/ActivityFeed.vue` | Minor: three-way loading/empty/live states |
| `mission-control-vue/src/views/OverviewPage.vue` | Minor: ops footer loading states |
| `mission-control-vue/src/assets/tokens.css` | Minor: `.loading-text` + `pulse-faint` animation |

**No changes to:**
- Any domain store (profiles, kanban, sessions, servers, content, ui)
- Any page component (OverviewPage, ProfilesPage, KanbanPage, etc.)
- Any canvas component (RadarCanvas, SparklineCanvas, PieChart)
- Content API endpoints
- Dokku log SSE stream
- Glance data endpoint
- `build_snapshot()` — preserved for `/api/snapshot` fallback

## Verification Checklist

- [ ] `server.py` starts 10 publisher threads
- [ ] Each publisher pushes only when its data changes
- [ ] SSE stream carries named events (`gateway`, `hermes-health`, etc.)
- [ ] Legacy `snapshot` event is no longer pushed
- [ ] Per-channel REST endpoints return correct data
- [ ] `/api/snapshot` still works (for debugging/polling fallback)
| Configured widgets show "Loading…" (pulsing) during progressive load, not blank-state text |
- [ ] All 6 pages render correctly
- [ ] Top bar uplink indicator shows SYNCED when SSE connected, DEGRADED when polling
- [ ] Polling fallback works (stop server → frontend switches to per-channel polling)
- [ ] `dashboard.db` has per-channel retention tables
- [ ] No console errors in browser
- [ ] Build succeeds: `cd mission-control-vue && npm run build`
