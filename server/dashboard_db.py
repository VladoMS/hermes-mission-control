"""Dashboard retention database."""

import sqlite3
import time
from server.config import DASHBOARD_DB, RETENTION_DAYS, _CHANNEL_REGISTRY
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
