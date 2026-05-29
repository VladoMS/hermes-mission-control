"""Per-channel data collectors."""

import os
import json
from server.config import HERMES_HOME
from server.readers import read_json, _read_servers_config
from server.health import get_hermes_health, get_prod_health
from server.profiles import build_profiles
from server.sessions import build_unified_sessions, build_sessions_ledger, build_daily_costs
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


def collect_openrouter_usage():
    """Collect OpenRouter credit usage and rate limit info from /api/v1/auth/key.
    Reads OPENROUTER_API_KEY from Hermes .env. Never raises."""
    import urllib.request
    import urllib.error
    import re

    # Read API key from Hermes .env
    api_key = None
    env_path = os.path.join(HERMES_HOME, ".env")
    try:
        with open(env_path, "r") as f:
            for line in f:
                m = re.match(r'^OPENROUTER_API_KEY\s*=\s*(.+)$', line.strip())
                if m:
                    api_key = m.group(1).strip().strip('"').strip("'")
                    break
    except Exception:
        pass

    if not api_key:
        return {"error": "OPENROUTER_API_KEY not found in .env"}

    try:
        req = urllib.request.Request(
            "https://openrouter.ai/api/v1/auth/key",
            headers={"Authorization": f"Bearer {api_key}"}
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            body = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        return {"error": f"OpenRouter API HTTP {e.code}: {e.reason}"}
    except urllib.error.URLError as e:
        return {"error": f"OpenRouter API unreachable: {e.reason}"}
    except json.JSONDecodeError:
        return {"error": "OpenRouter API returned invalid JSON"}
    except Exception as e:
        return {"error": f"OpenRouter API error: {e}"}

    data = body.get("data", {}) if isinstance(body, dict) else {}

    rate = data.get("rate_limit", {}) or {}
    limit = data.get("limit")
    limit_remaining = data.get("limit_remaining")

    return {
        "total_usage_usd": data.get("usage", 0),
        "usage_daily_usd": data.get("usage_daily", 0),
        "usage_weekly_usd": data.get("usage_weekly", 0),
        "usage_monthly_usd": data.get("usage_monthly", 0),
        "byok_usage_usd": data.get("byok_usage", 0),
        "credit_limit_usd": limit,
        "credit_remaining_usd": limit_remaining,
        "is_free_tier": data.get("is_free_tier", False),
        "rate_limit_requests": rate.get("requests", -1),
        "rate_limit_interval": rate.get("interval", "10s"),
    }


def collect_daily_costs():
    """Collect per-day cost breakdown with linear regression prediction.

    Cross-references OpenRouter API for today's authoritative cost figure
    (state.db estimated_cost_usd is unreliable for sessions where the model
    name lacks the provider prefix).

    Returns dict with 'days' (array of {date, cost, prediction}),
    'daily_average' (float), 'today_so_far' (float), and
    'openrouter_daily' (float or None). Never raises."""
    profiles = build_profiles([])
    # Fetch OpenRouter usage for today's authoritative cost
    or_usage = collect_openrouter_usage()
    return build_daily_costs(profiles, [], openrouter_usage=or_usage)

