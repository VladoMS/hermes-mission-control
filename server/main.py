"""Mission Control entry point — server bootstrap and lifecycle."""
import http.server
import os
import ssl
import subprocess
import sys
import threading

# Ensure the project root is on the Python path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from server.config import (
    HOST, PORT, CERT_DIR, CERT_FILE, KEY_FILE, DASHBOARD_DB,
    _SSE_QUEUE, _CHANNEL_REGISTRY
)
from server.dashboard_db import _init_dashboard_db, _cleanup_old_snapshots
from server.handler import MissionControlHandler
from server.snapshot import _CHANNEL_COLLECTORS
from server.sse import publish_channel

# =============================================================================
# HTTP Server
# =============================================================================

class ThreadingHTTPServer(http.server.ThreadingHTTPServer):
    """Threaded HTTP server with SO_REUSEADDR."""
    allow_reuse_address = True
    daemon_threads = True


# =============================================================================
# SSL Certificate
# =============================================================================

def _ensure_cert():
    """Generate a self-signed certificate if one doesn't exist.
    Returns (cert_path, key_path)."""
    os.makedirs(CERT_DIR, exist_ok=True, mode=0o700)
    if os.path.isfile(CERT_FILE) and os.path.isfile(KEY_FILE):
        return CERT_FILE, KEY_FILE

    print("▶ Generating self-signed SSL certificate (valid 365 days)...")
    subprocess.run([
        "openssl", "req", "-x509", "-newkey", "rsa:4096",
        "-keyout", KEY_FILE,
        "-out", CERT_FILE,
        "-days", "365",
        "-nodes",
        "-subj", "/CN=Mission Control",
        "-addext", "subjectAltName=IP:100.67.254.90,DNS:localhost",
    ], check=True, capture_output=True)
    os.chmod(KEY_FILE, 0o600)
    os.chmod(CERT_FILE, 0o644)
    print(f"  ▶ cert: {CERT_FILE}")
    print(f"  ▶ key:  {KEY_FILE}")
    return CERT_FILE, KEY_FILE


# =============================================================================
# Entry point
# =============================================================================

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

    print(f"  ▶ {len(_publisher_threads)} channel publishers started\n")

    # Ensure SSL certificate exists (required for PWA features)
    cert_path, key_path = _ensure_cert()

    server = ThreadingHTTPServer((HOST, PORT), MissionControlHandler)
    # Wrap with SSL for HTTPS
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    ctx.load_cert_chain(cert_path, key_path)
    server.socket = ctx.wrap_socket(server.socket, server_side=True)

    print(f"▶ MISSION CONTROL listening on https://{HOST}:{PORT}")
    print(f"  GET /                → index.html")
    print(f"  GET /api/snapshot    → legacy full snapshot (polling fallback)")
    print(f"  GET /api/gateway     → per-channel REST endpoints")
    print(f"  GET /api/sessions    → ... (all 16 channels)")
    print(f"  GET /api/content     → document list")
    print(f"  GET /api/content/get → read document")
    print(f"  POST /api/content/save → save document")
    print(f"  GET /events          → SSE multiplexed stream")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n▼ Shutting down.")
        server.shutdown()


if __name__ == "__main__":
    main()
