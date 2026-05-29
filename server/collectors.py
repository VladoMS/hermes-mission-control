"""Per-channel data collectors."""

import os
import json
from server.config import HERMES_HOME
from server.readers import read_json
from server.health import get_hermes_health, get_prod_health
from server.profiles import build_profiles
from server.sessions import build_unified_sessions, build_sessions_ledger
from server.servers import build_servers
from server.kanban import read_kanban_boards
# =============================================================================
# Channel collectors — one function per data source
# Each is thread-safe, never raises, and returns a dict
# =============================================================================

def collect_gateway():
    """Collect gateway state. Returns the raw gateway dict, never raises."""
    gw = read_json(os.path.join(HERMES_HOME, "gateway_state.json"))
    if gw is None:
        return {"error": "gateway_state.json: read failed", "gateway_state": "unknown"}
    return gw


def collect_processes():
    """Collect managed process list. Returns dict, never raises."""
    procs = read_json(os.path.join(HERMES_HOME, "processes.json"))
    return {"processes": procs if procs is not None else []}


def collect_hermes_health():
    """Collect local VPS health. Returns dict, never raises."""
    errors = []
    result = get_hermes_health(errors)
    return {"health": result, "errors": errors}


def collect_sessions_ledger():
    """Collect aggregated session counts and token totals from all state.dbs.
    Returns the same structure as build_sessions_ledger() but collected independently."""
    profiles = build_profiles([])  # silent — errors go to a discard list
    unified, total_count = build_unified_sessions(profiles, [])
    ledger = build_sessions_ledger(unified, total_count)
    return ledger


def collect_profiles():
    """Collect profile list — returns array directly (matches old snapshot.profiles shape)."""
    errors = []
    return build_profiles(errors)


def collect_sessions():
    """Collect unified session list (top 50) — returns array directly."""
    profiles = build_profiles([])
    unified, _ = build_unified_sessions(profiles, [])
    return unified


def collect_servers():
    """Collect full server list — returns array directly (matches old snapshot.servers shape)."""
    errors = []
    return build_servers(errors)


def collect_kanban():
    """Collect kanban boards — returns dict matching old snapshot.kanban shape."""
    errors = []
    result = read_kanban_boards(errors)
    result["errors"] = errors
    return result


def collect_prod_health():
    """Collect prod VPS health (SSH, TTL-cached). Returns dict."""
    errors = []
    health = get_prod_health(errors)
    return {"health": health, "errors": errors}


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

