"""HTTP request handler."""

import http.server
import json
import os
import subprocess
import threading
import time
import urllib.parse
from http import HTTPStatus
from server.config import _CHANNEL_REGISTRY, _CHANNEL_FINGERPRINTS, _fp_lock, _CHANNEL_BURST, _SSE_QUEUE, CA_CERT_FILE, HERMES_HOME
from server.sse import _sse_multiplex_drain
from server.readers import _read_servers_config, read_json
from server.content import list_content, read_content, save_content
from server.glance import _get_glance_data
from server.snapshot import _CHANNEL_COLLECTORS
# =============================================================================
# HTTP Handlers
# =============================================================================

_DIST_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "dist")
_INDEX_PATH = os.path.join(_DIST_DIR, "index.html")


class MissionControlHandler(http.server.BaseHTTPRequestHandler):
    """Request handler — serves index, snapshot JSON, and SSE stream."""

    server_version = "MissionControl/1.0"

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        qs = urllib.parse.parse_qs(parsed.query)

        # API routes
        if path == "/api/snapshot":
            self._serve_snapshot()
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
        elif path == "/api/servers":
            self._serve_channel("servers", collect_servers)
        # Work server endpoints
        elif path == "/api/work-system":
            self._serve_channel("work-system", collect_work_system_health)
        elif path == "/api/work-docker":
            self._serve_channel("work-docker", collect_work_docker)
        elif path == "/api/work-nexus":
            self._serve_channel("work-nexus", collect_work_nexus)
        elif path == "/api/work-jenkins":
            self._serve_channel("work-jenkins", collect_work_jenkins)
        elif path == "/api/work-postgres":
            self._serve_channel("work-postgres", collect_work_postgres)
        elif path == "/api/content":
            self._serve_content_list()
        elif path == "/api/content/get":
            self._serve_content_get(qs)
        elif path == "/api/glance-data":
            self._serve_glance_data()
        elif path == "/events":
            self._serve_sse(qs)
        elif path == "/api/dokku/logs":
            self._serve_dokku_logs(qs)
        elif path == "/ca-cert.pem":
            self._serve_ca_cert()
        # Static assets (served from dist/)
        elif (path.startswith("/assets/")
              or path == "/favicon.ico"
              or path == "/sw.js"
              or path == "/manifest.webmanifest"
              or path.startswith("/icons/")
              or path == "/icon.svg"):
            self._serve_static(path)
        # SPA fallback — all other paths serve index.html
        else:
            self._serve_index()

    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path

        if path == "/api/content/save":
            self._serve_content_save()
        else:
            self.send_error(HTTPStatus.NOT_FOUND)

    def do_OPTIONS(self):
        """CORS preflight."""
        self.send_response(204)
        self._cors_headers()
        self.end_headers()

    def _cors_headers(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")

    def _serve_index(self):
        try:
            with open(_INDEX_PATH, "rb") as f:
                body = f.read()
        except Exception:
            body = b"<h1>MISSION CONTROL</h1><p>dist/index.html not found. Run: npm run build</p>"
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", len(body))
        self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
        self._cors_headers()
        self.end_headers()
        self.wfile.write(body)

    def _serve_static(self, path):
        """Serve static files from dist/ directory."""
        import mimetypes
        if not mimetypes.inited:
            mimetypes.init()
        filepath = os.path.join(_DIST_DIR, path.lstrip("/"))
        if not os.path.isfile(filepath):
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        try:
            with open(filepath, "rb") as f:
                body = f.read()
        except Exception:
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        mime, _ = mimetypes.guess_type(filepath)
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", mime or "application/octet-stream")
        self.send_header("Content-Length", len(body))
        # Service worker must be revalidated on every navigation request
        if os.path.basename(filepath) == "sw.js":
            self.send_header("Cache-Control", "max-age=0, must-revalidate")
            self.send_header("Service-Worker-Allowed", "/")
        else:
            self.send_header("Cache-Control", "public, max-age=3600")
        self._cors_headers()
        self.end_headers()
        self.wfile.write(body)

    def _serve_snapshot(self):
        snapshot = build_snapshot()
        body = json.dumps(snapshot, default=str).encode("utf-8")
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", len(body))
        self._cors_headers()
        self.end_headers()
        self.wfile.write(body)

    def _serve_glance_data(self):
        """GET /api/glance-data — weather + Twitch streams + timezone config."""
        data = _get_glance_data()
        body = json.dumps(data, default=str).encode("utf-8")
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", len(body))
        self.send_header("Cache-Control", "public, max-age=60")
        self._cors_headers()
        self.end_headers()
        self.wfile.write(body)

    def _serve_ca_cert(self):
        """Serve the CA certificate for client trust installation."""
        try:
            with open(CA_CERT_FILE, "rb") as f:
                body = f.read()
        except Exception:
            self.send_error(HTTPStatus.NOT_FOUND, "CA cert not found")
            return
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "application/x-pem-file")
        self.send_header("Content-Length", len(body))
        self.send_header("Content-Disposition", "attachment; filename=\"mission-control-ca.pem\"")
        self.send_header("Cache-Control", "no-cache")
        self._cors_headers()
        self.end_headers()
        self.wfile.write(body)

    def _serve_sse(self, qs=None):
        """SSE stream — multiplexed via shared queue.
        Each channel publishes independently; this handler drains the queue.

        Query params:
            channels — comma-separated event types to subscribe to.
                       If omitted, all channels are delivered.
        """
        # ── Parse channel filter ──
        raw = (qs or {}).get("channels", [None])[0]
        if raw:
            channel_set = set(c.strip() for c in raw.split(",") if c.strip())
        else:
            channel_set = None  # No filter → all channels

        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "keep-alive")
        self._cors_headers()
        self.end_headers()

        # ── Initial burst: signal Tier 1 publishers to push immediately ──
        with _fp_lock:
            for event_type, interval, tier in _CHANNEL_REGISTRY:
                if tier == 1 and (channel_set is None or event_type in channel_set):
                    _CHANNEL_FINGERPRINTS.pop(event_type, None)
                    burst = _CHANNEL_BURST.get(event_type)
                    if burst:
                        burst.set()

        try:
            while True:
                _sse_multiplex_drain(
                    self.wfile,
                    self.wfile.flush,
                    _SSE_QUEUE,
                    timeout=0.5,
                    channels=channel_set
                )
        except (BrokenPipeError, ConnectionResetError, OSError):
            pass

    def _serve_dokku_logs(self, qs):
        """SSE stream of docker logs for a Dokku app container."""
        server_name = (qs.get("server", [None])[0] or "").strip()
        app_name = (qs.get("app", [None])[0] or "").strip()
        tail = (qs.get("tail", ["100"])[0] or "100").strip()

        if not server_name or not app_name:
            self.send_error(HTTPStatus.BAD_REQUEST, "Missing server or app query parameter")
            return

        # Resolve server host from servers.json
        servers_cfg = _read_servers_config()
        host = None
        for srv in servers_cfg:
            if srv.get("name") == server_name:
                host = srv.get("host")
                break
        if not host or host == "localhost":
            self.send_error(HTTPStatus.BAD_REQUEST, f"Server '{server_name}' not found or is localhost")
            return

        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "keep-alive")
        self._cors_headers()
        self.end_headers()

        try:
            # Gather logs from ALL containers in the app's stack, prefixed with [container_name]
            # Example: vladislavstoyanov → vladislavstoyanov.web.1, vladislavstoyanov.scheduler.1, etc.
            cmd = (
                f"containers=$(docker ps --filter 'name=^{app_name}\\.' --format '{{{{.Names}}}}');"
                f"if [ -z \"$containers\" ]; then"
                f"  docker logs --follow --tail {tail} {app_name}.web.1 2>&1;"
                f"else"
                f"  for ctr in $containers; do"
                f"    docker logs --follow --tail {tail} \"$ctr\" 2>&1 | sed -u 's/^/['\"$ctr\"'] /' &"
                f"  done;"
                f"  wait;"
                f"fi"
            )
            p = subprocess.Popen(
                ["ssh", "-o", "ConnectTimeout=5", "-o", "BatchMode=yes", host, cmd],
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True
            )
            for line in iter(p.stdout.readline, ""):
                if not line:
                    break
                # SSE format — strip control chars, escape for JSON
                clean = line.rstrip("\n").replace("\\", "\\\\").replace('"', '\\"')
                msg = f"data: {clean}\n\n"
                try:
                    self.wfile.write(msg.encode("utf-8"))
                    self.wfile.flush()
                except (BrokenPipeError, ConnectionResetError, OSError):
                    break
            p.terminate()
        except (BrokenPipeError, ConnectionResetError, OSError):
            pass
        except Exception:
            pass

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

    def _serve_content_list(self):
        """GET /api/content — list .md files under ~/.hermes/content/."""
        docs = list_content()
        body = json.dumps({"documents": docs}, default=str).encode("utf-8")
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", len(body))
        self._cors_headers()
        self.end_headers()
        self.wfile.write(body)

    def _serve_content_get(self, qs):
        """GET /api/content/get?path= — return raw markdown."""
        rel_path = qs.get("path", [None])[0]
        if not rel_path:
            self._json_error(HTTPStatus.BAD_REQUEST, "missing 'path' parameter")
            return
        content, abs_path, err = read_content(rel_path)
        if err:
            self._json_error(HTTPStatus.BAD_REQUEST, err)
            return
        body = json.dumps({"path": rel_path, "abs_path": abs_path, "content": content}).encode("utf-8")
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", len(body))
        self._cors_headers()
        self.end_headers()
        self.wfile.write(body)

    def _serve_content_save(self):
        """POST /api/content/save — body { path, content }. Write content back."""
        length = int(self.headers.get("Content-Length", 0))
        if length == 0:
            self._json_error(HTTPStatus.BAD_REQUEST, "empty body")
            return
        try:
            raw = self.rfile.read(length)
            data = json.loads(raw.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            self._json_error(HTTPStatus.BAD_REQUEST, "invalid JSON")
            return

        rel_path = data.get("path")
        content = data.get("content")
        if not rel_path or content is None:
            self._json_error(HTTPStatus.BAD_REQUEST, "missing 'path' or 'content'")
            return

        ok, err = save_content(rel_path, content)
        if not ok:
            self._json_error(HTTPStatus.BAD_REQUEST, err)
            return

        body = json.dumps({"ok": True, "path": rel_path}).encode("utf-8")
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", len(body))
        self._cors_headers()
        self.end_headers()
        self.wfile.write(body)

    def _json_error(self, status, message):
        """Send a JSON error response."""
        body = json.dumps({"error": message}).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", len(body))
        self._cors_headers()
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format, *args):
        """Suppress default access logging."""
        return

