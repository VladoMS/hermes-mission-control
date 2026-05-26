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

import http.server
import json
import os
import sqlite3
import subprocess
import threading
import time
import urllib.parse
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
DASHBOARD_DB = os.path.join(os.path.dirname(os.path.abspath(__file__)), "dashboard.db")
RETENTION_DAYS = 30

# =============================================================================
# Local retention database — instant load + 30-day history
# =============================================================================

def _init_dashboard_db():
    """Create dashboard.db tables if they don't exist."""
    db = sqlite3.connect(DASHBOARD_DB)
    db.execute("PRAGMA journal_mode=WAL")
    db.execute("PRAGMA synchronous=NORMAL")
    db.executescript("""
        CREATE TABLE IF NOT EXISTS snapshots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp REAL NOT NULL,
            snapshot_json TEXT NOT NULL,
            error_count INTEGER DEFAULT 0
        );
        CREATE INDEX IF NOT EXISTS idx_snapshots_ts ON snapshots(timestamp DESC);
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
    """Delete rows older than RETENTION_DAYS and VACUUM."""
    try:
        cutoff = time.time() - (RETENTION_DAYS * 86400)
        db = sqlite3.connect(DASHBOARD_DB)
        deleted = db.execute("DELETE FROM snapshots WHERE timestamp < ?", (cutoff,)).rowcount
        db.commit()
        if deleted > 0:
            db.execute("VACUUM")
        db.close()
        print(f"  DB cleanup: removed {deleted} rows older than {RETENTION_DAYS}d")
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
    """Read raw markdown content. Returns (content, error)."""
    abs_path, err = _validate_content_path(rel_path)
    if err:
        return None, err
    try:
        with open(abs_path, "r") as f:
            return f.read(), None
    except Exception as e:
        return None, f"read error: {e}"


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
            "SELECT id, title, assignee, status, priority, created_at, "
            "started_at, completed_at "
            "FROM tasks ORDER BY priority DESC, created_at ASC"
        ).fetchall()
        db.close()

        tasks = []
        for r in rows:
            tid, title, assignee, status, priority, created_at, started_at, completed_at = r
            tasks.append({
                "id": tid,
                "title": title or "",
                "assignee": assignee or "",
                "status": status or "todo",
                "priority": priority or 0,
                "priority_name": _PRIORITY_NAMES.get(priority or 0, "low"),
                "created_at": created_at,
                "started_at": started_at,
                "completed_at": completed_at,
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
    Returns list sorted by started_at desc, limited to 50 sessions."""
    all_sessions = []

    # Root state.db
    root_path = os.path.join(HERMES_HOME, "state.db")
    if os.path.exists(root_path):
        all_sessions.extend(_read_sessions_from_db(root_path, "default", errors_out))

    # Per-profile state.dbs
    for profile in profiles:
        name = profile.get("name", "")
        if name == "default":
            continue
        prof_dir = os.path.join(HERMES_HOME, "profiles", name)
        state_path = os.path.join(prof_dir, "state.db")
        if os.path.exists(state_path):
            all_sessions.extend(_read_sessions_from_db(state_path, name, errors_out))

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

    # Sort by started_at desc, limit to 50
    all_sessions.sort(key=lambda s: s.get("started_at", 0) or 0, reverse=True)
    return all_sessions[:50]


def build_sessions_ledger(all_sessions):
    """Compute aggregate token/cost stats from a unified session list.
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
        "session_count": len(all_sessions or []),
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

    # --- Cron jobs (Hermes + system) ---
    snapshot["crons"] = build_crons(errors)

    # --- Profiles ---
    snapshot["profiles"] = build_profiles(errors)

    # --- Sessions — unified cross-profile list from all state.dbs ---
    unified = build_unified_sessions(snapshot["profiles"], errors)
    snapshot["sessions"] = unified
    snapshot["sessions_ledger"] = build_sessions_ledger(unified)

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

_INDEX_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "index.html")


class MissionControlHandler(http.server.BaseHTTPRequestHandler):
    """Request handler — serves index, snapshot JSON, and SSE stream."""

    server_version = "MissionControl/1.0"

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        qs = urllib.parse.parse_qs(parsed.query)

        if path == "/":
            self._serve_index()
        elif path == "/api/snapshot":
            self._serve_snapshot()
        elif path == "/api/content":
            self._serve_content_list()
        elif path == "/api/content/get":
            self._serve_content_get(qs)
        elif path == "/events":
            self._serve_sse()
        else:
            self.send_error(HTTPStatus.NOT_FOUND)

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
            # Inject cached snapshot for instant load (before SSE connects)
            cached = _get_latest_snapshot()
            if cached:
                injection = ('<script>window.__mc={snapshot:' + cached + '};</script>').encode("utf-8")
                body = body.replace(b'</head>', injection + b'</head>', 1)
        except Exception:
            body = b"<h1>MISSION CONTROL</h1><p>index.html not found</p>"
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", len(body))
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

    def _serve_sse(self):
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "keep-alive")
        self._cors_headers()
        self.end_headers()

        try:
            while True:
                snapshot = build_snapshot()
                data = json.dumps(snapshot, default=str)
                msg = f"event: snapshot\ndata: {data}\n\n"
                self.wfile.write(msg.encode("utf-8"))
                self.wfile.flush()
                time.sleep(SSE_INTERVAL)
        except (BrokenPipeError, ConnectionResetError, OSError):
            pass

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
        content, err = read_content(rel_path)
        if err:
            self._json_error(HTTPStatus.BAD_REQUEST, err)
            return
        body = json.dumps({"path": rel_path, "content": content}).encode("utf-8")
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
    server = ThreadingHTTPServer((HOST, PORT), MissionControlHandler)
    print(f"▶ MISSION CONTROL listening on {HOST}:{PORT}")
    print(f"  GET /                → index.html")
    print(f"  GET /api/snapshot    → data snapshot (JSON)")
    print(f"  GET /api/content     → document list")
    print(f"  GET /api/content/get → read document")
    print(f"  POST /api/content/save → save document")
    print(f"  GET /events          → SSE stream ({SSE_INTERVAL}s interval)")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n▼ Shutting down.")
        server.shutdown()


if __name__ == "__main__":
    main()
