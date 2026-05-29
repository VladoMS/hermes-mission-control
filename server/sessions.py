"""Session ledger builder."""

import os
from server.config import HERMES_HOME
from server.readers import read_sqlite_ro
# =============================================================================
# Unified Sessions — cross-profile session list + token ledger
# =============================================================================

def _count_sessions_in_db(path, profile_name, errors_out):
    """Count ALL sessions in a state.db without LIMIT — for real total display."""
    try:
        db = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
        db.execute("PRAGMA query_only=1")
        count = db.execute("SELECT COUNT(*) FROM sessions").fetchone()[0]
        db.close()
        return count
    except Exception as e:
        errors_out.append(f"{profile_name} state.db count: {e}")
        return 0


def _read_sessions_from_db(path, profile_name, errors_out):
    """Read sessions from a single state.db, returning list with profile attribution."""
    try:
        db = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
        db.execute("PRAGMA query_only=1")
        rows = db.execute(
            "SELECT id, title, model, started_at, ended_at, message_count, "
            "input_tokens, output_tokens, cache_read_tokens, cache_write_tokens, "
            "estimated_cost_usd, source, tool_call_count, billing_provider "
            "FROM sessions ORDER BY started_at DESC LIMIT 50"
        ).fetchall()
        cols = ["id", "title", "model", "started_at", "ended_at", "message_count",
                "input_tokens", "output_tokens", "cache_read_tokens", "cache_write_tokens",
                "estimated_cost_usd", "source", "tool_call_count", "billing_provider"]
        sessions = []
        for row in rows:
            s = dict(zip(cols, row))
            s["profile"] = profile_name
            sessions.append(s)
        db.close()
        return sessions
    except Exception as e:
        errors_out.append(f"{profile_name} state.db sessions: {e}")
        return []


def build_unified_sessions(profiles, errors_out):
    """Build a unified session list from all state.dbs with profile attribution.
    Also cross-references sessions.json for display_name (title fallback).
    Returns (capped_list, total_count) — list limited to 50 for display, but
    total_count is the real unfiltered session count across all state.dbs."""
    all_sessions = []
    total_count = 0

    # Root state.db
    root_path = os.path.join(HERMES_HOME, "state.db")
    if os.path.exists(root_path):
        all_sessions.extend(_read_sessions_from_db(root_path, "default", errors_out))
        total_count += _count_sessions_in_db(root_path, "default", errors_out)

    # Per-profile state.dbs
    for profile in profiles:
        name = profile.get("name", "")
        if name == "default":
            continue
        prof_dir = os.path.join(HERMES_HOME, "profiles", name)
        state_path = os.path.join(prof_dir, "state.db")
        if os.path.exists(state_path):
            all_sessions.extend(_read_sessions_from_db(state_path, name, errors_out))
            total_count += _count_sessions_in_db(state_path, name, errors_out)

    # Cross-reference with sessions.json for display_name (title fallback)
    try:
        sessions_json = read_json(os.path.join(HERMES_HOME, "sessions", "sessions.json"))
        if sessions_json and isinstance(sessions_json, dict):
            # Build lookup: session_id -> display_name
            display_names = {}
            for k, v in sessions_json.items():
                if isinstance(v, dict) and v.get("session_id"):
                    display_names[v["session_id"]] = v.get("display_name", "")
            for s in all_sessions:
                sid = s.get("id")
                if sid and sid in display_names and display_names[sid]:
                    s["display_name"] = display_names[sid]
    except Exception:
        pass

    # Sort by started_at desc, limit to 50 for display
    all_sessions.sort(key=lambda s: s.get("started_at", 0) or 0, reverse=True)
    return all_sessions[:50], total_count


def build_sessions_ledger(all_sessions, total_session_count=None):
    """Compute aggregate token/cost stats from a unified session list.
    total_session_count is the real unfiltered count (all_sessions may be capped).
    Returns dict with totals, per-model breakdown, per-profile breakdown, cache hit rate."""
    total_input = 0
    total_output = 0
    total_cache_read = 0
    total_cache_write = 0
    total_cost = 0.0

    per_model = {}
    per_profile = {}

    for s in (all_sessions or []):
        inp = s.get("input_tokens") or 0
        out = s.get("output_tokens") or 0
        cr = s.get("cache_read_tokens") or 0
        cw = s.get("cache_write_tokens") or 0
        cost = s.get("estimated_cost_usd") or 0

        total_input += inp
        total_output += out
        total_cache_read += cr
        total_cache_write += cw
        if cost and cost > 0:
            total_cost += cost

        model = s.get("model") or "unknown"
        profile = s.get("profile") or "unknown"

        if model not in per_model:
            per_model[model] = {"input_tokens": 0, "output_tokens": 0,
                               "cache_read_tokens": 0, "cache_write_tokens": 0,
                               "sessions": 0, "estimated_cost_usd": 0.0}
        pm = per_model[model]
        pm["input_tokens"] += inp
        pm["output_tokens"] += out
        pm["cache_read_tokens"] += cr
        pm["cache_write_tokens"] += cw
        pm["sessions"] += 1
        pm["estimated_cost_usd"] += cost

        if profile not in per_profile:
            per_profile[profile] = {"input_tokens": 0, "output_tokens": 0,
                                    "cache_read_tokens": 0, "cache_write_tokens": 0,
                                    "sessions": 0, "estimated_cost_usd": 0.0}
        pp = per_profile[profile]
        pp["input_tokens"] += inp
        pp["output_tokens"] += out
        pp["cache_read_tokens"] += cr
        pp["cache_write_tokens"] += cw
        pp["sessions"] += 1
        pp["estimated_cost_usd"] += cost

    total_cache = total_cache_read + total_cache_write
    total_all = total_input + total_output + total_cache

    # Cache hit rate: cache_read / (cache_read + input)
    denominator = total_cache_read + total_input
    cache_hit_rate = round(100.0 * total_cache_read / denominator, 1) if denominator > 0 else 0.0

    # Sort per_model and per_profile by total tokens desc
    def _tok_sum(d):
        return d.get("input_tokens", 0) + d.get("output_tokens", 0) + d.get("cache_read_tokens", 0) + d.get("cache_write_tokens", 0)

    sorted_models = dict(sorted(per_model.items(), key=lambda kv: _tok_sum(kv[1]), reverse=True))
    sorted_profiles = dict(sorted(per_profile.items(), key=lambda kv: _tok_sum(kv[1]), reverse=True))

    return {
        "total_input_tokens": total_input,
        "total_output_tokens": total_output,
        "total_cache_read_tokens": total_cache_read,
        "total_cache_write_tokens": total_cache_write,
        "total_cache_tokens": total_cache,
        "total_tokens": total_all,
        "total_estimated_cost_usd": round(total_cost, 4),
        "cache_hit_rate_pct": cache_hit_rate,
        "per_model": sorted_models,
        "per_profile": sorted_profiles,
        "session_count": total_session_count if total_session_count is not None else len(all_sessions or []),
    }
