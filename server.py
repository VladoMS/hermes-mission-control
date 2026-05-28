#!/usr/bin/env python3
"""
Mission Control — backend server for Hermes agent dashboard.
Phase 1: Data Layer

Serves:
  GET /            → index.html
  GET /api/snapshot → full JSON snapshot of all data sources
  GET /events       → SSE stream (snapshot every 5 seconds)

Python stdlib only. No pip, no npm.
"""

import hashlib
import http.server
import json
import os
import queue as queue_module
import sqlite3
import subprocess
import threading
import time
import urllib.parse
import urllib.request
from http import HTTPStatus

# =============================================================================
# Constants
# =============================================================================

# Resolve the real Hermes data directory even when running under a profile
# (kanban workers have HOME set to the profile's nested home).
def _resolve_hermes_home():
    """Find the actual ~/.hermes data directory, not a profile subdirectory."""
    env_home = os.environ.get("HERMES_HOME", "")
    if env_home and "/profiles/" in env_home:
        # Running under a profile — walk up to the real .hermes
        return os.path.dirname(os.path.dirname(env_home))
    candidate = os.path.expanduser("~/.hermes")
    if os.path.isdir(candidate):
        return candidate
    # Fallback
    return "/home/hermes/.hermes"

HERMES_HOME = _resolve_hermes_home()
PORT = 51763
HOST = "0.0.0.0"
SSE_INTERVAL = 5       # seconds between SSE pushes
PROD_CACHE_TTL = 30    # seconds — cache prod SSH health to avoid hammering SSH
SERVERS_CONFIG = os.path.join(os.path.dirname(os.path.abspath(__file__)), "servers.json")
DASHBOARD_DB = os.path.join(os.path.dirname(os.path.abspath(__file__)), "dashboard.db")
RETENTION_DAYS = 30

# ── SSE Multiplexer ──────────────────────────────────────────────────────
_SSE_QUEUE = queue_module.Queue(maxsize=64)
_CHANNEL_FINGERPRINTS = {}   # {event_type: md5_hex}, guarded by _fp_lock
_fp_lock = threading.Lock()

# Channel registry: (event_type, interval_seconds, tier)
# Tier 1 = burst on connect, Tier 2-3 = arrive on cadence
_CHANNEL_REGISTRY = [
    # Tier 1 — Fast, frequent
    ("gateway",          5,   1),
    ("processes",        5,   1),
    ("hermes-health",    5,   1),
    ("sessions-ledger", 15,   1),
    # Tier 2 — Medium, moderate
    ("profiles",        60,   2),
    ("sessions",        30,   2),
    ("kanban",          30,   2),
    # Tier 3 — Slow, cached
    ("prod-health",     30,   3),
    ("dokku",           60,   3),
    ("server-crons",   300,   3),
    ("servers",         60,   3),
]

# Burst signals — set on new SSE client connect, cleared after one push
_CHANNEL_BURST = {event_type: threading.Event() for event_type, _, _ in _CHANNEL_REGISTRY}

# =============================================================================
# Local retention database — instant load + 30-day history
# =============================================================================

def _init_dashboard_db():
    """Create dashboard.db tables if they don't exist."""
    db = sqlite3.connect(DASHBOARD_DB)
    db.execute("PRAGMA journal_mode=WAL")
    db.execute("PRAGMA synchronous=NORMAL")
    # Legacy snapshot table (full-snapshot retention, kept for backward compat)
    db.executescript("""
        CREATE TABLE IF NOT EXISTS snapshots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp REAL NOT NULL,
            snapshot_json TEXT NOT NULL,
            error_count INTEGER DEFAULT 0
        );
        CREATE INDEX IF NOT EXISTS idx_snapshots_ts ON snapshots(timestamp DESC);
    """)
    # Per-channel retention tables (one per event type)
    for event_type, _, _ in _CHANNEL_REGISTRY:
        table_name = f"retention_{event_type.replace('-', '_')}"
        db.execute(f"""
            CREATE TABLE IF NOT EXISTS {table_name} (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp REAL NOT NULL,
                payload TEXT NOT NULL
            )
        """)
        db.execute(f"""
            CREATE INDEX IF NOT EXISTS idx_{table_name}_ts
            ON {table_name}(timestamp)
        """)
    db.commit()
    db.close()

def _save_snapshot_to_db(snapshot_json: str, error_count: int):
    """Insert a snapshot row with automatic retention cleanup check."""
    try:
        db = sqlite3.connect(DASHBOARD_DB)
        db.execute(
            "INSERT INTO snapshots (timestamp, snapshot_json, error_count) VALUES (?, ?, ?)",
            (time.time(), snapshot_json, error_count)
        )
        db.commit()
        db.close()
    except Exception:
        pass  # non-critical — dashboard still works without DB writes

def _get_latest_snapshot():
    """Return the most recent snapshot JSON string, or None if DB is empty."""
    try:
        db = sqlite3.connect(DASHBOARD_DB)
        row = db.execute(
            "SELECT snapshot_json FROM snapshots ORDER BY timestamp DESC LIMIT 1"
        ).fetchone()
        db.close()
        return row[0] if row else None
    except Exception:
        return None

def _cleanup_old_snapshots():
    """Delete rows older than RETENTION_DAYS and VACUUM. Also trims per-channel retention."""
    try:
        cutoff = time.time() - (RETENTION_DAYS * 86400)
        db = sqlite3.connect(DASHBOARD_DB)
        deleted = db.execute("DELETE FROM snapshots WHERE timestamp < ?", (cutoff,)).rowcount
        # Per-channel retention cleanup (keep last 1000 entries per channel)
        for event_type, _, _ in _CHANNEL_REGISTRY:
            table_name = f"retention_{event_type.replace('-', '_')}"
            try:
                db.execute(f"""
                    DELETE FROM {table_name} WHERE id NOT IN (
                        SELECT id FROM {table_name} ORDER BY id DESC LIMIT 1000
                    )
                """)
            except Exception:
                pass
        db.commit()
        if deleted > 0:
            db.execute("VACUUM")
        db.close()
        print(f"  DB cleanup: removed {deleted} old snapshot rows, trimmed per-channel retention")
    except Exception:
        pass

# =============================================================================
# Thread-safe caches
# =============================================================================

_cpu_lock = threading.Lock()
_last_cpu_sample = None   # dict from /proc/stat line 1

_prod_lock = threading.Lock()
_prod_cache = None        # { data: {...}, ts: float }
_prod_errors_cache = []

# =============================================================================
# Data readers — each wrapped in try/except, returns None on failure
# =============================================================================

def read_sqlite_ro(path):
    """Open SQLite DB in read-only mode. Returns dict of {table_name: {columns, rows, row_count}} or None."""
    try:
        db = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
        db.execute("PRAGMA query_only=1")

        tables = db.execute(
            "SELECT name FROM sqlite_master "
            "WHERE type='table' AND name NOT LIKE 'sqlite_%' "
            "ORDER BY name"
        ).fetchall()

        result = {}
        for (tname,) in tables:
            try:
                cols = [c[1] for c in db.execute(f"PRAGMA table_info([{tname}])").fetchall()]
                rows = db.execute(f"SELECT * FROM [{tname}] LIMIT 500").fetchall()
                row_count = db.execute(f"SELECT count(*) FROM [{tname}]").fetchone()[0]
                result[tname] = {
                    "columns": cols,
                    "rows": [dict(zip(cols, row)) for row in rows],
                    "row_count": row_count,
                }
            except Exception:
                result[tname] = {
                    "columns": [],
                    "rows": [],
                    "row_count": 0,
                    "error": "table read failed",
                }

        db.close()
        return result
    except Exception:
        return None


def read_json(path):
    """Read and parse a JSON file. Returns parsed object or None."""
    try:
        with open(path, "r") as f:
            return json.load(f)
    except Exception:
        return None


def read_profile_yaml(path):
    """Read a Hermes profile.yaml file (hand-written subset). Returns dict."""
    try:
        with open(path, "r") as f:
            data = {}
            for line in f:
                line = line.strip()
                if ":" in line and not line.startswith("#"):
                    key, _, val = line.partition(":")
                    data[key.strip()] = val.strip().strip("\"'")
            return data
    except Exception:
        return {}


def read_config_yaml(path):
    """Extract model/provider from a config.yaml. Returns dict."""
    try:
        with open(path, "r") as f:
            content = f.read()
        result = {}
        lines = content.split("\n")
        in_model = False
        for line in lines:
            stripped = line.strip()
            if stripped == "model:":
                in_model = True
                continue
            if in_model:
                if stripped.startswith("default:"):
                    result["model"] = stripped.split(":", 1)[1].strip().strip("\"'")
                elif stripped.startswith("provider:"):
                    result["provider"] = stripped.split(":", 1)[1].strip().strip("\"'")
                elif not stripped.startswith(" "):
                    in_model = False
        return result
    except Exception:
        return {}


