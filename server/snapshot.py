"""Snapshot assembly and channel collector registry."""

import json
import os
import time
from server.config import HERMES_HOME
from server.dashboard_db import _save_snapshot_to_db
from server.readers import read_json
from server.health import get_hermes_health, get_prod_health
from server.profiles import build_profiles
from server.sessions import build_unified_sessions, build_sessions_ledger
from server.servers import build_servers
from server.kanban import read_kanban_boards
from server.cron_parser import build_crons
from server.collectors import collect_gateway, collect_processes, collect_hermes_health, collect_sessions_ledger, collect_profiles, collect_sessions, collect_kanban, collect_prod_health, collect_dokku, collect_server_crons, collect_servers
from server.work_servers import collect_work_system_health, collect_work_docker, collect_work_nexus, collect_work_jenkins, collect_work_postgres


# Map event_type → collector function (used by publisher threads and REST endpoints)
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
    "servers":          collect_servers,
    # Work servers (Tier 3 — slow, cached)
    "work-system":      collect_work_system_health,
    "work-docker":      collect_work_docker,
    "work-nexus":       collect_work_nexus,
    "work-jenkins":     collect_work_jenkins,
    "work-postgres":    collect_work_postgres,
}


# =============================================================================
# Snapshot assembly
# =============================================================================

def build_snapshot():
    """Build the complete /api/snapshot JSON payload."""
    errors = []
    snapshot = {
        "timestamp": time.time(),
        "timestamp_iso": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "errors": errors,
    }

    # --- Gateway ---
    gw = read_json(os.path.join(HERMES_HOME, "gateway_state.json"))
    if gw is not None:
        snapshot["gateway"] = gw
    else:
        errors.append("gateway_state.json: read failed")
        snapshot["gateway"] = {}

    # --- Cron jobs (Hermes + system) — kept for backward compat, crons live per-server now ---
    snapshot["crons"] = build_crons(errors)

    # --- Servers (dynamic from servers.json) — replaces standalone VPS health ---
    snapshot["servers"] = build_servers(errors)

    # --- Profiles ---
    snapshot["profiles"] = build_profiles(errors)

    # --- Sessions — unified cross-profile list from all state.dbs ---
    unified, total_session_count = build_unified_sessions(snapshot["profiles"], errors)
    snapshot["sessions"] = unified
    snapshot["sessions_ledger"] = build_sessions_ledger(unified, total_session_count)

    # --- Processes ---
    procs = read_json(os.path.join(HERMES_HOME, "processes.json"))
    snapshot["processes"] = procs if procs is not None else []

    # --- Kanban boards (clean grouped structure) ---
    snapshot["kanban"] = read_kanban_boards(errors)

    # --- VPS Health ---
    snapshot["vps"] = {
        "hermes": get_hermes_health(errors),
        "prod": get_prod_health(errors),
    }

    # Save to local retention DB (non-critical — dashboard works without it)
    try:
        _save_snapshot_to_db(json.dumps(snapshot, default=str), len(errors))
    except Exception:
        pass

    return snapshot

