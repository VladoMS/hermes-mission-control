"""Session ledger builder."""

import os
import sqlite3
import time
from server.config import HERMES_HOME
from server.readers import read_sqlite_ro, read_json

# ── OpenRouter per-model pricing (USD per 1M tokens) ──────────────
# Source: https://openrouter.ai/models (verified May 2026)
# Cache reads are billed at 50% of input price on most models.
# NOTE: This static table is a fallback.  At runtime we FIRST derive
# per-model rates from sessions with valid estimated_cost_usd (see
# _build_model_pricing_cache), which catches aliases and unknown models.
OPENROUTER_PRICING = {
    "openai/gpt-4o":                    {"input": 2.50,  "output": 10.00},
    "openai/gpt-4o-2024-08-06":         {"input": 2.50,  "output": 10.00},
    "openai/gpt-4o-mini":               {"input": 0.15,  "output": 0.60},
    "openai/gpt-4o-mini-2024-07-18":    {"input": 0.15,  "output": 0.60},
    "openai/gpt-4-turbo":               {"input": 10.00, "output": 30.00},
    "openai/o1":                        {"input": 15.00, "output": 60.00},
    "openai/o1-mini":                   {"input": 3.00,  "output": 12.00},
    "openai/o3-mini":                   {"input": 1.10,  "output": 4.40},
    "openai/gpt-4.1":                   {"input": 2.00,  "output": 8.00},
    "openai/gpt-4.1-mini":              {"input": 0.40,  "output": 1.60},
    "openai/gpt-4.1-nano":              {"input": 0.10,  "output": 0.40},
    "anthropic/claude-3.5-sonnet":      {"input": 3.00,  "output": 15.00},
    "anthropic/claude-3.5-haiku":       {"input": 0.80,  "output": 4.00},
    "anthropic/claude-3-opus":          {"input": 15.00, "output": 75.00},
    "anthropic/claude-3-haiku":         {"input": 0.25,  "output": 1.25},
    "anthropic/claude-opus-4":          {"input": 15.00, "output": 75.00},
    "anthropic/claude-sonnet-4":        {"input": 15.00, "output": 75.00},
    "anthropic/claude-sonnet-4-20250514":{"input": 15.00, "output": 75.00},
    "google/gemini-2.0-flash":          {"input": 0.10,  "output": 0.40},
    "google/gemini-2.0-flash-001":      {"input": 0.10,  "output": 0.40},
    "google/gemini-2.5-pro":            {"input": 1.25,  "output": 5.00},
    "google/gemini-2.5-flash":          {"input": 0.15,  "output": 0.60},
    "google/gemini-2.0-flash-lite":     {"input": 0.075, "output": 0.30},
    "google/gemma-3-27b-it":            {"input": 0.13,  "output": 0.52},
    "deepseek/deepseek-chat":           {"input": 0.14,  "output": 0.28},
    "deepseek/deepseek-r1":             {"input": 0.55,  "output": 2.19},
    "deepseek/deepseek-r1-distill-llama-70b": {"input": 0.23, "output": 0.92},
    "deepseek/deepseek-v4-pro":         {"input": 0.20,  "output": 0.80},
    "deepseek/deepseek-v4-flash":       {"input": 0.075, "output": 0.30},
    "mistral/mistral-large":            {"input": 2.00,  "output": 6.00},
    "mistral/mistral-large-2407":       {"input": 2.00,  "output": 6.00},
    "mistral/mistral-small":            {"input": 1.00,  "output": 3.00},
    "meta-llama/llama-3.3-70b":         {"input": 0.25,  "output": 1.00},
    "meta-llama/llama-3.1-405b":        {"input": 2.00,  "output": 6.00},
    "meta-llama/llama-3.1-70b":         {"input": 0.25,  "output": 1.00},
    "meta-llama/llama-3.1-8b":          {"input": 0.05,  "output": 0.20},
    "qwen/qwen-2.5-72b":               {"input": 0.35,  "output": 1.40},
    "qwen/qwen-2.5-32b":               {"input": 0.18,  "output": 0.72},
    "qwen/qwen-2.5-coder-32b":         {"input": 0.18,  "output": 0.72},
    "qwen/qwq-32b":                    {"input": 0.18,  "output": 0.72},
    "cohere/command-r-plus":            {"input": 3.00,  "output": 15.00},
    "cohere/command-r":                 {"input": 0.50,  "output": 1.50},
    "nousresearch/hermes-3-llama-3.1-405b": {"input": 1.00, "output": 2.00},
}

# Short-name aliases (model names stored in state.db without provider prefix)
_SHORT_NAME_MAP = {}
for _full_key in OPENROUTER_PRICING:
    _short = _full_key.split("/", 1)[-1]
    _SHORT_NAME_MAP[_short] = _full_key


def _resolve_model_pricing(model_name):
    """Look up per-token pricing for a model name.
    Returns (input_price_per_1M, output_price_per_1M) or (0, 0) if unknown."""
    if not model_name:
        return (0.0, 0.0)
    if model_name in OPENROUTER_PRICING:
        p = OPENROUTER_PRICING[model_name]
        return (p["input"], p["output"])
    if model_name in _SHORT_NAME_MAP:
        p = OPENROUTER_PRICING[_SHORT_NAME_MAP[model_name]]
        return (p["input"], p["output"])
    return (0.0, 0.0)


# ── Runtime-derived pricing cache ──────────────────────────────