def get_state_db_stats(path):
    """Read aggregate stats from a state.db: sessions, messages, tokens, cost, models."""
    try:
        db = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
        db.execute("PRAGMA query_only=1")
        stats = {}

        try:
            stats["session_count"] = db.execute("SELECT count(*) FROM sessions").fetchone()[0]
        except Exception:
            stats["session_count"] = 0

        try:
            stats["message_count"] = db.execute("SELECT count(*) FROM messages").fetchone()[0]
        except Exception:
            stats["message_count"] = 0

        try:
            row = db.execute(
                "SELECT COALESCE(SUM(input_tokens),0), COALESCE(SUM(output_tokens),0), "
                "COALESCE(SUM(cache_read_tokens),0), COALESCE(SUM(cache_write_tokens),0) "
                "FROM sessions"
            ).fetchone()
            stats["total_input_tokens"] = row[0] or 0
            stats["total_output_tokens"] = row[1] or 0
            stats["total_cache_read_tokens"] = row[2] or 0
            stats["total_cache_write_tokens"] = row[3] or 0
        except Exception:
            stats["total_input_tokens"] = 0
            stats["total_output_tokens"] = 0
            stats["total_cache_read_tokens"] = 0
            stats["total_cache_write_tokens"] = 0

        try:
            row = db.execute(
                "SELECT COALESCE(SUM(estimated_cost_usd),0) FROM sessions"
            ).fetchone()
            stats["total_estimated_cost_usd"] = round(row[0] or 0, 4)
        except Exception:
            stats["total_estimated_cost_usd"] = 0.0

        try:
            stats["active_sessions"] = db.execute(
                "SELECT count(*) FROM sessions WHERE ended_at IS NULL"
            ).fetchone()[0]
        except Exception:
            stats["active_sessions"] = 0

        try:
            stats["completed_sessions"] = db.execute(
                "SELECT count(*) FROM sessions WHERE ended_at IS NOT NULL"
            ).fetchone()[0]
        except Exception:
            stats["completed_sessions"] = 0

        try:
            rows = db.execute(
                "SELECT model, count(*) as cnt FROM sessions "
                "WHERE model IS NOT NULL GROUP BY model ORDER BY cnt DESC"
            ).fetchall()
            stats["models"] = [{"model": r[0], "sessions": r[1]} for r in rows]
        except Exception:
            stats["models"] = []

        # Recent sessions (last 10) — now includes cache tokens
        try:
            rows = db.execute(
                "SELECT id, title, model, started_at, ended_at, end_reason, message_count, "
                "input_tokens, output_tokens, cache_read_tokens, cache_write_tokens, "
                "estimated_cost_usd "
                "FROM sessions ORDER BY started_at DESC LIMIT 10"
            ).fetchall()
            cols = ["id", "title", "model", "started_at", "ended_at", "end_reason", "message_count",
                    "input_tokens", "output_tokens", "cache_read_tokens", "cache_write_tokens",
                    "estimated_cost_usd"]
            stats["recent_sessions"] = [dict(zip(cols, r)) for r in rows]
        except Exception:
            stats["recent_sessions"] = []

        # 7-day daily session counts (for mini bar chart)
        try:
            now = time.time()
            seven_days_ago = now - 7 * 86400
            day_start = seven_days_ago - (seven_days_ago % 86400)  # align to midnight UTC
            daily = {}
            for i in range(7):
                day_key = time.strftime("%Y-%m-%d", time.gmtime(day_start + i * 86400))
                daily[day_key] = 0
            rows = db.execute(
                "SELECT started_at FROM sessions WHERE started_at >= ?", (seven_days_ago,)
            ).fetchall()
            for (ts,) in rows:
                day_key = time.strftime("%Y-%m-%d", time.gmtime(ts))
                if day_key in daily:
                    daily[day_key] += 1
            stats["daily_sessions_7d"] = [daily[k] for k in sorted(daily.keys())]
        except Exception:
            stats["daily_sessions_7d"] = [0] * 7

        db.close()
        return stats
    except Exception:
        return None


# =============================================================================
# Cron expression parser — human-readable descriptions
# =============================================================================

