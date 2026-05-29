"""Database connection management, table schemas, and retention cleanup."""

import sqlite3
import time

def _migrate_add_column(db: sqlite3.Connection, table: str, column: str, col_def: str) -> None:
    """Add a column to an existing table if it doesn't already exist."""
    try:
        db.execute(f"ALTER TABLE {table} ADD COLUMN {column} {col_def}")
    except sqlite3.OperationalError:
        pass  # column already exists


# =============================================================================
# Table schemas — one CREATE per domain model
# Column order must match the model's COLUMNS tuple exactly.
# =============================================================================

TABLE_SCHEMAS = {
    "gateway_data": """CREATE TABLE IF NOT EXISTS gateway_data (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        collected_at REAL NOT NULL,
        pid INTEGER NOT NULL,
        kind TEXT NOT NULL,
        argv TEXT NOT NULL,
        start_time REAL NOT NULL,
        gateway_state TEXT NOT NULL,
        exit_reason TEXT,
        restart_requested INTEGER NOT NULL,
        active_agents INTEGER NOT NULL,
        platforms_json TEXT NOT NULL,
        updated_at TEXT NOT NULL
    )""",
    "process_list_data": """CREATE TABLE IF NOT EXISTS process_list_data (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        collected_at REAL NOT NULL,
        data_json TEXT NOT NULL
    )""",
    "vps_health": """CREATE TABLE IF NOT EXISTS vps_health (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        collected_at REAL NOT NULL,
        host TEXT NOT NULL,
        cpu_pct REAL,
        mem_total_mb REAL,
        mem_used_mb REAL,
        mem_available_mb REAL,
        mem_pct REAL,
        disk_total_gb REAL,
        disk_used_gb REAL,
        disk_free_gb REAL,
        disk_pct REAL,
        uptime REAL,
        ssh_ok INTEGER
    )""",
    "cron_jobs": """CREATE TABLE IF NOT EXISTS cron_jobs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        collected_at REAL NOT NULL,
        server_name TEXT NOT NULL,
        job_id TEXT,
        name TEXT NOT NULL,
        command TEXT NOT NULL,
        schedule_display TEXT NOT NULL,
        schedule_desc TEXT NOT NULL,
        next_run_at TEXT,
        next_run_relative TEXT,
        enabled INTEGER NOT NULL,
        source TEXT NOT NULL,
        source_path TEXT,
        user TEXT
    )""",
    "server_health": """CREATE TABLE IF NOT EXISTS server_health (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        collected_at REAL NOT NULL,
        server_name TEXT NOT NULL,
        cpu_pct REAL,
        mem_total_mb REAL,
        mem_used_mb REAL,
        mem_pct REAL,
        disk_total_gb REAL,
        disk_used_gb REAL,
        disk_pct REAL,
        uptime REAL,
        ssh_ok INTEGER
    )""",
    "dokku_apps": """CREATE TABLE IF NOT EXISTS dokku_apps (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        collected_at REAL NOT NULL,
        server_name TEXT NOT NULL,
        app_name TEXT NOT NULL,
        container_id TEXT NOT NULL,
        image TEXT NOT NULL,
        status TEXT NOT NULL,
        container_name TEXT NOT NULL,
        cpu_pct REAL,
        mem_pct REAL,
        mem_usage TEXT
    )""",
    "profiles": """CREATE TABLE IF NOT EXISTS profiles (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        collected_at REAL NOT NULL,
        description TEXT NOT NULL,
        description_auto TEXT,
        model TEXT,
        provider TEXT,
        has_state_db INTEGER NOT NULL
    )""",
    "profile_stats": """CREATE TABLE IF NOT EXISTS profile_stats (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        collected_at REAL NOT NULL,
        profile_name TEXT NOT NULL,
        session_count INTEGER NOT NULL,
        message_count INTEGER NOT NULL,
        total_input_tokens INTEGER NOT NULL,
        total_output_tokens INTEGER NOT NULL,
        total_cache_read_tokens INTEGER NOT NULL,
        total_cache_write_tokens INTEGER NOT NULL,
        total_estimated_cost_usd REAL NOT NULL,
        active_sessions INTEGER NOT NULL,
        completed_sessions INTEGER NOT NULL
    )""",
    "profile_model_usage": """CREATE TABLE IF NOT EXISTS profile_model_usage (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        collected_at REAL NOT NULL,
        profile_name TEXT NOT NULL,
        model TEXT NOT NULL,
        sessions INTEGER NOT NULL
    )""",
    "sessions": """CREATE TABLE IF NOT EXISTS sessions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        collected_at REAL NOT NULL,
        session_id TEXT NOT NULL,
        profile TEXT NOT NULL,
        title TEXT,
        model TEXT,
        source TEXT,
        started_at REAL,
        ended_at REAL,
        end_reason TEXT,
        message_count INTEGER,
        input_tokens INTEGER,
        output_tokens INTEGER,
        cache_read_tokens INTEGER,
        cache_write_tokens INTEGER,
        estimated_cost_usd REAL,
        tool_call_count INTEGER,
        billing_provider TEXT,
        display_name TEXT
    )""",
    "sessions_ledger": """CREATE TABLE IF NOT EXISTS sessions_ledger (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        collected_at REAL NOT NULL,
        total_input_tokens INTEGER NOT NULL,
        total_output_tokens INTEGER NOT NULL,
        total_cache_read_tokens INTEGER NOT NULL,
        total_cache_write_tokens INTEGER NOT NULL,
        total_estimated_cost_usd REAL NOT NULL,
        cache_hit_rate_pct REAL NOT NULL,
        session_count INTEGER NOT NULL
    )""",
    "ledger_breakdown": """CREATE TABLE IF NOT EXISTS ledger_breakdown (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        collected_at REAL NOT NULL,
        kind TEXT NOT NULL,
        key TEXT NOT NULL,
        input_tokens INTEGER NOT NULL,
        output_tokens INTEGER NOT NULL,
        cache_read_tokens INTEGER NOT NULL,
        cache_write_tokens INTEGER NOT NULL,
        sessions INTEGER NOT NULL,
        estimated_cost_usd REAL NOT NULL
    )""",
    "kanban_tasks": """CREATE TABLE IF NOT EXISTS kanban_tasks (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        collected_at REAL NOT NULL,
        board_name TEXT NOT NULL,
        task_id TEXT NOT NULL,
        title TEXT NOT NULL,
        body TEXT NOT NULL,
        status TEXT NOT NULL,
        priority INTEGER NOT NULL,
        priority_name TEXT NOT NULL,
        assignee TEXT NOT NULL,
        created_at REAL,
        started_at REAL,
        completed_at REAL,
        workspace_path TEXT NOT NULL,
        skills TEXT NOT NULL,
        result TEXT NOT NULL,
        created_by TEXT NOT NULL,
        model_override TEXT NOT NULL
    )""",
    "openrouter_usage": """CREATE TABLE IF NOT EXISTS openrouter_usage (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        collected_at REAL NOT NULL,
        total_usage_usd REAL NOT NULL,
        usage_daily_usd REAL NOT NULL,
        usage_weekly_usd REAL NOT NULL,
        usage_monthly_usd REAL NOT NULL,
        byok_usage_usd REAL NOT NULL,
        credit_limit_usd REAL,
        credit_remaining_usd REAL,
        is_free_tier INTEGER NOT NULL,
        rate_limit_requests INTEGER NOT NULL,
        rate_limit_interval TEXT NOT NULL
    )""",
    "openrouter_activity": """CREATE TABLE IF NOT EXISTS openrouter_activity (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        collected_at REAL NOT NULL,
        date TEXT NOT NULL,
        model TEXT NOT NULL,
        model_permaslug TEXT NOT NULL,
        endpoint_id TEXT NOT NULL,
        provider_name TEXT NOT NULL,
        usage REAL NOT NULL,
        byok_usage_inference REAL NOT NULL,
        requests INTEGER NOT NULL,
        prompt_tokens INTEGER NOT NULL,
        completion_tokens INTEGER NOT NULL,
        reasoning_tokens INTEGER NOT NULL,
        key_name TEXT NOT NULL DEFAULT ''
    )""",
    "openrouter_keys": """CREATE TABLE IF NOT EXISTS openrouter_keys (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        collected_at REAL NOT NULL,
        key_hash TEXT NOT NULL,
        key_name TEXT NOT NULL,
        label TEXT NOT NULL,
        usage REAL NOT NULL,
        usage_daily REAL NOT NULL,
        usage_weekly REAL NOT NULL,
        usage_monthly REAL NOT NULL,
        disabled INTEGER NOT NULL
    )""",
    "daily_costs": """CREATE TABLE IF NOT EXISTS daily_costs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        collected_at REAL NOT NULL,
        date TEXT NOT NULL,
        cost REAL NOT NULL,
        prediction INTEGER NOT NULL,
        daily_average REAL NOT NULL,
        today_so_far REAL NOT NULL,
        openrouter_daily REAL,
        monthly_projection REAL NOT NULL
    )""",
    "work_server_health": """CREATE TABLE IF NOT EXISTS work_server_health (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        collected_at REAL NOT NULL,
        server_name TEXT NOT NULL,
        ansible_group TEXT NOT NULL,
        hostname TEXT NOT NULL,
        health_json TEXT NOT NULL
    )""",
    "work_docker": """CREATE TABLE IF NOT EXISTS work_docker (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        collected_at REAL NOT NULL,
        server_name TEXT NOT NULL,
        hostname TEXT NOT NULL,
        docker_json TEXT NOT NULL
    )""",
    "work_nexus": """CREATE TABLE IF NOT EXISTS work_nexus (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        collected_at REAL NOT NULL,
        server_name TEXT NOT NULL,
        hostname TEXT NOT NULL,
        nexus_json TEXT NOT NULL
    )""",
    "work_jenkins": """CREATE TABLE IF NOT EXISTS work_jenkins (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        collected_at REAL NOT NULL,
        server_name TEXT NOT NULL,
        hostname TEXT NOT NULL,
        jenkins_type TEXT NOT NULL,
        jenkins_json TEXT NOT NULL
    )""",
    "work_postgres": """CREATE TABLE IF NOT EXISTS work_postgres (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        collected_at REAL NOT NULL,
        server_name TEXT NOT NULL,
        hostname TEXT NOT NULL,
        postgres_json TEXT NOT NULL,
        patroni_json TEXT NOT NULL,
        etcd_json TEXT NOT NULL
    )""",
}

