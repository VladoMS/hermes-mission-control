"""Hermes data readers and shared caches."""

import os
import sqlite3
import json
import threading
from server.config import HERMES_HOME
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



# ── Server config readers (shared between health and servers modules) ──

def _read_servers_config():
    """Load servers.json. Returns list of server dicts or empty list on failure."""
    try:
        with open(SERVERS_CONFIG) as f:
            cfg = json.load(f)
        return sorted(cfg.get("servers", []), key=lambda s: s.get("sort_order", 99))
    except Exception:
        return []