def _build_model_pricing_cache(profile_list):
    """Scan all state.dbs for sessions with valid estimated_cost_usd and derive
    an effective cost-per-effective-token rate for each model.

    "Effective tokens" = input + output + cache_read×0.5 + cache_write
    (cache reads cost ~50% of input tokens on most OpenRouter models).

    Returns {model_name_lower: rate_per_effective_token}.
    Both the full OpenRouter ID and the short name (without provider prefix)
    are indexed so that e.g. 'deepseek-v4-pro' maps to the same rate derived
    from 'deepseek/deepseek-v4-pro' sessions."""
    cache = {}
    paths = []

    root = os.path.join(HERMES_HOME, "state.db")
    if os.path.exists(root):
        paths.append(root)

    for profile in (profile_list or []):
        name = profile.get("name", "")
        if name == "default":
            continue
        p = os.path.join(HERMES_HOME, "profiles", name, "state.db")
        if os.path.exists(p):
            paths.append(p)

    for path in paths:
        try:
            db = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
            db.execute("PRAGMA query_only=1")
            rows = db.execute(
                "SELECT model, input_tokens, output_tokens, "
                "cache_read_tokens, cache_write_tokens, estimated_cost_usd "
                "FROM sessions "
                "WHERE estimated_cost_usd IS NOT NULL AND estimated_cost_usd > 0 "
                "AND (input_tokens > 0 OR output_tokens > 0 "
                "     OR cache_read_tokens > 0 OR cache_write_tokens > 0)"
            ).fetchall()
            db.close()
            for row in rows:
                model = row[0]
                if not model:
                    continue
                inp = float(row[1] or 0)
                out = float(row[2] or 0)
                cr = float(row[3] or 0)
                cw = float(row[4] or 0)
                cost = float(row[5])
                effective = inp + out + cr * 0.5 + cw
                if effective <= 0:
                    continue
                rate = cost / effective
                key = model.lower()
                if key not in cache or rate > cache[key]:
                    cache[key] = rate
                # Also index under the short name (suffix after '/')
                if "/" in model:
                    short = model.split("/", 1)[-1].lower()
                    if short not in cache or rate > cache[short]:
                        cache[short] = rate
        except Exception:
            continue
    return cache


def _compute_session_cost(model, input_tks, output_tks, cache_read_tks, cache_write_tks, estimated_cost_usd, pricing_cache=None):
    """Return the best known cost for a session.

    Priority:
    1. estimated_cost_usd (if present and > 0) — authoritative
    2. Runtime-derived pricing cache (from sessions with valid cost)
    3. Static OPENROUTER_PRICING table (fallback)
    4. $0.00 — unknown model, no data"""
    if estimated_cost_usd and estimated_cost_usd > 0:
        return float(estimated_cost_usd)

    inp = float(input_tks or 0)
    out = float(output_tks or 0)
    cr = float(cache_read_tks or 0)
    cw = float(cache_write_tks or 0)
    effective = inp + out + cr * 0.5 + cw
    if effective <= 0:
        return 0.0

    # Try runtime-derived cache first (catches aliases, e.g. deepseek-v4-pro
    # when the cache was built from deepseek/deepseek-v4-pro sessions)
    if pricing_cache and model:
        key = model.lower()
        if key in pricing_cache:
            return round(effective * pricing_cache[key], 6)

    # Fall back to static pricing table
    inp_price, out_price = _resolve_model_pricing(model)
    if inp_price > 0 or out_price > 0:
        cost = (inp * inp_price + out * out_price + cr * inp_price * 0.5 + cw * inp_price) / 1_000_000
        return round(cost, 6)

    return 0.0
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
    """Read per-session cost data from a single state.db (all rows, no limit).
    Returns list of dicts with started_at, model, token counts, and estimated_cost_usd."""
    try:
        db = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
        db.execute("PRAGMA query_only=1")
        rows = db.execute(
            "SELECT started_at, model, "
            "input_tokens, output_tokens, cache_read_tokens, cache_write_tokens, "
            "estimated_cost_usd "
            "FROM sessions "
            "WHERE started_at IS NOT NULL "
            "ORDER BY started_at ASC"
        ).fetchall()
        db.close()
        result = []
        for row in rows:
            result.append({
                "started_at": row[0],
                "model": row[1],
                "input_tokens": row[2],
                "output_tokens": row[3],
                "cache_read_tokens": row[4],
                "cache_write_tokens": row[5],
                "estimated_cost_usd": row[6],
            })
        return result
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

    # Build derived pricing cache from sessions that have valid cost data.
    # This lets us compute token-based cost for same-model sessions that
    # don't (e.g. deepseek-v4-pro from deepseek/deepseek-v4-pro rates).
    pricing_cache = _build_model_pricing_cache(profiles)

    daily = defaultdict(float)

    def _process(path):
        for s in _read_daily_costs_from_db(path, errors_out):
            started_at = s["started_at"]
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
            cost = _compute_session_cost(
                s["model"], s["input_tokens"], s["output_tokens"],
                s["cache_read_tokens"], s["cache_write_tokens"],
                s["estimated_cost_usd"],
                pricing_cache,
            )
            date_str = time.strftime("%Y-%m-%d", time.gmtime(ts))
            daily[date_str] += cost

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


def build_sessions_ledger(all_sessions, total_session_count=None, pricing_cache=None):
    """Compute aggregate token/cost stats from a unified session list.
    total_session_count is the real unfiltered count (all_sessions may be capped).
    pricing_cache is an optional dict from _build_model_pricing_cache() for
    computing cost on sessions missing estimated_cost_usd.
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
        cost = _compute_session_cost(
            s.get("model"), inp, out, cr, cw,
            s.get("estimated_cost_usd"),
            pricing_cache,
        )

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