TABLE_INDEXES = {
    "gateway_data": "CREATE INDEX IF NOT EXISTS idx_gateway_data_ca ON gateway_data(collected_at DESC)",
    "process_list_data": "CREATE INDEX IF NOT EXISTS idx_process_list_data_ca ON process_list_data(collected_at DESC)",
    "vps_health": "CREATE INDEX IF NOT EXISTS idx_vps_health_ca ON vps_health(collected_at DESC)",
    "cron_jobs": "CREATE INDEX IF NOT EXISTS idx_cron_jobs_ca ON cron_jobs(collected_at DESC)",
    "server_health": "CREATE INDEX IF NOT EXISTS idx_server_health_ca ON server_health(collected_at DESC)",
    "dokku_apps": "CREATE INDEX IF NOT EXISTS idx_dokku_apps_ca ON dokku_apps(collected_at DESC)",
    "profiles": "CREATE INDEX IF NOT EXISTS idx_profiles_ca ON profiles(collected_at DESC)",
    "profile_stats": "CREATE INDEX IF NOT EXISTS idx_profile_stats_ca ON profile_stats(collected_at DESC)",
    "profile_model_usage": "CREATE INDEX IF NOT EXISTS idx_profile_model_usage_ca ON profile_model_usage(collected_at DESC)",
    "sessions": "CREATE INDEX IF NOT EXISTS idx_sessions_ca ON sessions(collected_at DESC)",
    "sessions_ledger": "CREATE INDEX IF NOT EXISTS idx_sessions_ledger_ca ON sessions_ledger(collected_at DESC)",
    "ledger_breakdown": "CREATE INDEX IF NOT EXISTS idx_ledger_breakdown_ca ON ledger_breakdown(collected_at DESC)",
    "kanban_tasks": "CREATE INDEX IF NOT EXISTS idx_kanban_tasks_ca ON kanban_tasks(collected_at DESC)",
    "openrouter_usage": "CREATE INDEX IF NOT EXISTS idx_openrouter_usage_ca ON openrouter_usage(collected_at DESC)",
    "openrouter_activity": "CREATE INDEX IF NOT EXISTS idx_openrouter_activity_ca ON openrouter_activity(collected_at DESC)",
    "openrouter_keys": "CREATE INDEX IF NOT EXISTS idx_openrouter_keys_ca ON openrouter_keys(collected_at DESC)",
    "daily_costs": "CREATE INDEX IF NOT EXISTS idx_daily_costs_ca ON daily_costs(collected_at DESC)",
    "work_server_health": "CREATE INDEX IF NOT EXISTS idx_work_server_health_ca ON work_server_health(collected_at DESC)",
    "work_docker": "CREATE INDEX IF NOT EXISTS idx_work_docker_ca ON work_docker(collected_at DESC)",
    "work_nexus": "CREATE INDEX IF NOT EXISTS idx_work_nexus_ca ON work_nexus(collected_at DESC)",
    "work_jenkins": "CREATE INDEX IF NOT EXISTS idx_work_jenkins_ca ON work_jenkins(collected_at DESC)",
    "work_postgres": "CREATE INDEX IF NOT EXISTS idx_work_postgres_ca ON work_postgres(collected_at DESC)",
}

