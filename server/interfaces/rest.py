"""REST API controller — replaces handler.py.

Serves:
  - /api/v2/<domain> — normalized per-domain JSON (from repos)
  - /api/<channel>  — legacy polling fallback (calls collector, returns data)
  - /events         — SSE multiplexed stream (17 channels)
  - /api/content, /api/vault, /api/glance-data — content/glance endpoints
  - /api/dokku/logs — Docker log streaming for Dokku containers
  - Static SPA (dist/) with SPA fallback
"""

from __future__ import annotations
import http.server
import json
import mimetypes
import os
import subprocess
import threading
import time
import urllib.parse
from dataclasses import asdict
from http import HTTPStatus

from server.config import (
    _CHANNEL_REGISTRY, _CHANNEL_FINGERPRINTS, _fp_lock,
    _CHANNEL_BURST, _SSE_QUEUE, CA_CERT_FILE,
)
from server.sse import _sse_multiplex_drain
from server.content import list_content, read_content, save_content, list_vault, read_vault
from server.glance import _get_glance_data
from server.readers import _read_servers_config

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_DIST_DIR = os.path.join(_ROOT, "dist")
_INDEX_PATH = os.path.join(_DIST_DIR, "index.html")

# ── v2 domain config: domain → (repo_key, mode, collector_key) ────────

_DOMAIN_CONFIG = {
    "gateway":             ("gateway",             "singleton", "gateway"),
    "processes":           ("processes",           "singleton", "processes"),
    "hermes-health":       ("vps-health",          "list",      "hermes-health"),
    "prod-health":         ("vps-health",          "list",      "prod-health"),
    "profiles":            ("profiles",            "list",      "profiles"),
    "profile-stats":       ("profile-stats",       "list",      None),
    "profile-model-usage": ("profile-model-usage", "list",      None),
    "sessions":            ("sessions",            "list",      "sessions"),
    "sessions-ledger":     ("sessions-ledger",     "singleton", "sessions-ledger"),
    "ledger-breakdown":    ("ledger-breakdown",    "list",      None),
    "kanban":              ("kanban",              "list",      "kanban"),
    "dokku":               ("dokku",               "list",      "dokku"),
    "server-crons":        ("cron-jobs",           "list",      "server-crons"),
    "servers":             ("servers",             "list",      "servers"),
    "openrouter-usage":    ("openrouter-usage",    "singleton", "openrouter-usage"),
    "openrouter-activity": ("openrouter-activity", "list",      "openrouter-activity"),
    "openrouter-keys":     ("openrouter-keys",     "list",      "openrouter-keys"),
    "daily-costs":         ("daily-costs",         "list",      "daily-costs"),
    "work-system":         ("work-system",         "list",      "work-system"),
    "work-docker":         ("work-docker",         "list",      "work-docker"),
    "work-nexus":          ("work-nexus",          "list",      "work-nexus"),
    "work-jenkins":        ("work-jenkins",        "list",      "work-jenkins"),
    "work-postgres":       ("work-postgres",       "list",      "work-postgres"),
}


