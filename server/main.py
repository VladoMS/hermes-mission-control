"""Mission Control entry point — server bootstrap and lifecycle.

Phase 6: fully migrated to new architecture. SSE publishers use collector
classes (write to normalized repos + return payloads). New REST handler
(MissionControlHandlerV2) serves v2 API, legacy polling fallback, SSE,
content/vault/glance endpoints. Old handler.py, collectors.py, snapshot.py,
dashboard_db.py removed.
"""

import http.server
import os
import ssl
import subprocess
import sys
import threading

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from server.config import (
    HOST, PORT, CERT_DIR, CERT_FILE, KEY_FILE, DASHBOARD_DB,
    _SSE_QUEUE, _CHANNEL_REGISTRY,
)
from server.sse import publish_channel

from server.infrastructure.database import Database
from server.infrastructure.repositories import (
    SqliteGatewayRepository, SqliteProcessListRepository,
    SqliteVpsHealthRepository, SqliteCronJobRepository,
    SqliteServerHealthRepository, SqliteDokkuAppRepository,
    SqliteProfileRepository, SqliteProfileStatsRepository,
    SqliteProfileModelUsageRepository, SqliteSessionRepository,
    SqliteSessionLedgerRepository, SqliteLedgerBreakdownRepository,
    SqliteKanbanTaskRepository, SqliteOpenRouterUsageRepository,
    SqliteOpenRouterActivityRepository,
    SqliteOpenRouterKeyRepository,
    SqliteDailyCostRepository,
    SqliteWorkServerHealthRepository, SqliteWorkDockerRepository,
    SqliteWorkNexusRepository, SqliteWorkJenkinsRepository,
    SqliteWorkPostgresRepository,
)
from server.application.collectors import (
    GatewayCollector, ProcessListCollector,
    HermesHealthCollector, ProdHealthCollector,
    ProfileCollector, SessionCollector,
    SessionLedgerCollector, KanbanCollector,
    DokkuCollector, ServerCronCollector, ServerCollector,
    OpenRouterUsageCollector, OpenRouterActivityCollector,
    OpenRouterKeyCollector, DailyCostCollector,
    WorkSystemCollector, WorkDockerCollector,
    WorkNexusCollector, WorkJenkinsCollector, WorkPostgresCollector,
)
from server.interfaces.rest import MissionControlHandlerV2


class ThreadingHTTPServer(http.server.ThreadingHTTPServer):
    allow_reuse_address = True
    daemon_threads = True


def _ensure_cert():
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


def _build_repos(db_path: str) -> dict:
    db = Database(db_path)
    db.initialize()
    return {
        "gateway":              SqliteGatewayRepository(db_path),
        "processes":            SqliteProcessListRepository(db_path),
        "vps-health":           SqliteVpsHealthRepository(db_path),
        "profiles":             SqliteProfileRepository(db_path),
        "profile-stats":        SqliteProfileStatsRepository(db_path),
        "profile-model-usage":  SqliteProfileModelUsageRepository(db_path),
        "sessions":             SqliteSessionRepository(db_path),
        "sessions-ledger":      SqliteSessionLedgerRepository(db_path),
        "ledger-breakdown":     SqliteLedgerBreakdownRepository(db_path),
        "kanban":               SqliteKanbanTaskRepository(db_path),
        "cron-jobs":            SqliteCronJobRepository(db_path),
        "servers":              SqliteServerHealthRepository(db_path),
        "dokku":                SqliteDokkuAppRepository(db_path),
        "openrouter-usage":     SqliteOpenRouterUsageRepository(db_path),
        "openrouter-activity":  SqliteOpenRouterActivityRepository(db_path),
        "openrouter-keys":      SqliteOpenRouterKeyRepository(db_path),
        "daily-costs":          SqliteDailyCostRepository(db_path),
        "work-system":          SqliteWorkServerHealthRepository(db_path),
        "work-docker":          SqliteWorkDockerRepository(db_path),
        "work-nexus":           SqliteWorkNexusRepository(db_path),
        "work-jenkins":         SqliteWorkJenkinsRepository(db_path),
        "work-postgres":        SqliteWorkPostgresRepository(db_path),
    }