# =============================================================================
# Database
# =============================================================================

class Database:
    """Manages the dashboard retention database.

    Creates tables, handles migrations, and prunes old data.
    All writes are best-effort (dashboard works without DB).
    """

    def __init__(self, db_path: str):
        self.db_path = db_path

    def initialize(self) -> None:
        """Create all tables and indexes if they don't exist."""
        try:
            db = sqlite3.connect(self.db_path)
            db.execute("PRAGMA journal_mode=WAL")
            db.execute("PRAGMA synchronous=NORMAL")
            for schema in TABLE_SCHEMAS.values():
                db.execute(schema)
            for idx in TABLE_INDEXES.values():
                db.execute(idx)
            # Migrations: add columns for existing tables
            _migrate_add_column(db, "openrouter_activity", "key_name", "TEXT NOT NULL DEFAULT ''")
            db.commit()
            db.close()
        except Exception:
            pass

    def cleanup(self, retention_days: int = 30) -> int:
        """Delete rows older than retention_days from all tables.

        Returns total rows deleted across all tables.
        """
        cutoff = time.time() - (retention_days * 86400)
        total = 0
        try:
            db = sqlite3.connect(self.db_path)
            for table_name in TABLE_SCHEMAS:
                try:
                    deleted = db.execute(
                        f"DELETE FROM {table_name} WHERE collected_at < ?",
                        (cutoff,),
                    ).rowcount
                    total += deleted
                except Exception:
                    pass
            db.commit()
            if total > 0:
                try:
                    db.execute("VACUUM")
                except Exception:
                    pass
            db.close()
        except Exception:
            pass
        return total
