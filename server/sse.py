"""SSE multiplexer infrastructure."""

import hashlib
import json
import queue as queue_module
import threading
import time
from server.config import _CHANNEL_FINGERPRINTS, _fp_lock, _CHANNEL_BURST, DASHBOARD_DB
# =============================================================================
# SSE Multiplexer — publisher framework
# =============================================================================

def publish_channel(event_type, collect_fn, interval, queue):
    """
    Generic channel publisher — runs in its own thread.

    Each cycle:
      1. Collect data via collect_fn() (must be thread-safe)
      2. MD5-fingerprint the JSON output
      3. If changed → push to queue
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
