"""SSE multiplexer infrastructure."""

import hashlib
import json
import queue as queue_module
import sqlite3
import threading
import time
from server.config import _CHANNEL_FINGERPRINTS, _fp_lock, _CHANNEL_BURST, DASHBOARD_DB
# =============================================================================
# SSE Multiplexer — publisher framework
# =============================================================================

def _save_channel_retention(event_type, payload, db_path):
    """Save a single channel's data to its retention table. Creates table if needed."""
    table_name = f"retention_{event_type.replace('-', '_')}"
    db = sqlite3.connect(db_path)
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


def publish_channel(event_type, collect_fn, interval, queue, retention_db_path=None):
    """
    Generic channel publisher — runs in its own thread.

    Each cycle:
      1. Collect data via collect_fn() (must be thread-safe)
      2. MD5-fingerprint the JSON output
      3. If changed → push to queue + optionally save to retention DB
      4. Sleep for interval seconds (unless burst-signaled)

    Thread-safe: only touches its own fingerprint entry (guarded by _fp_lock)
    and the shared queue (thread-safe by design).
    """
    global _CHANNEL_FINGERPRINTS
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
            import traceback, sys
            print(f"[publisher:{event_type}] ERROR: {traceback.format_exc()}", file=sys.stderr, flush=True)
            time.sleep(1)  # brief pause before retry to avoid tight crash loops

        # Burst mode: if signaled, skip sleep and collect immediately
        burst_event = _CHANNEL_BURST.get(event_type)
        if burst_event and burst_event.is_set():
            burst_event.clear()
            continue
        time.sleep(interval)


def _sse_multiplex_drain(wfile, flush_fn, queue, timeout=0.5, channels=None):
    """
    Drain the shared SSE queue, writing named events to the client.
    Called from _serve_sse() in a loop.

    Blocks up to `timeout` seconds waiting for the next event.
    Returns True if at least one event was written, False if timeout elapsed.

    If `channels` is a set, events not in that set are silently dropped.

    Handles BrokenPipeError/ConnectionResetError by re-raising to caller.
    """
    try:
        event_type, payload = queue.get(timeout=timeout)
        if channels is not None and event_type not in channels:
            return False  # Silently drop events for unsubscribed channels
        msg = f"event: {event_type}\ndata: {payload}\n\n"
        wfile.write(msg.encode("utf-8"))
        flush_fn()
        return True
    except queue_module.Empty:
        # Send a heartbeat comment to keep the connection alive
        wfile.write(b": heartbeat\n\n")
        flush_fn()
        return False