def _build_collectors(repos: dict) -> dict:
    or_collector = OpenRouterUsageCollector(repos["openrouter-usage"])
    or_activity_collector = OpenRouterActivityCollector(repos["openrouter-activity"])
    or_keys_collector = OpenRouterKeyCollector(repos["openrouter-keys"])
    return {
        "gateway":              GatewayCollector(repos["gateway"]),
        "processes":            ProcessListCollector(repos["processes"]),
        "hermes-health":        HermesHealthCollector(repos["vps-health"]),
        "prod-health":          ProdHealthCollector(repos["vps-health"]),
        "profiles":             ProfileCollector(repos["profiles"], repos["profile-stats"], repos["profile-model-usage"]),
        "sessions":             SessionCollector(repos["sessions"]),
        "sessions-ledger":      SessionLedgerCollector(repos["sessions-ledger"], repos["ledger-breakdown"], repos["openrouter-activity"]),
        "kanban":               KanbanCollector(repos["kanban"]),
        "dokku":                DokkuCollector(repos["dokku"]),
        "server-crons":         ServerCronCollector(repos["cron-jobs"]),
        "servers":              ServerCollector(repos["servers"]),
        "openrouter-usage":     or_collector,
        "openrouter-activity":  or_activity_collector,
        "openrouter-keys":      or_keys_collector,
        "daily-costs":          DailyCostCollector(repos["daily-costs"], or_collector, repos["openrouter-activity"], repos["openrouter-keys"]),
        "work-system":          WorkSystemCollector(repos["work-system"]),
        "work-docker":          WorkDockerCollector(repos["work-docker"]),
        "work-nexus":           WorkNexusCollector(repos["work-nexus"]),
        "work-jenkins":         WorkJenkinsCollector(repos["work-jenkins"]),
        "work-postgres":        WorkPostgresCollector(repos["work-postgres"]),
    }


def main():
    # ── Initialize new infrastructure ──────────────────────────────────
    repos = _build_repos(DASHBOARD_DB)
    collectors = _build_collectors(repos)
    collector_fns = {k: v.collect for k, v in collectors.items()}

    # Wire REST handler with enriched data cache
    enriched_cache = {}
    MissionControlHandlerV2.repos = repos
    MissionControlHandlerV2.collectors = collector_fns
    MissionControlHandlerV2.enriched_cache = enriched_cache

    # Start SSE publisher threads
    _publisher_threads = []
    for event_type, interval, tier in _CHANNEL_REGISTRY:
        collector = collector_fns.get(event_type)
        if collector is None:
            print(f"  WARNING: no collector for channel '{event_type}' — skipping")
            continue

        def _collect_and_cache(event_type=event_type, collector=collector):
            data = collector()
            enriched_cache[event_type] = data
            return data

        t = threading.Thread(
            target=publish_channel,
            args=(event_type, _collect_and_cache, interval, _SSE_QUEUE),
            daemon=True,
            name=f"ch-{event_type}",
        )
        t.start()
        _publisher_threads.append(t)
        print(f"  ▶ publisher: {event_type} every {interval}s (tier {tier})")

    print(f"  ▶ {len(_publisher_threads)} channel publishers started\n")

    cert_path, key_path = _ensure_cert()
    server = ThreadingHTTPServer((HOST, PORT), MissionControlHandlerV2)
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    ctx.load_cert_chain(cert_path, key_path)
    server.socket = ctx.wrap_socket(server.socket, server_side=True)

    print(f"▶ MISSION CONTROL (v2) listening on https://{HOST}:{PORT}")
    print(f"  GET /                     → SPA (index.html)")
    print(f"  GET /api/v2/<domain>      → normalized per-domain JSON")
    print(f"  GET /api/v2/<domain>?live → force collect then read")
    print(f"  GET /api/<channel>         → legacy polling fallback (18 channels)")
    print(f"  GET /events               → SSE multiplexed stream")
    print(f"  GET /api/content          → document list")
    print(f"  GET /api/content/get      → document content")
    print(f"  POST /api/content/save    → save document")
    print(f"  GET /api/vault            → vault document list")
    print(f"  GET /api/vault/get        → vault document content")
    print(f"  GET /api/glance-data      → weather + Twitch + timezones")
    print(f"  GET /api/dokku/logs       → docker log streaming SSE")
    print(f"  GET /ca-cert.pem          → CA certificate download")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n▼ Shutting down.")
        server.shutdown()


if __name__ == "__main__":
    main()