class MissionControlHandlerV2(http.server.BaseHTTPRequestHandler):
    """REST API handler — repos + collectors injected as class attributes.

    Usage:
        MissionControlHandlerV2.repos = { ... }
        MissionControlHandlerV2.collectors = { ... }  # {name: bound_method}
        MissionControlHandlerV2.enriched_cache = { ... }  # {event_type: enriched_data}
        server = HTTPServer((host, port), MissionControlHandlerV2)
    """

    server_version = "MissionControl/2.0"
    repos: dict = {}
    collectors: dict = {}
    enriched_cache: dict = {}

    # ── Route table ──────────────────────────────────────────────────────

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        qs = urllib.parse.parse_qs(parsed.query)

        if path.startswith("/api/v2/"):
            self._serve_v2(path[8:], qs)
        elif path == "/events":
            self._serve_sse(qs)
        elif path == "/api/dokku/logs":
            self._serve_dokku_logs(qs)
        elif path == "/api/content":
            self._serve_content_list()
        elif path == "/api/content/get":
            self._serve_content_get(qs)
        elif path == "/api/vault":
            self._serve_vault_list()
        elif path == "/api/vault/get":
            self._serve_vault_get(qs)
        elif path == "/api/glance-data":
            self._serve_glance_data()
        elif path == "/ca-cert.pem":
            self._serve_ca_cert()
        elif (path.startswith("/assets/")
              or path == "/favicon.ico"
              or path == "/sw.js"
              or path == "/manifest.webmanifest"
              or path.startswith("/icons/")
              or path == "/icon.svg"):
            self._serve_static(path)
        else:
            self._serve_index()

    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path == "/api/content/save":
            self._serve_content_save()
        else:
            self.send_error(HTTPStatus.NOT_FOUND)

    def do_OPTIONS(self):
        self.send_response(204)
        self._cors_headers()
        self.end_headers()

    # ── v2 API: /api/v2/<domain> ────────────────────────────────────────

    def _serve_v2(self, domain: str, qs: dict):
        config = _DOMAIN_CONFIG.get(domain)
        if config is None:
            self._json_error(HTTPStatus.NOT_FOUND, f"unknown domain: {domain}")
            return
        repo_key, mode, collector_key = config

        # Live mode: force collection first
        if "live" in qs:
            collector_fn = self.collectors.get(collector_key)
            if collector_fn:
                fresh = collector_fn()
                self.__class__.enriched_cache[domain] = fresh

        # Return from enriched cache if available
        cached = self.__class__.enriched_cache.get(domain)
        if cached is not None:
            self._json_response(cached)
            return

        # Fallback: repo model data (before first SSE push)
        repo = self.repos.get(repo_key)
        if repo is None:
            self._json_error(HTTPStatus.NOT_FOUND, f"no repo for: {domain}")
            return

        try:
            if mode == "singleton":
                item = repo.get_latest()
                self._json_response(asdict(item) if item else {"data": None})
            else:
                self._json_response([asdict(i) for i in repo.get_latest()])
        except Exception as e:
            self._json_error(HTTPStatus.INTERNAL_SERVER_ERROR, str(e))

    # ── SSE: /events ───────────────────────────────────────────────────

    def _serve_sse(self, qs=None):
        raw = (qs or {}).get("channels", [None])[0]
        channel_set = (
            set(c.strip() for c in raw.split(",") if c.strip())
            if raw else None
        )

        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "keep-alive")
        self._cors_headers()
        self.end_headers()

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
                    self.wfile, self.wfile.flush, _SSE_QUEUE,
                    timeout=0.5, channels=channel_set,
                )
        except (BrokenPipeError, ConnectionResetError, OSError):
            pass

    # ── Dokku logs SSE: /api/dokku/logs ───────────────────────────────

    def _serve_dokku_logs(self, qs):
        server_name = (qs.get("server", [None])[0] or "").strip()
        app_name = (qs.get("app", [None])[0] or "").strip()
        tail = (qs.get("tail", ["100"])[0] or "100").strip()

        if not server_name or not app_name:
            self.send_error(HTTPStatus.BAD_REQUEST, "Missing server or app query parameter")
            return

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
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
            )
            for line in iter(p.stdout.readline, ""):
                if not line:
                    break
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

    # ── Content endpoints ─────────────────────────────────────────────

    def _serve_content_list(self):
        docs = list_content()
        self._json_response({"documents": docs})

    def _serve_content_get(self, qs):
        rel_path = qs.get("path", [None])[0]
        if not rel_path:
            self._json_error(HTTPStatus.BAD_REQUEST, "missing 'path' parameter")
            return
        content, abs_path, err = read_content(rel_path)
        if err:
            self._json_error(HTTPStatus.BAD_REQUEST, err)
            return
        self._json_response({"path": rel_path, "abs_path": abs_path, "content": content})

    def _serve_content_save(self):
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
        self._json_response({"ok": True, "path": rel_path})

    # ── Vault endpoints ───────────────────────────────────────────────

    def _serve_vault_list(self):
        docs = list_vault()
        self._json_response({"documents": docs})

    def _serve_vault_get(self, qs):
        rel_path = qs.get("path", [None])[0]
        if not rel_path:
            self._json_error(HTTPStatus.BAD_REQUEST, "missing 'path' parameter")
            return
        content, abs_path, err = read_vault(rel_path)
        if err:
            self._json_error(HTTPStatus.BAD_REQUEST, err)
            return
        self._json_response({"path": rel_path, "abs_path": abs_path, "content": content})

    # ── Glance data ───────────────────────────────────────────────────

    def _serve_glance_data(self):
        data = _get_glance_data()
        self._json_response(data, cache_seconds=60)

    # ── CA certificate ────────────────────────────────────────────────

    def _serve_ca_cert(self):
        try:
            with open(CA_CERT_FILE, "rb") as f:
                body = f.read()
        except Exception:
            self.send_error(HTTPStatus.NOT_FOUND, "CA cert not found")
            return
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "application/x-pem-file")
        self.send_header("Content-Length", len(body))
        self.send_header("Content-Disposition", 'attachment; filename="mission-control-ca.pem"')
        self.send_header("Cache-Control", "no-cache")
        self._cors_headers()
        self.end_headers()
        self.wfile.write(body)

    # ── Static file serving ───────────────────────────────────────────

    def _serve_index(self):
        try:
            with open(_INDEX_PATH, "rb") as f:
                body = f.read()
        except Exception:
            body = b"<h1>MISSION CONTROL</h1><p>dist/index.html not found.</p>"
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", len(body))
        self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
        self._cors_headers()
        self.end_headers()
        self.wfile.write(body)

    def _serve_static(self, path: str):
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
        if os.path.basename(filepath) == "sw.js":
            self.send_header("Cache-Control", "max-age=0, must-revalidate")
            self.send_header("Service-Worker-Allowed", "/")
        else:
            self.send_header("Cache-Control", "public, max-age=3600")
        self._cors_headers()
        self.end_headers()
        self.wfile.write(body)

    # ── Response helpers ──────────────────────────────────────────────

    def _cors_headers(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")

    def _json_response(self, data, status=HTTPStatus.OK, cache_seconds=None):
        body = json.dumps(data, default=str).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", len(body))
        if cache_seconds:
            self.send_header("Cache-Control", f"public, max-age={cache_seconds}")
        else:
            self.send_header("Cache-Control", "no-cache")
        self._cors_headers()
        self.end_headers()
        self.wfile.write(body)

    def _json_error(self, status, message):
        self._json_response({"error": message}, status)

    def log_message(self, format, *args):
        pass