_CRON_MONTHS = ["", "Jan", "Feb", "Mar", "Apr", "May", "Jun",
                "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
_CRON_DAYS = ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"]


def _pad_time(h, m):
    """Return 'HH:MM' zero-padded."""
    return f"{int(h):02d}:{int(m):02d}"


def _parse_cron_field(field, lo, hi, names=None):
    """
    Parse a single cron field. Returns ('all' | 'list' | 'range' | 'step', data).
    data: for 'all' → None; for 'list' → list of ints; for 'range' → (start, end);
          for 'step' → (start, end, step).
    """
    field = field.strip()
    if field == "*":
        return ("all", None)

    # Step: */N or S-E/N
    if "/" in field:
        base, _, step = field.partition("/")
        step = int(step)
        if base == "*":
            return ("step", (lo, hi, step))
        if "-" in base:
            s, e = base.split("-", 1)
            return ("step", (int(s), int(e), step))
        return ("step", (int(base), hi, step))

    # Range: S-E
    if "-" in field:
        s, e = field.split("-", 1)
        return ("range", (int(s), int(e)))

    # List: a,b,c
    if "," in field:
        return ("list", [int(x) for x in field.split(",")])

    # Single value
    return ("single", int(field))


def _cron_desc_minute(m):
    """Return a phrase describing the minutes field."""
    kind, data = _parse_cron_field(m, 0, 59)
    if kind == "all":
        return ""
    if kind == "single":
        return f"at minute {data}"
    if kind == "list":
        return f"at minutes {', '.join(map(str, data))}"
    if kind == "range":
        return f"every minute from {data[0]} to {data[1]}"
    if kind == "step":
        if data[0] == 0 and data[1] == 59:
            return f"every {data[2]} minutes"
        return f"every {data[2]} minutes from {data[0]} to {data[1]}"
    return ""


def _cron_desc_hour(h):
    """Return a phrase describing the hour field."""
    kind, data = _parse_cron_field(h, 0, 23)
    if kind == "all":
        return ""
    if kind == "single":
        return f"at {_pad_time(data, 0)}"
    if kind == "list":
        times = [_pad_time(x, 0) for x in data]
        return "at " + ", ".join(times)
    if kind == "range":
        return f"every hour from {_pad_time(data[0], 0)} to {_pad_time(data[1], 0)}"
    if kind == "step":
        if data[0] == 0 and data[1] == 23:
            return f"every {data[2]} hours"
        return f"every {data[2]} hours from {data[0]} to {data[1]}"
    return ""


def _cron_desc_dom(dom):
    """Return a phrase describing the day-of-month field."""
    kind, data = _parse_cron_field(dom, 1, 31)
    if kind == "all":
        return ""
    if kind == "single":
        return f"on day {data}"
    if kind == "list":
        return "on days " + ", ".join(map(str, data))
    if kind == "range":
        return f"on days {data[0]}–{data[1]}"
    if kind == "step":
        return f"every {data[2]} days starting day {data[0]}"
    return ""


def _cron_desc_month(mon):
    """Return a phrase describing the month field."""
    kind, data = _parse_cron_field(mon, 1, 12)
    if kind == "all":
        return ""
    if kind == "single":
        return f"in {_CRON_MONTHS[data]}"
    if kind == "list":
        names = [_CRON_MONTHS[x] for x in data]
        return "in " + ", ".join(names)
    if kind == "range":
        return f"from {_CRON_MONTHS[data[0]]} to {_CRON_MONTHS[data[1]]}"
    if kind == "step":
        return f"every {data[2]} months from {_CRON_MONTHS[data[0]]}"
    return ""


def _cron_desc_dow(dow):
    """Return a phrase describing the day-of-week field."""
    kind, data = _parse_cron_field(dow, 0, 7)
    if kind == "all":
        return ""
    if kind == "single":
        idx = data if data <= 6 else 0
        return f"on {_CRON_DAYS[idx]}"
    if kind == "list":
        names = [_CRON_DAYS[x if x <= 6 else 0] for x in data]
        return "on " + ", ".join(names)
    if kind == "range":
        s = data[0] if data[0] <= 6 else 0
        e = data[1] if data[1] <= 6 else 6
        return f"{_CRON_DAYS[s]} through {_CRON_DAYS[e]}"
    if kind == "step":
        return f"every {data[2]} days of week from {_CRON_DAYS[data[0]]}"
    return ""


def cron_to_human(expr):
    """
    Convert a 5-field cron expression to a human-readable English description.

    Returns a short string like 'Every day at 03:00', 'Every 30 minutes', etc.
    """
    try:
        parts = expr.strip().split()
        if len(parts) != 5:
            return expr
        minute, hour, dom, month, dow = parts
    except Exception:
        return expr

    # Detect "every N minutes" (step on minutes, * everything else)
    mkind, mdata = _parse_cron_field(minute, 0, 59)
    if mkind == "step" and hour == "*" and dom == "*" and month == "*" and dow == "*":
        return f"Every {mdata[2]} minutes"

    # Detect "every minute" (* * * * *)
    if minute == "*" and hour == "*" and dom == "*" and month == "*" and dow == "*":
        return "Every minute"

    # Hour-level patterns
    hkind, hdata = _parse_cron_field(hour, 0, 23)

    # Every hour at minute N
    if mkind == "single" and hour == "*" and dom == "*" and month == "*" and dow == "*":
        return f"Every hour at minute {mdata}"

    # Every N hours
    if mkind == "single" and hkind == "step" and dom == "*" and month == "*" and dow == "*":
        if hdata[0] == 0 and hdata[1] == 23:
            if mdata != 0:
                return f"Every {hdata[2]} hours at minute {mdata}"
            return f"Every {hdata[2]} hours"
        return f"Every {hdata[2]} hours from {hdata[0]}:00 to {hdata[1]}:00 at minute {mdata}"

    # Every day at HH:MM
    if hour != "*" and dom == "*" and month == "*" and dow == "*":
        hkind2, hdata2 = _parse_cron_field(hour, 0, 23)
        if hkind2 == "single" and (mkind == "single" or mkind == "all"):
            m_val = mdata if mkind == "single" else 0
            return f"Every day at {_pad_time(hdata2, m_val)}"
        if hkind2 == "list" and mkind == "single":
            times = [f"{_pad_time(x, mdata)}" for x in hdata2]
            return "Every day at " + ", ".join(times)
        if hkind2 == "step" and hdata2[0] == 0 and hdata2[1] == 23:
            if mkind == "single" and mdata != 0:
                return f"Every {hdata2[2]} hours at minute {mdata}"
            return f"Every {hdata2[2]} hours"

    # Day-of-week patterns — "Every Monday at HH:MM"
    if dow != "*" and dom == "*":
        hkind3, hdata3 = _parse_cron_field(hour, 0, 23)
        if hkind3 == "single" and (mkind == "single" or mkind == "all"):
            m_val = mdata if mkind == "single" else 0
            time_str = f" at {_pad_time(hdata3, m_val)}"
            dkind, ddata = _parse_cron_field(dow, 0, 7)
            if dkind == "single":
                idx = ddata if ddata <= 6 else 0
                return f"Every {_CRON_DAYS[idx]}{time_str}"
            if dkind == "list":
                names = [_CRON_DAYS[x if x <= 6 else 0] for x in ddata]
                return f"Every {', '.join(names)}{time_str}"
        return _cron_desc_dow(dow) + " " + _cron_desc_hour(hour) + " " + _cron_desc_minute(minute)

    # Day-of-month patterns — "1st of every month at HH:MM"
    if dom != "*":
        hkind4, hdata4 = _parse_cron_field(hour, 0, 23)
        if hkind4 == "single" and (mkind == "single" or mkind == "all"):
            m_val = mdata if mkind == "single" else 0
            time_str = f" at {_pad_time(hdata4, m_val)}"
            if dom.isdigit():
                d = int(dom)
                suffix = "th" if 11 <= d <= 13 else {1: "st", 2: "nd", 3: "rd"}.get(d % 10, "th")
                return f"{d}{suffix} of every month{time_str}"
            return f"On day {dom} of every month{time_str}"

    # Fallback: stitch field descriptions
    pieces = []
    for fn in [_cron_desc_minute, _cron_desc_hour, _cron_desc_dom, _cron_desc_month, _cron_desc_dow]:
        p = fn
        if p == _cron_desc_minute:
            desc = _cron_desc_minute(minute)
        elif p == _cron_desc_hour:
            desc = _cron_desc_hour(hour)
        elif p == _cron_desc_dom:
            desc = _cron_desc_dom(dom)
        elif p == _cron_desc_month:
            desc = _cron_desc_month(month)
        else:
            desc = _cron_desc_dow(dow)
        if desc:
            pieces.append(desc)

    if pieces:
        return " ".join(pieces).capitalize()
    return expr


# =============================================================================
# Cron next-run calculator
# =============================================================================

import calendar as _calendar

def _next_cron_field(value, kind, data, lo, hi):
    """Find the next valid value >= `value` for a single cron field. Returns (next_val, wrapped)."""
    if kind == "all":
        return value, False
    if kind == "single":
        if value <= data:
            return data, False
        else:
            return lo, True   # wrap: no valid value remaining in this range
    if kind == "list":
        for v in data:
            if v >= value:
                return v, False
        return data[0], True  # wrap to first in list
    if kind == "range":
        if value < data[0]:
            return data[0], False
        if value <= data[1]:
            return value, False
        return data[0], True  # wrap
    if kind == "step":
        start, end, step = data
        if value < start:
            return start, False
        if value <= end:
            # Find first multiple of step >= value, starting from start
            dist = value - start
            next_val = start + ((dist + step - 1) // step) * step
            if next_val <= end:
                return next_val, False
        return start, True  # wrap
    return value, False


def cron_next_run(expr, from_ts=None):
    """
    Calculate the next time a 5-field cron expression will fire, as a Unix timestamp.
    Uses a simple minute-by-minute search (max 2 years forward, ~1M iterations).
    Returns the next timestamp or None if no match within 2 years.
    """
    import datetime as _dt

    try:
        parts = expr.strip().split()
        if len(parts) != 5:
            return None
        m_expr, h_expr, dom_expr, mon_expr, dow_expr = parts
    except Exception:
        return None

    # Pre-parse all fields
    m_info = (m_expr, _parse_cron_field(m_expr, 0, 59))
    h_info = (h_expr, _parse_cron_field(h_expr, 0, 23))
    dom_info = (dom_expr, _parse_cron_field(dom_expr, 1, 31))
    mon_info = (mon_expr, _parse_cron_field(mon_expr, 1, 12))
    dow_info = (dow_expr, _parse_cron_field(dow_expr, 0, 7))

    if from_ts is None:
        now = _dt.datetime.utcnow()
    else:
        now = _dt.datetime.utcfromtimestamp(from_ts)

    # Start from current minute
    year, month, day, hour, minute = now.year, now.month, now.day, now.hour, now.minute
    # Increment by 1 minute so "now" doesn't match if it just fired
    minute += 1

    max_iter = 2 * 366 * 24 * 60  # ~2 years in minutes
    for _ in range(max_iter):
        if minute >= 60:
            minute = 0
            hour += 1
        if hour >= 24:
            hour = 0
            day += 1
        days_in_month = _calendar.monthrange(year, month)[1]
        if day > days_in_month:
            day = 1
            month += 1
        if month > 12:
            month = 1
            year += 1

        # Check each field
        dow = _calendar.weekday(year, month, day)  # 0=Mon, need 0=Sun for cron
        cron_dow = (dow + 1) % 7

        # Minute match
        m_kind, m_data = m_info[1]
        if m_kind == "single" and minute != m_data:
            minute += 1; continue
        elif m_kind == "list" and minute not in m_data:
            minute += 1; continue
        elif m_kind == "range" and not (m_data[0] <= minute <= m_data[1]):
            minute += 1; continue
        elif m_kind == "step":
            start, end, step = m_data
            if start <= minute <= end and (minute - start) % step == 0:
                pass
            else:
                minute += 1; continue

        # Hour match
        h_kind, h_data = h_info[1]
        if h_kind == "single" and hour != h_data:
            minute = 0; hour += 1; continue
        elif h_kind == "list" and hour not in h_data:
            minute = 0; hour += 1; continue
        elif h_kind == "range" and not (h_data[0] <= hour <= h_data[1]):
            minute = 0; hour += 1; continue
        elif h_kind == "step":
            start, end, step = h_data
            if not (start <= hour <= end and (hour - start) % step == 0):
                minute = 0; hour += 1; continue

        # Day-of-month and day-of-week: OR relationship in cron
        dom_kind, dom_data = dom_info[1]
        dow_kind, dow_data = dow_info[1]

        dom_ok = True
        dow_ok = True

        # If either field is non-*, both must match (OR).
        # If both are non-*, either match is sufficient.
        # If both are *, both are ok.

        if dom_expr != "*":
            dom_ok = False
            if dom_kind == "single" and day == dom_data:
                dom_ok = True
            elif dom_kind == "list" and day in dom_data:
                dom_ok = True
            elif dom_kind == "range" and dom_data[0] <= day <= dom_data[1]:
                dom_ok = True
            elif dom_kind == "step":
                start, end, step = dom_data
                if start <= day <= end and (day - start) % step == 0:
                    dom_ok = True

        if dow_expr != "*":
            dow_ok = False
            if dow_kind == "single":
                target = dow_data if dow_data <= 6 else 0
                if cron_dow == target:
                    dow_ok = True
            elif dow_kind == "list":
                targets = [x if x <= 6 else 0 for x in dow_data]
                if cron_dow in targets:
                    dow_ok = True
            elif dow_kind == "range":
                s = dow_data[0] if dow_data[0] <= 6 else 0
                e = dow_data[1] if dow_data[1] <= 6 else 6
                if s <= cron_dow <= e:
                    dow_ok = True
            elif dow_kind == "step":
                start = dow_data[0] if dow_data[0] <= 6 else 0
                if (cron_dow - start) % dow_data[2] == 0:
                    dow_ok = True

        # Cron OR semantics: if both fields are specified (non-*), either matching is enough.
        # If only one is specified, that one must match.
        if dom_expr != "*" and dow_expr != "*":
            if not (dom_ok or dow_ok):
                minute = 0; hour = 0; day += 1; continue
        elif dom_expr != "*" and not dom_ok:
            minute = 0; hour = 0; day += 1; continue
        elif dow_expr != "*" and not dow_ok:
            minute = 0; hour = 0; day += 1; continue

        # Month match
        mon_kind, mon_data = mon_info[1]
        if mon_kind == "single" and month != mon_data:
            minute = 0; hour = 0; day = 1; month += 1; continue
        elif mon_kind == "list" and month not in mon_data:
            minute = 0; hour = 0; day = 1; month += 1; continue
        elif mon_kind == "range" and not (mon_data[0] <= month <= mon_data[1]):
            minute = 0; hour = 0; day = 1; month += 1; continue
        elif mon_kind == "step":
            start, end, step = mon_data
            if not (start <= month <= end and (month - start) % step == 0):
                minute = 0; hour = 0; day = 1; month += 1; continue

        # All checks passed — found next run
        ts = _dt.datetime(year, month, day, hour, minute, 0).timestamp()
        return ts

    return None


def _relative_time(ts):
    """Convert a future Unix timestamp to a relative string like 'in 3h 12m'."""
    now = time.time()
    diff = int(ts - now)
    if diff < 0:
        return "now"
    if diff < 60:
        return "in <1m"
    if diff < 3600:
        return f"in {diff // 60}m"
    hours = diff // 3600
    minutes = (diff % 3600) // 60
    if hours < 48:
        if minutes == 0:
            return f"in {hours}h"
        return f"in {hours}h {minutes}m"
    days = hours // 24
    hours = hours % 24
    if hours == 0:
        return f"in {days}d"
    return f"in {days}d {hours}h"


# =============================================================================
# Cron Data Source — unified Hermes + system crontabs
# =============================================================================

def _parse_system_cron_line(line, source_label, source_path):
    """
    Parse one line from a system crontab file.
    Lines starting with # or blank or variable assignments are skipped.
    Returns a job dict or None.
    """
    line = line.strip()
    if not line or line.startswith("#"):
        return None
    # Variable assignments
    if "=" in line and not any(line.startswith(c) for c in "0123456789*@"):
        return None

    parts = line.split()
    if len(parts) < 6:
        return None

    # Try to parse: minute hour dom month dow user command
    # But some crontabs (root's) may not have a user field.
    # /etc/crontab and /etc/cron.d have the user field.
    # /var/spool/cron/crontabs/root does NOT have a user field.

    # Detect: if parts[5] looks like a cron field (digit/*), this is a no-user crontab
    p5 = parts[5]
    user = None
    cmd_start = 5

    if not (p5.isdigit() or p5 == "*" or "/" in p5 or "-" in p5 or "," in p5):
        # Has user field
        user = parts[5]
        cmd_start = 6

    expr = " ".join(parts[0:5])
    command = " ".join(parts[cmd_start:])

    valid_cron = True
    for f in parts[0:5]:
        if not any(c in "0123456789*-,/" for c in f):
            valid_cron = False
            break

    if not valid_cron:
        return None

    return {
        "id": None,
        "name": command[:80] + ("..." if len(command) > 80 else ""),
        "command": command,
        "schedule_display": expr,
        "schedule_desc": cron_to_human(expr),
        "next_run_at": None,
        "next_run_relative": None,
        "enabled": True,
        "source": "system",
        "source_path": source_path,
        "user": user,
    }


def _read_system_crontab(path, source_label, crons_out):
    """Read a single crontab file and append parsed entries to crons_out."""
    try:
        with open(path, "r") as f:
            for line in f:
                entry = _parse_system_cron_line(line, source_label, path)
                if entry:
                    # Compute next run
                    ts = cron_next_run(entry["schedule_display"])
                    if ts is not None:
                        entry["next_run_at"] = time.strftime(
                            "%Y-%m-%dT%H:%M:%SZ", time.gmtime(ts)
                        )
                        entry["next_run_relative"] = _relative_time(ts)
                    crons_out.append(entry)
    except Exception:
        pass  # File may not exist or be unreadable


def build_crons(errors_out):
    """
    Build the unified cron job list: Hermes jobs + system crontab jobs.
    Each entry has: id, name, command, schedule_display, schedule_desc,
    next_run_at, next_run_relative, enabled, source ('hermes'|'system'), source_path.
    Mutates errors_out.
    """
    crons = []

    # --- Hermes cron jobs ---
    cron_json = read_json(os.path.join(HERMES_HOME, "cron", "jobs.json"))
    hermes_jobs = []
    if cron_json is not None and "jobs" in cron_json:
        hermes_jobs = cron_json["jobs"]

    for job in hermes_jobs:
        expr = job.get("schedule_display", "")
        if not expr and "schedule" in job:
            expr = job["schedule"].get("expr", "")
        name = job.get("name", "unnamed")
        command = name
        if job.get("script"):
            command = job["script"]
        elif job.get("prompt"):
            command = job["prompt"][:80]

        entry = {
            "id": job.get("id"),
            "name": name,
            "command": command,
            "schedule_display": expr,
            "schedule_desc": cron_to_human(expr) if expr else "",
            "next_run_at": job.get("next_run_at"),
            "next_run_relative": None,
            "enabled": job.get("enabled", True),
            "source": "hermes",
            "source_path": os.path.join(HERMES_HOME, "cron", "jobs.json"),
            "user": None,
        }

        # Compute relative next run from the stored timestamp
        if entry["next_run_at"]:
            try:
                # Parse ISO timestamp
                import datetime as _dt
                ts_str = entry["next_run_at"]
                if ts_str.endswith("Z"):
                    ts_str = ts_str[:-1] + "+00:00"
                dt = _dt.datetime.fromisoformat(ts_str)
                ts = dt.timestamp()
                entry["next_run_relative"] = _relative_time(ts)
            except Exception:
                pass

        crons.append(entry)

    # --- System crontabs ---
    # /var/spool/cron/crontabs/root
    _read_system_crontab("/var/spool/cron/crontabs/root", "root crontab", crons)

    # /etc/crontab
    _read_system_crontab("/etc/crontab", "system crontab", crons)

    # /etc/cron.d/*
    try:
        cron_d_dir = "/etc/cron.d"
        for fname in sorted(os.listdir(cron_d_dir)):
            fpath = os.path.join(cron_d_dir, fname)
            if os.path.isfile(fpath) and not fname.startswith("."):
                _read_system_crontab(fpath, f"cron.d/{fname}", crons)
    except Exception as e:
        errors_out.append(f"reading /etc/cron.d: {e}")

    return crons


# =============================================================================
# VPS Health Collectors
# =============================================================================

def _parse_proc_stat(line):
    """Parse a /proc/stat cpu line into a dict. First token is 'cpu' (label), rest are numbers."""
    parts = line.strip().split()
    # parts[0] = 'cpu', parts[1:] = user, nice, system, idle, iowait, irq, softirq, steal, guest, guest_nice
    fields = ["user", "nice", "system", "idle", "iowait", "irq", "softirq", "steal", "guest", "guest_nice"]
    values = parts[1:]
    return {fields[i]: int(values[i]) for i in range(min(len(fields), len(values)))}


def _cpu_total_and_idle(sample):
    """Return (total, idle) jiffies from a /proc/stat cpu sample dict."""
    idle = sample.get("idle", 0) + sample.get("iowait", 0)
    total = sum(v for k, v in sample.items() if k != "cpu")
    return total, idle


def get_hermes_health(errors_out):
    """Collect hermes VPS health: CPU (two-sample diff), RAM, disk. Mutates errors_out."""
    result = {"cpu_pct": None, "mem": None, "disk": None}

    # --- CPU (two-sample diff, thread-safe) ---
    global _last_cpu_sample
    try:
        with open("/proc/stat", "r") as f:
            current = _parse_proc_stat(f.readline())
        with _cpu_lock:
            prev = _last_cpu_sample
            _last_cpu_sample = current
        if prev is not None:
            prev_total, prev_idle = _cpu_total_and_idle(prev)
            curr_total, curr_idle = _cpu_total_and_idle(current)
            tdiff = curr_total - prev_total
            if tdiff > 0:
                result["cpu_pct"] = round(100.0 * (1.0 - (curr_idle - prev_idle) / tdiff), 1)
            else:
                result["cpu_pct"] = 0.0
    except Exception as e:
        errors_out.append(f"hermes cpu: {e}")

    # --- RAM ---
    try:
        mem = {}
        with open("/proc/meminfo", "r") as f:
            for line in f:
                if ":" in line:
                    key, _, val = line.partition(":")
                    parts = val.strip().split()
                    if parts:
                        mem[key.strip()] = int(parts[0])
        total = mem.get("MemTotal", 0)
        available = mem.get("MemAvailable", mem.get("MemFree", 0))
        used = total - available
        pct = round(100.0 * used / total, 1) if total > 0 else 0.0
        result["mem"] = {
            "mem_total_mb": round(total / 1024, 1),
            "mem_used_mb": round(used / 1024, 1),
            "mem_available_mb": round(available / 1024, 1),
            "mem_pct": pct,
        }
    except Exception as e:
        errors_out.append(f"hermes mem: {e}")

    # --- Disk ---
    try:
        st = os.statvfs("/")
        total = st.f_blocks * st.f_frsize
        free = st.f_bavail * st.f_frsize
        used = total - free
        pct = round(100.0 * used / total, 1) if total > 0 else 0.0
        result["disk"] = {
            "disk_total_gb": round(total / (1024 ** 3), 1),
            "disk_used_gb": round(used / (1024 ** 3), 1),
            "disk_free_gb": round(free / (1024 ** 3), 1),
            "disk_pct": pct,
        }
    except Exception as e:
        errors_out.append(f"hermes disk: {e}")

    # --- Uptime ---
    try:
        with open("/proc/uptime", "r") as f:
            result["uptime"] = float(f.readline().split()[0])
    except Exception as e:
        errors_out.append(f"hermes uptime: {e}")

    return result


def _collect_prod_health_raw():
    """Execute one SSH call to prod gathering cpu×2, meminfo, and df. Returns (data, errors)."""
    result = {"cpu_pct": None, "mem": None, "disk": None, "ssh_ok": False}
    errors = []

    # Single SSH call: read /proc/stat twice (with remote sleep) + meminfo + df
    cmd = (
        "head -1 /proc/stat; sleep 0.5; head -1 /proc/stat; "
        "cat /proc/meminfo; df -B1 / | tail -1"
    )
    try:
        proc = subprocess.run(
            ["ssh", "-o", "ConnectTimeout=5", "-o", "StrictHostKeyChecking=no", "prod", cmd],
            capture_output=True, text=True, timeout=12,
        )
        if proc.returncode != 0:
            errors.append(f"prod ssh: exit code {proc.returncode}")
            return result, errors

        result["ssh_ok"] = True
        lines = proc.stdout.strip().split("\n")

        # First two lines are /proc/stat samples
        if len(lines) >= 2:
            try:
                s1 = _parse_proc_stat(lines[0])
                s2 = _parse_proc_stat(lines[1])
                t1, i1 = _cpu_total_and_idle(s1)
                t2, i2 = _cpu_total_and_idle(s2)
                if t2 > t1:
                    result["cpu_pct"] = round(100.0 * (1.0 - (i2 - i1) / (t2 - t1)), 1)
            except Exception as e:
                errors.append(f"prod cpu parse: {e}")

        # Parse /proc/meminfo lines between cpu samples and df
        mem = {}
        in_mem = False
        for line in lines[2:]:
            if line.startswith("MemTotal:"):
                in_mem = True
            if in_mem and ":" in line:
                key, _, val = line.partition(":")
                parts = val.strip().split()
                if parts and parts[0].isdigit():
                    mem[key.strip()] = int(parts[0])
            if line.startswith("Filesystem") or (in_mem and line.startswith("/")):
                in_mem = False

        if mem:
            total = mem.get("MemTotal", 0)
            available = mem.get("MemAvailable", mem.get("MemFree", 0))
            used = total - available
            pct = round(100.0 * used / total, 1) if total > 0 else 0.0
            result["mem"] = {
                "mem_total_mb": round(total / 1024, 1),
                "mem_used_mb": round(used / 1024, 1),
                "mem_available_mb": round(available / 1024, 1),
                "mem_pct": pct,
            }
        else:
            errors.append("prod mem: parse failure")

        # Last line is df output
        df_line = lines[-1].strip()
        if df_line:
            parts = df_line.split()
            if len(parts) >= 5:
                try:
                    total_b = int(parts[1])
                    used_b = int(parts[2])
                    avail_b = int(parts[3])
                    pct_str = parts[4].rstrip("%")
                    result["disk"] = {
                        "disk_total_gb": round(total_b / (1024 ** 3), 1),
                        "disk_used_gb": round(used_b / (1024 ** 3), 1),
                        "disk_free_gb": round(avail_b / (1024 ** 3), 1),
                        "disk_pct": float(pct_str) if pct_str.replace(".", "").replace("-", "").isdigit() else 0.0,
                    }
                except (ValueError, IndexError):
                    errors.append("prod disk: df parse failure")
        else:
            errors.append("prod disk: no df output")

    except subprocess.TimeoutExpired:
        errors.append("prod ssh: timeout (>12s)")
    except Exception as e:
        errors.append(f"prod ssh: {e}")

    return result, errors


def get_prod_health(errors_out):
    """
    Collect prod VPS health. Cached for PROD_CACHE_TTL seconds.
    Mutates errors_out with any cache-fresh errors.
    """
    global _prod_cache, _prod_errors_cache
    now = time.time()

    with _prod_lock:
        if _prod_cache and (now - _prod_cache["ts"]) < PROD_CACHE_TTL:
            errors_out.extend(_prod_errors_cache)
            return dict(_prod_cache["data"])  # shallow copy

    # Cache miss — do the SSH call
    data, errs = _collect_prod_health_raw()
    with _prod_lock:
        _prod_cache = {"data": data, "ts": now}
        _prod_errors_cache = list(errs)

    errors_out.extend(errs)
    return dict(data)


# =============================================================================
# Profile builder
# =============================================================================

def build_profiles(errors_out):
    """Build profile list: default + named profiles under ~/.hermes/profiles/. Mutates errors_out."""
    profiles = []

    # --- Default profile (root ~/.hermes/) ---
    pdata = {
        "name": "default",
        "description": "Primary Hermes agent profile",
        "model": "",
        "provider": "",
        "skills": {},
        "state_db_stats": None,
        "has_state_db": False,
    }

    # Root skills
    root_skills = read_json(os.path.join(HERMES_HOME, "skills", ".usage.json"))
    if root_skills is not None:
        pdata["skills"] = root_skills

    # Root state.db
    root_state = os.path.join(HERMES_HOME, "state.db")
    if os.path.exists(root_state):
        pdata["has_state_db"] = True
        stats = get_state_db_stats(root_state)
        if stats is not None:
            pdata["state_db_stats"] = stats
        else:
            errors_out.append("default state.db: stats query failed")

    profiles.append(pdata)

    # --- Named profiles ---
    profiles_dir = os.path.join(HERMES_HOME, "profiles")
    try:
        names = sorted(os.listdir(profiles_dir))
    except Exception as e:
        errors_out.append(f"profiles directory not readable: {e}")
        names = []

    for name in names:
        prof_dir = os.path.join(profiles_dir, name)
        if not os.path.isdir(prof_dir):
            continue

        pdata = {
            "name": name,
            "description": "",
            "description_auto": "false",
            "model": "",
            "provider": "",
            "skills": {},
            "state_db_stats": None,
            "has_state_db": False,
        }

        # profile.yaml
        try:
            pyaml_path = os.path.join(prof_dir, "profile.yaml")
            if os.path.isfile(pyaml_path):
                pyaml = read_profile_yaml(pyaml_path)
                pdata["description"] = pyaml.get("description", "")
                pdata["description_auto"] = pyaml.get("description_auto", "false")
        except Exception:
            pass

        # config.yaml → model/provider
        try:
            cfg_path = os.path.join(prof_dir, "config.yaml")
            if os.path.isfile(cfg_path):
                cfg = read_config_yaml(cfg_path)
                pdata["model"] = cfg.get("model", "")
                pdata["provider"] = cfg.get("provider", "")
        except Exception:
            pass

        # skills/.usage.json
        try:
            skills_path = os.path.join(prof_dir, "skills", ".usage.json")
            if os.path.isfile(skills_path):
                skills = read_json(skills_path)
                if skills is not None:
                    pdata["skills"] = skills
        except Exception:
            pass

        # state.db
        try:
            state_path = os.path.join(prof_dir, "state.db")
            if os.path.isfile(state_path):
                pdata["has_state_db"] = True
                stats = get_state_db_stats(state_path)
                if stats is not None:
                    pdata["state_db_stats"] = stats
                else:
                    errors_out.append(f"{name} state.db: stats query failed")
        except Exception:
            pass

        profiles.append(pdata)

    return profiles


# =============================================================================
# Content API helpers
# =============================================================================

CONTENT_DIR = os.path.join(HERMES_HOME, "content")


def _validate_content_path(rel_path):
    """Resolve a relative path against CONTENT_DIR. Reject traversal attempts.
    Returns (absolute_path, error_string). One will be None."""
    if not rel_path or ".." in rel_path or rel_path.startswith("/"):
        return None, "invalid path"
    abs_path = os.path.normpath(os.path.join(CONTENT_DIR, rel_path))
    if not abs_path.startswith(os.path.normpath(CONTENT_DIR) + os.sep) and abs_path != os.path.normpath(CONTENT_DIR):
        return None, "path traversal rejected"
    if not abs_path.endswith(".md"):
        return None, "not a markdown file"
    if not os.path.isfile(abs_path):
        return None, "file not found"
    return abs_path, None


def list_content():
    """Walk ~/.hermes/content/ and return list of .md file metadata.
    Returns list of {agent, filename, rel_path, title, modified_at, size}."""
    docs = []
    if not os.path.isdir(CONTENT_DIR):
        return docs

    try:
        for profile in sorted(os.listdir(CONTENT_DIR)):
            prof_dir = os.path.join(CONTENT_DIR, profile)
            if not os.path.isdir(prof_dir):
                continue
            try:
                for fname in sorted(os.listdir(prof_dir)):
                    if not fname.endswith(".md"):
                        continue
                    fpath = os.path.join(prof_dir, fname)
                    rel = os.path.join(profile, fname)
                    try:
                        st = os.stat(fpath)
                        title = fname
                        # Extract first H1 as title
                        try:
                            with open(fpath, "r") as f:
                                for line in f:
                                    stripped = line.strip()
                                    if stripped.startswith("# ") and not stripped.startswith("## "):
                                        title = stripped[2:].strip()
                                        break
                        except Exception:
                            pass
                        docs.append({
                            "agent": profile,
                            "filename": fname,
                            "rel_path": rel,
                            "abs_path": fpath,
                            "title": title,
                            "modified_at": st.st_mtime,
                            "size": st.st_size,
                        })
                    except OSError:
                        pass
            except OSError:
                pass
    except OSError:
        pass

    return docs


def read_content(rel_path):
    """Read raw markdown content. Returns (content, abs_path, error)."""
    abs_path, err = _validate_content_path(rel_path)
    if err:
        return None, None, err
    try:
        with open(abs_path, "r") as f:
            return f.read(), abs_path, None
    except Exception as e:
        return None, None, f"read error: {e}"


def save_content(rel_path, content):
    """Write markdown content back. Returns (True, None) or (False, error)."""
    abs_path, err = _validate_content_path(rel_path)
    if err:
        return False, err
    try:
        with open(abs_path, "w") as f:
            f.write(content)
        return True, None
    except Exception as e:
        return False, f"write error: {e}"


# =============================================================================
# Kanban reader — clean grouped structure for the frontend
# =============================================================================

# Status → column mapping
_STATUS_TO_COLUMN = {
    "triage":  "triage",
    "todo":    "todo",
    "ready":   "ready",
    "running": "running",
    "blocked": "blocked",
    "done":    "done",
    "archived":"archived",
}

_KANBAN_COLUMNS = ["triage", "todo", "ready", "running", "blocked", "done", "archived"]

_PRIORITY_NAMES = {0: "low", 1: "medium", 2: "high", 3: "critical"}


def _read_kanban_tasks(db_path):
    """Read tasks from a kanban.db. Returns list of task dicts or None on failure."""
    try:
        db = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        db.execute("PRAGMA query_only=1")
        rows = db.execute(
            "SELECT id, title, body, assignee, status, priority, "
            "created_at, started_at, completed_at, "
            "workspace_path, skills, result, created_by, model_override "
            "FROM tasks ORDER BY priority DESC, created_at ASC"
        ).fetchall()
        db.close()

        tasks = []
        for r in rows:
            tid, title, body, assignee, status, priority, \
                created_at, started_at, completed_at, \
                workspace_path, skills, result, created_by, model_override = r
            tasks.append({
                "id": tid,
                "title": title or "",
                "body": body or "",
                "assignee": assignee or "",
                "status": status or "todo",
                "priority": priority or 0,
                "priority_name": _PRIORITY_NAMES.get(priority or 0, "low"),
                "created_at": created_at,
                "started_at": started_at,
                "completed_at": completed_at,
                "workspace_path": workspace_path or "",
                "skills": skills or "",
                "result": result or "",
                "created_by": created_by or "",
                "model_override": model_override or "",
                "labels": [],
            })
        return tasks
    except Exception:
        return None


def read_kanban_boards(errors_out):
    """Read all kanban boards (root + per-board) and group tasks by status column.
    Returns {"boards": {name: {name, columns: {backlog,in_progress,done}, task_count}}, "default_board": str}.
    Mutates errors_out on failures.
    """
    boards = {}
    board_names = []

    # Board-specific kanban DBs first (these have the real data)
    boards_dir = os.path.join(HERMES_HOME, "kanban", "boards")
    try:
        for board_name in sorted(os.listdir(boards_dir)):
            board_db = os.path.join(boards_dir, board_name, "kanban.db")
            if os.path.isfile(board_db):
                tasks = _read_kanban_tasks(board_db)
                if tasks is not None:
                    columns = {c: [] for c in _KANBAN_COLUMNS}
                    for t in tasks:
                        col = _STATUS_TO_COLUMN.get(t["status"], "backlog")
                        columns[col].append(t)
                    boards[board_name] = {
                        "name": board_name,
                        "columns": columns,
                        "task_count": len(tasks),
                    }
                    board_names.append(board_name)
                else:
                    errors_out.append(f"kanban board '{board_name}': read failed")
    except Exception as e:
        errors_out.append(f"kanban boards directory: {e}")

    # Root kanban.db (usually empty, but include if it has tasks)
    root_db = os.path.join(HERMES_HOME, "kanban.db")
    if os.path.isfile(root_db):
        tasks = _read_kanban_tasks(root_db)
        if tasks is not None and len(tasks) > 0:
            columns = {c: [] for c in _KANBAN_COLUMNS}
            for t in tasks:
                col = _STATUS_TO_COLUMN.get(t["status"], "backlog")
                columns[col].append(t)
            boards["default"] = {
                "name": "default",
                "columns": columns,
                "task_count": len(tasks),
            }
            board_names.append("default")

    # Default board — first one with tasks, or first alphabetically
    first_with_tasks = None
    for name in board_names:
        if boards.get(name, {}).get("task_count", 0) > 0:
            first_with_tasks = name
            break
    default_board = first_with_tasks or (board_names[0] if board_names else "default")

    return {
        "boards": boards,
        "default_board": default_board,
    }


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


# =============================================================================
# Servers — dynamic server discovery + per-server data
# =============================================================================

def _read_servers_config():
    """Load servers.json. Returns list of server dicts or empty list on failure."""
    try:
        with open(SERVERS_CONFIG) as f:
            cfg = json.load(f)
        return sorted(cfg.get("servers", []), key=lambda s: s.get("sort_order", 99))
    except Exception:
        return []

def _ssh(host, cmd, timeout=10):
    """Run a command over SSH. Returns (stdout, exit_code) or (None, -1) on failure."""
    try:
        p = subprocess.run(
            ["ssh", "-o", "ConnectTimeout=5", "-o", "BatchMode=yes", host, cmd],
            capture_output=True, text=True, timeout=timeout
        )
        return p.stdout.strip(), p.returncode
    except Exception:
        return None, -1

def _get_dokku_data(host):
    """Collect Dokku app list and container status from a remote host.
    Returns dict with apps, containers, and per-app stats, or None if not a Dokku host."""
    if host == "localhost":
        return None
    result = {"apps": [], "containers": [], "container_stats": {}, "errors": []}

    # Dokku apps — try command, fall back gracefully
    out, rc = _ssh(host, "dokku apps:list 2>/dev/null || dokku ls 2>/dev/null")
    if rc == 0 and out:
        for line in out.split("\n"):
            line = line.strip()
            if line and line != "=====> My Apps" and not line.startswith("---"):
                result["apps"].append(line)
    elif out:
        for line in out.split("\n"):
            line = line.strip()
            if line and line != "=====> My Apps" and not line.startswith("---"):
                result["apps"].append(line)

    # Docker containers (PS format: short ID, image, status, names)
    out, rc = _ssh(host, "docker ps --format '{{.ID}}\\t{{.Image}}\\t{{.Status}}\\t{{.Names}}' 2>/dev/null")
    if rc == 0 and out:
        for line in out.split("\n"):
            parts = line.split("\t")
            if len(parts) >= 4:
                result["containers"].append({
                    "id": parts[0],
                    "image": parts[1],
                    "status": parts[2],
                    "name": parts[3],
                })

    # Docker stats — per-container CPU/MEM (one-shot, no stream)
    out, rc = _ssh(host, "docker stats --no-stream --format '{{.Name}}\\t{{.CPUPerc}}\\t{{.MemPerc}}\\t{{.MemUsage}}' 2>/dev/null", timeout=8)
    if rc == 0 and out:
        for line in out.split("\n"):
            parts = line.split("\t")
            if len(parts) >= 4:
                name = parts[0]
                cpu = parts[1].rstrip('%')
                mem = parts[2].rstrip('%')
                mem_usage = parts[3]
                try:
                    result["container_stats"][name] = {
                        "cpu_pct": float(cpu),
                        "mem_pct": float(mem),
                        "mem_usage": mem_usage,
                    }
                except ValueError:
                    result["container_stats"][name] = {
                        "cpu_pct": 0,
                        "mem_pct": 0,
                        "mem_usage": mem_usage,
                    }

    return result

def _get_server_crons(host, errors_out):
    """Get cron jobs for a specific server. Returns list of cron entries."""
    if host == "localhost":
        # Reuse the existing build_crons which reads Hermes + system locally
        return build_crons(errors_out)
    
    # Remote: read via SSH (simplified — just raw crontab lines)
    crons = []
    out, rc = _ssh(host, "cat /var/spool/cron/crontabs/root /etc/crontab /etc/cron.d/* 2>/dev/null")
    if rc == 0 and out:
        for line in out.split("\n"):
            line = line.strip()
            if line and not line.startswith("#") and not line.startswith("PATH=") and not line.startswith("SHELL="):
                parts = line.split()
                if len(parts) >= 6 and _looks_like_cron(" ".join(parts[:5])):
                    expr = " ".join(parts[:5])
                    cmd = " ".join(parts[5:])
                    crons.append({
                        "schedule_display": expr,
                        "schedule_desc": cron_to_human(expr) if cron_to_human(expr) else expr,
                        "command": cmd[:120],
                        "source": "system",
                        "host": host,
                    })
    return crons

def _looks_like_cron(field):
    """Quick check if a string looks like a valid cron expression."""
    import re
    return bool(re.match(r'^[\d*/,\-]+\s+[\d*/,\-]+\s+[\d*/,\-]+\s+[\d*/,\-]+\s+[\d*/,\-]+$', field))

def _get_health_for(host, errors_out):
    """Get VPS health for any host. Local = direct /proc, remote = SSH /proc."""
    if host == "localhost":
        return get_hermes_health(errors_out)
    
    # SSH-based health collection (reuse prod pattern but for any host)
    data = {"cpu_pct": None, "mem": None, "disk": None, "ssh_ok": False}
    try:
        out, rc = _ssh(host, "cat /proc/stat /proc/meminfo && df -BG / | tail -1", timeout=8)
        if rc != 0:
            errors_out.append(f"{host} health: SSH failed (code {rc})")
            return data
        data["ssh_ok"] = True
        
        lines = out.split("\n")
        # Parse /proc/stat (first line = cpu total)
        if lines:
            parts = lines[0].split()
            if len(parts) >= 5:
                # Simple single-sample CPU: just report what we can
                total = sum(int(p) for p in parts[1:5]) if len(parts) >= 5 else 1
                idle = int(parts[4]) if len(parts) >= 5 else 0
                data["cpu_pct"] = 0.0  # Need two samples; first call seeds the baseline
        
        # Parse /proc/meminfo
        mem_total = mem_avail = 0
        for line in lines:
            if line.startswith("MemTotal:"):
                mem_total = int(line.split()[1]) // 1024
            if line.startswith("MemAvailable:"):
                mem_avail = int(line.split()[1]) // 1024
        if mem_total > 0:
            mem_used = mem_total - mem_avail
            data["mem"] = {
                "mem_total_mb": mem_total,
                "mem_used_mb": mem_used,
                "mem_available_mb": mem_avail,
                "mem_pct": round(mem_used / mem_total * 100, 1),
            }
        
        # Parse df output
        for line in lines:
            if line.endswith("G") and "/" in line:
                parts = line.split()
                if len(parts) >= 3:
                    try:
                        total_gb = float(parts[1].rstrip("G"))
                        used_gb = float(parts[2].rstrip("G"))
                        data["disk"] = {
                            "disk_total_gb": total_gb,
                            "disk_used_gb": used_gb,
                            "disk_free_gb": round(total_gb - used_gb, 1),
                            "disk_pct": round(used_gb / total_gb * 100, 1) if total_gb > 0 else 0,
                        }
                    except ValueError:
                        pass
        
    except Exception as e:
        errors_out.append(f"{host} health: {e}")
    
    return data

def build_servers(errors_out):
    """Build servers array for the snapshot. One entry per server in servers.json."""
    servers_cfg = _read_servers_config()
    servers = []

    for srv in servers_cfg:
        name = srv["name"]
        host = srv["host"]
        entry = {
            "name": name,
            "display": srv.get("display", name),
            "host": host,
            "type": srv.get("type", "vps"),
            "notes": srv.get("notes", ""),
            "has_dokku": srv.get("has_dokku", False),
            "cron_label": srv.get("cron_label", "JOBS"),
            "health": {},
            "crons": [],
            "dokku": None,
        }

        # Health — use proper collector per host
        if host == "localhost":
            entry["health"] = get_hermes_health(errors_out)
        elif host == "prod":
            entry["health"] = get_prod_health(errors_out)
        else:
            entry["health"] = _get_health_for(host, errors_out)

        # Cron jobs
        entry["crons"] = _get_server_crons(host, errors_out)

        # Dokku (only if applicable)
        if srv.get("has_dokku"):
            dokku = _get_dokku_data(host)
            if dokku:
                entry["dokku"] = dokku

        servers.append(entry)

    return servers

# =============================================================================
# Glance data — weather, Twitch streams, world clock config
# Transferred from glance.vladislavstoyanov.com (glanceapp/glance)
# =============================================================================

# Veliko Tarnovo coordinates (from Open-Meteo geocoding)
_GLANCE_WEATHER_LAT = 43.0812
_GLANCE_WEATHER_LON = 25.6347
_GLANCE_WEATHER_TZ = "Europe/Sofia"

# Twitch GQL — same public endpoint glance uses
_TWITCH_GQL_URL = "https://gql.twitch.tv/gql"
_TWITCH_CLIENT_ID = "kimne78kx3ncx6brgo4mv6wki5h1ko"

# Timezones for world clock (from glance config)
_GLANCE_TIMEZONES = [
    ("Europe/Sofia", "Sofia"),
    ("UTC", "UTC"),
    ("Europe/Rome", "Italy"),
    ("America/Los_Angeles", "US West"),
    ("America/New_York", "US East"),
    ("Asia/Singapore", "Singapore"),
    ("Australia/Sydney", "Australia"),
]

# Twitch channels to monitor (from glance config)
_GLANCE_TWITCH_CHANNELS = [
    "shuncrone", "ladyauroratv", "wejil", "biotrextv", "mordant_cassie",
    "yuca_", "shinosaito", "colt_gunner_mh", "maximilian_dood", "justtus23",
    "yvreux", "hidesashi", "beringr", "garucabra", "6thquill",
    "swaticus05", "captainkaleo", "kaizowario", "peeboz", "vbgkenji", "nzknbr",
]

# Cache
_weather_cache = {"data": None, "ts": 0}
_twitch_cache = {"data": None, "ts": 0}
_WEATHER_CACHE_TTL = 3600    # 1 hour
_TWITCH_CACHE_TTL = 120      # 2 minutes

# WMO weather code → human-readable label
_WMO_CODES = {
    0: "Clear", 1: "Mostly Clear", 2: "Partly Cloudy", 3: "Overcast",
    45: "Fog", 48: "Rime Fog",
    51: "Light Drizzle", 53: "Drizzle", 55: "Heavy Drizzle",
    61: "Light Rain", 63: "Rain", 65: "Heavy Rain",
    71: "Light Snow", 73: "Snow", 75: "Heavy Snow",
    80: "Rain Showers", 81: "Moderate Rain Showers", 82: "Heavy Rain Showers",
    95: "Thunderstorm", 96: "T-storm + Hail", 99: "Heavy T-storm + Hail",
}


def _fetch_weather():
    """Fetch current weather for Veliko Tarnovo from Open-Meteo (free, no key)."""
    global _weather_cache
    now = time.time()
    if _weather_cache["data"] is not None and (now - _weather_cache["ts"]) < _WEATHER_CACHE_TTL:
        return _weather_cache["data"]

    try:
        url = (
            f"https://api.open-meteo.com/v1/forecast"
            f"?latitude={_GLANCE_WEATHER_LAT}&longitude={_GLANCE_WEATHER_LON}"
            f"&current=temperature_2m,apparent_temperature,weather_code,relative_humidity_2m,wind_speed_10m"
            f"&timezone={urllib.parse.quote(_GLANCE_WEATHER_TZ)}"
        )
        req = urllib.request.Request(url, headers={"User-Agent": "MissionControl/1.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))

        current = data.get("current", {})
        code = current.get("weather_code", 0)
        result = {
            "temperature": current.get("temperature_2m"),
            "feels_like": current.get("apparent_temperature"),
            "weather_code": code,
            "weather_label": _WMO_CODES.get(code, f"Code {code}"),
            "humidity": current.get("relative_humidity_2m"),
            "wind_speed": current.get("wind_speed_10m"),
            "location": "Veliko Tarnovo",
            "updated": now,
        }
        _weather_cache = {"data": result, "ts": now}
        return result
    except Exception:
        # Return stale cache if available
        if _weather_cache["data"] is not None:
            return _weather_cache["data"]
        return {"error": "weather fetch failed", "location": "Veliko Tarnovo"}


def _fetch_twitch_streams():
    """Fetch live status for configured Twitch channels via GQL (same approach as glance)."""
    global _twitch_cache
    now = time.time()
    if _twitch_cache["data"] is not None and (now - _twitch_cache["ts"]) < _TWITCH_CACHE_TTL:
        return _twitch_cache["data"]

    try:
        results = []
        # Fetch each channel; Twitch GQL supports batched queries but one-at-a-time is simpler
        for channel in _GLANCE_TWITCH_CHANNELS:
            try:
                info = _fetch_single_twitch_channel(channel)
                results.append(info)
            except Exception:
                results.append({"login": channel, "error": "fetch failed"})

        # Sort: live first, by viewers desc; then offline alphabetically
        live = [r for r in results if r.get("is_live")]
        offline = [r for r in results if not r.get("is_live")]
        live.sort(key=lambda r: -(r.get("viewers_count", 0)))
        offline.sort(key=lambda r: r.get("login", ""))
        sorted_results = live + offline

        data = {"channels": sorted_results, "live_count": len(live), "total": len(sorted_results), "updated": now}
        _twitch_cache = {"data": data, "ts": now}
        return data
    except Exception:
        if _twitch_cache["data"] is not None:
            return _twitch_cache["data"]
        return {"channels": [], "live_count": 0, "total": 0, "error": "twitch fetch failed"}


def _fetch_single_twitch_channel(login):
    """Fetch a single Twitch channel's live status via GQL persisted queries."""
    body = json.dumps([
        {
            "operationName": "ChannelShell",
            "variables": {"login": login},
            "extensions": {
                "persistedQuery": {
                    "version": 1,
                    "sha256Hash": "580ab410bcd0c1ad194224957ae2241e5d252b2c5173d8e0cce9d32d5bb14efe"
                }
            }
        },
        {
            "operationName": "StreamMetadata",
            "variables": {"channelLogin": login},
            "extensions": {
                "persistedQuery": {
                    "version": 1,
                    "sha256Hash": "676ee2f834ede42eb4514cdb432b3134fefc12590080c9a2c9bb44a2a4a63266"
                }
            }
        }
    ]).encode("utf-8")

    req = urllib.request.Request(
        _TWITCH_GQL_URL,
        data=body,
        headers={
            "Client-ID": _TWITCH_CLIENT_ID,
            "Content-Type": "application/json",
            "User-Agent": "MissionControl/1.0",
        }
    )
    with urllib.request.urlopen(req, timeout=10) as resp:
        ops = json.loads(resp.read().decode("utf-8"))

    result = {"login": login, "display_name": login, "is_live": False}

    if not isinstance(ops, list) or len(ops) < 1:
        return result

    # Parse ChannelShell (first operation)
    shell = ops[0].get("data", {})
    user = shell.get("userOrError", {})
    if user.get("__typename") == "User":
        result["display_name"] = user.get("displayName", login)
        result["avatar_url"] = user.get("profileImageURL", "")
        stream = user.get("stream")
        if stream is not None:
            result["is_live"] = True
            result["viewers_count"] = stream.get("viewersCount", 0)
            # Parse StreamMetadata (second operation) for title/category
            if len(ops) >= 2:
                meta = ops[1].get("data", {}).get("user")
                if meta:
                    if meta.get("lastBroadcast"):
                        result["title"] = meta["lastBroadcast"].get("title", "")
                    s = meta.get("stream")
                    if s:
                        result["started_at"] = s.get("createdAt", "")
                        g = s.get("game")
                        if g:
                            result["category"] = g.get("name", "")

    return result


def _get_glance_data():
    """Return combined glance data: timezones, weather, twitch."""
    return {
        "timezones": _GLANCE_TIMEZONES,
        "weather": _fetch_weather(),
        "twitch": _fetch_twitch_streams(),
    }


# =============================================================================
# SSE Multiplexer — publisher framework
# =============================================================================

def _save_channel_retention(event_type, payload, db_path):
    """Save a single channel's data to its retention table. Creates table if needed."""
    table_name = f"retention_{event_type.replace('-', '_')}"
    db = sqlite3.connect(db_path)
    db.execute("PRAGMA journal_mode=WAL")
    db.execute(f"""
        CREATE TABLE IF NOT EXISTS {table_name} (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp REAL NOT NULL,
            payload TEXT NOT NULL
        )
    """)
    db.execute(
        f"INSERT INTO {table_name} (timestamp, payload) VALUES (?, ?)",
        (time.time(), payload)
    )
    # Keep only last 1000 entries per channel
    db.execute(f"""
        DELETE FROM {table_name} WHERE id NOT IN (
            SELECT id FROM {table_name} ORDER BY id DESC LIMIT 1000
        )
    """)
    db.commit()
    db.close()


def publish_channel(event_type, collect_fn, interval, queue, retention_db_path=None):
    """
    Generic channel publisher — runs in its own thread.

    Each cycle:
      1. Collect data via collect_fn() (must be thread-safe)
      2. MD5-fingerprint the JSON output
      3. If changed → push to queue + optionally save to retention DB
      4. Sleep for interval seconds (unless burst-signaled)

    Thread-safe: only touches its own fingerprint entry (guarded by _fp_lock)
    and the shared queue (thread-safe by design).
    """
    global _CHANNEL_FINGERPRINTS
    while True:
        try:
            data = collect_fn()
            payload = json.dumps(data, default=str, sort_keys=True)
            fp = hashlib.md5(payload.encode()).hexdigest()

            with _fp_lock:
                if fp != _CHANNEL_FINGERPRINTS.get(event_type):
                    _CHANNEL_FINGERPRINTS[event_type] = fp
                    changed = True
                else:
                    changed = False

            if changed:
                # Push to SSE queue (non-blocking — drops if queue full)
                try:
                    queue.put_nowait((event_type, payload))
                except queue_module.Full:
                    pass  # Client too slow, drop this push — next cycle will catch up

                # Save to retention DB (best-effort, non-blocking)
                if retention_db_path:
                    try:
                        _save_channel_retention(event_type, payload, retention_db_path)
                    except Exception:
                        pass
        except Exception:
            # Log but don't crash the publisher thread
            import traceback, sys
            print(f"[publisher:{event_type}] ERROR: {traceback.format_exc()}", file=sys.stderr, flush=True)
            time.sleep(1)  # brief pause before retry to avoid tight crash loops

        # Burst mode: if signaled, skip sleep and collect immediately
        burst_event = _CHANNEL_BURST.get(event_type)
        if burst_event and burst_event.is_set():
            burst_event.clear()
            continue
        time.sleep(interval)


def _sse_multiplex_drain(wfile, flush_fn, queue, timeout=0.5):
    """
    Drain the shared SSE queue, writing named events to the client.
    Called from _serve_sse() in a loop.

    Blocks up to `timeout` seconds waiting for the next event.
    Returns True if at least one event was written, False if timeout elapsed.

    Handles BrokenPipeError/ConnectionResetError by re-raising to caller.
    """
    try:
        event_type, payload = queue.get(timeout=timeout)
        msg = f"event: {event_type}\ndata: {payload}\n\n"
        wfile.write(msg.encode("utf-8"))
        flush_fn()
        return True
    except queue_module.Empty:
        # Send a heartbeat comment to keep the connection alive
        wfile.write(b": heartbeat\n\n")
        flush_fn()
        return False


# =============================================================================
# Channel collectors — one function per data source
# Each is thread-safe, never raises, and returns a dict
# =============================================================================

def collect_gateway():
    """Collect gateway state. Returns dict with 'data' key, never raises."""
    gw = read_json(os.path.join(HERMES_HOME, "gateway_state.json"))
    if gw is None:
        return {"error": "gateway_state.json: read failed", "data": {}}
    return {"data": gw}


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
    """Collect profile list with state_db_stats. Returns dict."""
    errors = []
    profiles = build_profiles(errors)
    return {"profiles": profiles, "errors": errors}


def collect_sessions():
    """Collect unified session list (top 50 across all profiles).
    Returns the capped list — the uncapped count is in sessions_ledger."""
    profiles = build_profiles([])
    unified, _ = build_unified_sessions(profiles, [])
    return {"sessions": unified}


def collect_kanban():
    """Collect kanban boards. Returns dict matching the old snapshot kanban shape."""
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


def collect_servers():
    """Collect full server list with health, crons, dokku — same shape as build_servers()."""
    errors = []
    servers = build_servers(errors)
    return {"servers": servers, "errors": errors}


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
        elif path == "/api/content":
            self._serve_content_list()
        elif path == "/api/content/get":
            self._serve_content_get(qs)
        elif path == "/api/glance-data":
            self._serve_glance_data()
        elif path == "/events":
            self._serve_sse()
        elif path == "/api/dokku/logs":
            self._serve_dokku_logs(qs)
        # Static assets (served from dist/)
        elif path.startswith("/assets/") or path == "/favicon.ico":
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

    def _serve_sse(self):
        """SSE stream — multiplexed via shared queue.
        Each channel publishes independently; this handler drains the queue.
        Also sends a heartbeat comment every 0.5s if the queue is empty.
        """
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "keep-alive")
        self._cors_headers()
        self.end_headers()

        # ── Initial burst: signal Tier 1 publishers to push immediately ──
        with _fp_lock:
            for event_type, interval, tier in _CHANNEL_REGISTRY:
                if tier == 1:
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
                    timeout=0.5
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


class ThreadingHTTPServer(http.server.ThreadingHTTPServer):
    """Threaded HTTP server with SO_REUSEADDR."""
    allow_reuse_address = True
    daemon_threads = True


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

    server = ThreadingHTTPServer((HOST, PORT), MissionControlHandler)
    print(f"▶ MISSION CONTROL listening on {HOST}:{PORT}")
    print(f"  GET /                → index.html")
    print(f"  GET /api/snapshot    → legacy full snapshot (polling fallback)")
    print(f"  GET /api/gateway     → per-channel REST endpoints")
    print(f"  GET /api/sessions    → ... (all 10 channels)")
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
