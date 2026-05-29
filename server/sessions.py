"""Session ledger builder."""

import os
import sqlite3
import time
from server.config import HERMES_HOME
from server.readers import read_sqlite_ro, read_json
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


def _read_daily_costs_from_db(path, errors_out):
    """Read per-day cost from a single state.db (last 90 days, no limit)."""
    try:
        db = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
        db.execute("PRAGMA query_only=1")
        rows = db.execute(
            "SELECT started_at, estimated_cost_usd "
            "FROM sessions "
            "WHERE started_at IS NOT NULL "
            "ORDER BY started_at ASC"
        ).fetchall()
        db.close()
        return rows
    except Exception as e:
        errors_out.append(f"state.db daily costs: {e}")
        return []


def build_daily_costs(profiles, errors_out, openrouter_usage=None):
    """Build per-day cost breakdown from all state.dbs.

    Queries ALL sessions with started_at + cost, groups by day,
    sorts chronologically, and appends a linear-regression prediction.

    If openrouter_usage is provided, today's cost is overridden with
    the OpenRouter API's usage_daily_usd (the authoritative source).
    This corrects for sessions where estimated_cost_usd is missing
    due to model name formatting inconsistencies in state.db.

    Returns a dict with 'days' (array of {date, cost, prediction}),
    'daily_average' (float), 'today_so_far' (float), and
    'openrouter_daily' (float or None).
    """
    from collections import defaultdict
    daily = defaultdict(float)

    def _process(path):
        for started_at, cost in _read_daily_costs_from_db(path, errors_out):
            if not started_at:
                continue
            # started_at may be Unix timestamp (int/float) or ISO string
            try:
                if isinstance(started_at, (int, float)):
                    ts = float(started_at)
                else:
                    ts = float(started_at)
            except (ValueError, TypeError):
                continue
            date_str = time.strftime("%Y-%m-%d", time.gmtime(ts))
            daily[date_str] += float(cost or 0)

    # Root state.db
    root_path = os.path.join(HERMES_HOME, "state.db")
    if os.path.exists(root_path):
        _process(root_path)

    # Per-profile state.dbs
    for profile in (profiles or []):
        name = profile.get("name", "")
        if name == "default":
            continue
        state_path = os.path.join(HERMES_HOME, "profiles", name, "state.db")
        if os.path.exists(state_path):
            _process(state_path)

    if not daily:
        return {"days": [], "daily_average": 0.0, "today_so_far": 0.0, "openrouter_daily": None}

    # Sort by date
    sorted_dates = sorted(daily.keys())
    days = [{"date": d, "cost": round(daily[d], 6), "prediction": None} for d in sorted_dates]

    # Compute daily average (exclude today — partial day)
    today_str = time.strftime("%Y-%m-%d", time.gmtime())
    past_days = [d for d in sorted_dates if d != today_str]
    past_costs = [daily[d] for d in past_days]
    daily_average = sum(past_costs) / len(past_costs) if past_costs else 0.0

    # ── OpenRouter cross-reference ──
    # Override today's cost with the authoritative OpenRouter API value.
    # state.db estimated_cost_usd is unreliable: some sessions have model
    # names without provider prefix, causing cost estimation to return $0.
    or_daily = None
    if openrouter_usage and isinstance(openrouter_usage, dict):
        or_daily = openrouter_usage.get("usage_daily_usd")
        if or_daily and isinstance(or_daily, (int, float)) and or_daily > 0:
            # Replace today's entry in the days array
            for d in days:
                if d["date"] == today_str:
                    d["cost"] = round(float(or_daily), 6)
                    break
            else:
                # No today entry exists yet — add one
                days.append({
                    "date": today_str,
                    "cost": round(float(or_daily), 6),
                    "prediction": None,
                })

    # Linear regression on last 14 days for prediction
    prediction_days = []
    if len(past_days) >= 3:
        N = min(14, len(past_days))
        recent = past_days[-N:]
        xs = list(range(N))
        ys = [daily[d] for d in recent]

        n = len(xs)
        sum_x = sum(xs)
        sum_y = sum(ys)
        sum_xy = sum(x * y for x, y in zip(xs, ys))
        sum_xx = sum(x * x for x in xs)
        denom = n * sum_xx - sum_x * sum_x
        if denom != 0:
            slope = (n * sum_xy - sum_x * sum_y) / denom
            intercept = (sum_y - slope * sum_x) / n
            # Predict next 3 days starting AFTER the last actual day
            last_actual = sorted_dates[-1]
            for i in range(1, 4):
                pred_val = max(0.0, intercept + slope * (N + i - 1))
                pred_date = _add_days(last_actual, i)
                prediction_days.append({
                    "date": pred_date,
                    "cost": 0.0,
                    "prediction": round(pred_val, 6),
                })

    today_cost = or_daily if or_daily else daily.get(today_str, 0.0)
    return {
        "days": days + prediction_days,
        "daily_average": round(daily_average, 6),
        "today_so_far": round(today_cost, 6),
        "openrouter_daily": round(or_daily, 6) if or_daily else None,
        "monthly_projection": round(today_cost * 30, 6),
    }


def _add_days(date_str, n):
    """Add n days to a YYYY-MM-DD date string."""
    from datetime import datetime, timedelta
    dt = datetime.strptime(date_str, "%Y-%m-%d")
    return (dt + timedelta(days=n)).strftime("%Y-%m-%d")


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
