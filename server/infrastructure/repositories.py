"""SQLite implementations of all domain repository interfaces."""

import sqlite3
from server.domain.models import (
    GatewayState, ProcessList, VpsHealth, CronJob, ServerHealth, DokkuApp,
    Profile, ProfileStats, ProfileModelUsage, Session, SessionLedger,
    LedgerBreakdown, KanbanTask, OpenRouterUsage, DailyCost,
    WorkServerHealth, WorkDocker, WorkNexus, WorkJenkins, WorkPostgres,
)
from server.domain.repositories import (
    GatewayRepository, ProcessListRepository, VpsHealthRepository,
    CronJobRepository, ServerHealthRepository, DokkuAppRepository,
    ProfileRepository, ProfileStatsRepository, ProfileModelUsageRepository,
    SessionRepository, SessionLedgerRepository, LedgerBreakdownRepository,
    KanbanTaskRepository, OpenRouterUsageRepository, DailyCostRepository,
    WorkServerHealthRepository, WorkDockerRepository, WorkNexusRepository,
    WorkJenkinsRepository, WorkPostgresRepository,
)

# =============================================================================
# Shared base — common SQL patterns for all repositories
# =============================================================================

class _SqliteBase:
    """Shared SQLite helpers. Every repo inherits from this + its ABC."""

    def __init__(self, db_path: str, table_name: str, model_class):
        self.db_path = db_path
        self.table_name = table_name
        self.model_class = model_class
        self._columns = model_class.COLUMNS
        self._col_list = ", ".join(self._columns)
        self._placeholders = ", ".join("?" * len(self._columns))
        self._insert_sql = (
            f"INSERT INTO {table_name} ({self._col_list}) "
            f"VALUES ({self._placeholders})"
        )
        self._select_sql = f"SELECT {self._col_list} FROM {table_name}"

    def _connect(self):
        return sqlite3.connect(self.db_path)

    def _insert(self, row: tuple) -> None:
        try:
            db = self._connect()
            db.execute(self._insert_sql, row)
            db.commit()
            db.close()
        except Exception:
            pass

    def _insert_many(self, rows: list[tuple]) -> None:
        if not rows:
            return
        try:
            db = self._connect()
            db.executemany(self._insert_sql, rows)
            db.commit()
            db.close()
        except Exception:
            pass

    def _fetch_latest_singleton(self) -> tuple | None:
        try:
            db = self._connect()
            row = db.execute(
                f"{self._select_sql} ORDER BY collected_at DESC LIMIT 1"
            ).fetchone()
            db.close()
            return row
        except Exception:
            return None

    def _fetch_latest_batch(self) -> list[tuple]:
        try:
            db = self._connect()
            rows = db.execute(
                f"{self._select_sql} "
                f"WHERE collected_at = (SELECT MAX(collected_at) "
                f"FROM {self.table_name})"
            ).fetchall()
            db.close()
            return rows
        except Exception:
            return []

    def _delete_before(self, before: float) -> int:
        try:
            db = self._connect()
            deleted = db.execute(
                f"DELETE FROM {self.table_name} WHERE collected_at < ?",
                (before,),
            ).rowcount
            db.commit()
            db.close()
            return deleted or 0
        except Exception:
            return 0


# =============================================================================
# Gateway
# =============================================================================

class SqliteGatewayRepository(_SqliteBase, GatewayRepository):
    def __init__(self, db_path: str):
        super().__init__(db_path, "gateway_data", GatewayState)

    def save(self, state: GatewayState) -> None:
        self._insert(state.to_row())

    def get_latest(self) -> GatewayState | None:
        row = self._fetch_latest_singleton()
        return GatewayState.from_row(row) if row else None

    def cleanup(self, before: float) -> int:
        return self._delete_before(before)


# =============================================================================
# Process List
# =============================================================================

class SqliteProcessListRepository(_SqliteBase, ProcessListRepository):
    def __init__(self, db_path: str):
        super().__init__(db_path, "process_list_data", ProcessList)

    def save(self, proc: ProcessList) -> None:
        self._insert(proc.to_row())

    def get_latest(self) -> ProcessList | None:
        row = self._fetch_latest_singleton()
        return ProcessList.from_row(row) if row else None

    def cleanup(self, before: float) -> int:
        return self._delete_before(before)


# =============================================================================
# VPS Health
# =============================================================================

class SqliteVpsHealthRepository(_SqliteBase, VpsHealthRepository):
    def __init__(self, db_path: str):
        super().__init__(db_path, "vps_health", VpsHealth)

    def save_many(self, items: list[VpsHealth]) -> None:
        self._insert_many([item.to_row() for item in items])

    def get_latest(self) -> list[VpsHealth]:
        return [VpsHealth.from_row(r) for r in self._fetch_latest_batch()]

    def cleanup(self, before: float) -> int:
        return self._delete_before(before)


# =============================================================================
# Cron Jobs
# =============================================================================

class SqliteCronJobRepository(_SqliteBase, CronJobRepository):
    def __init__(self, db_path: str):
        super().__init__(db_path, "cron_jobs", CronJob)

    def save_many(self, items: list[CronJob]) -> None:
        self._insert_many([item.to_row() for item in items])

    def get_latest(self) -> list[CronJob]:
        return [CronJob.from_row(r) for r in self._fetch_latest_batch()]

    def cleanup(self, before: float) -> int:
        return self._delete_before(before)


# =============================================================================
# Server Health
# =============================================================================

class SqliteServerHealthRepository(_SqliteBase, ServerHealthRepository):
    def __init__(self, db_path: str):
        super().__init__(db_path, "server_health", ServerHealth)

    def save_many(self, items: list[ServerHealth]) -> None:
        self._insert_many([item.to_row() for item in items])

    def get_latest(self) -> list[ServerHealth]:
        return [ServerHealth.from_row(r) for r in self._fetch_latest_batch()]

    def cleanup(self, before: float) -> int:
        return self._delete_before(before)


# =============================================================================
# Dokku Apps
# =============================================================================

class SqliteDokkuAppRepository(_SqliteBase, DokkuAppRepository):
    def __init__(self, db_path: str):
        super().__init__(db_path, "dokku_apps", DokkuApp)

    def save_many(self, items: list[DokkuApp]) -> None:
        self._insert_many([item.to_row() for item in items])

    def get_latest(self) -> list[DokkuApp]:
        return [DokkuApp.from_row(r) for r in self._fetch_latest_batch()]

    def cleanup(self, before: float) -> int:
        return self._delete_before(before)


# =============================================================================
# Profile
# =============================================================================

class SqliteProfileRepository(_SqliteBase, ProfileRepository):
    def __init__(self, db_path: str):
        super().__init__(db_path, "profiles", Profile)

    def save_many(self, items: list[Profile]) -> None:
        self._insert_many([item.to_row() for item in items])

    def get_latest(self) -> list[Profile]:
        return [Profile.from_row(r) for r in self._fetch_latest_batch()]

    def cleanup(self, before: float) -> int:
        return self._delete_before(before)


# =============================================================================
# Profile Stats
# =============================================================================

class SqliteProfileStatsRepository(_SqliteBase, ProfileStatsRepository):
    def __init__(self, db_path: str):
        super().__init__(db_path, "profile_stats", ProfileStats)

    def save_many(self, items: list[ProfileStats]) -> None:
        self._insert_many([item.to_row() for item in items])

    def get_latest(self) -> list[ProfileStats]:
        return [ProfileStats.from_row(r) for r in self._fetch_latest_batch()]

    def cleanup(self, before: float) -> int:
        return self._delete_before(before)


# =============================================================================
# Profile Model Usage
# =============================================================================

class SqliteProfileModelUsageRepository(_SqliteBase, ProfileModelUsageRepository):
    def __init__(self, db_path: str):
        super().__init__(db_path, "profile_model_usage", ProfileModelUsage)

    def save_many(self, items: list[ProfileModelUsage]) -> None:
        self._insert_many([item.to_row() for item in items])

    def get_latest(self) -> list[ProfileModelUsage]:
        return [ProfileModelUsage.from_row(r) for r in self._fetch_latest_batch()]

    def cleanup(self, before: float) -> int:
        return self._delete_before(before)


# =============================================================================
# Session
# =============================================================================

class SqliteSessionRepository(_SqliteBase, SessionRepository):
    def __init__(self, db_path: str):
        super().__init__(db_path, "sessions", Session)

    def save_many(self, items: list[Session]) -> None:
        self._insert_many([item.to_row() for item in items])

    def get_latest(self, limit: int = 50) -> list[Session]:
        # Return all sessions from the latest collection batch (capped at `limit`)
        try:
            db = self._connect()
            rows = db.execute(
                f"{self._select_sql} "
                f"WHERE collected_at = (SELECT MAX(collected_at) "
                f"FROM {self.table_name}) "
                f"ORDER BY started_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
            db.close()
            return [Session.from_row(r) for r in rows]
        except Exception:
            return []

    def cleanup(self, before: float) -> int:
        return self._delete_before(before)


# =============================================================================
# Session Ledger
# =============================================================================

class SqliteSessionLedgerRepository(_SqliteBase, SessionLedgerRepository):
    def __init__(self, db_path: str):
        super().__init__(db_path, "sessions_ledger", SessionLedger)

    def save(self, ledger: SessionLedger) -> None:
        self._insert(ledger.to_row())

    def get_latest(self) -> SessionLedger | None:
        row = self._fetch_latest_singleton()
        return SessionLedger.from_row(row) if row else None

    def cleanup(self, before: float) -> int:
        return self._delete_before(before)


# =============================================================================
# Ledger Breakdown
# =============================================================================

class SqliteLedgerBreakdownRepository(_SqliteBase, LedgerBreakdownRepository):
    def __init__(self, db_path: str):
        super().__init__(db_path, "ledger_breakdown", LedgerBreakdown)

    def save_many(self, items: list[LedgerBreakdown]) -> None:
        self._insert_many([item.to_row() for item in items])

    def get_latest(self) -> list[LedgerBreakdown]:
        return [LedgerBreakdown.from_row(r) for r in self._fetch_latest_batch()]

    def cleanup(self, before: float) -> int:
        return self._delete_before(before)


# =============================================================================
# Kanban Tasks
# =============================================================================

class SqliteKanbanTaskRepository(_SqliteBase, KanbanTaskRepository):
    def __init__(self, db_path: str):
        super().__init__(db_path, "kanban_tasks", KanbanTask)

    def save_many(self, items: list[KanbanTask]) -> None:
        self._insert_many([item.to_row() for item in items])

    def get_latest(self) -> list[KanbanTask]:
        return [KanbanTask.from_row(r) for r in self._fetch_latest_batch()]

    def cleanup(self, before: float) -> int:
        return self._delete_before(before)


# =============================================================================
# OpenRouter Usage
# =============================================================================

class SqliteOpenRouterUsageRepository(_SqliteBase, OpenRouterUsageRepository):
    def __init__(self, db_path: str):
        super().__init__(db_path, "openrouter_usage", OpenRouterUsage)

    def save(self, usage: OpenRouterUsage) -> None:
        self._insert(usage.to_row())

    def get_latest(self) -> OpenRouterUsage | None:
        row = self._fetch_latest_singleton()
        return OpenRouterUsage.from_row(row) if row else None

    def cleanup(self, before: float) -> int:
        return self._delete_before(before)


# =============================================================================
# Daily Costs
# =============================================================================

class SqliteDailyCostRepository(_SqliteBase, DailyCostRepository):
    def __init__(self, db_path: str):
        super().__init__(db_path, "daily_costs", DailyCost)

    def save_many(self, items: list[DailyCost]) -> None:
        self._insert_many([item.to_row() for item in items])

    def get_latest(self) -> list[DailyCost]:
        return [DailyCost.from_row(r) for r in self._fetch_latest_batch()]

    def cleanup(self, before: float) -> int:
        return self._delete_before(before)


# =============================================================================
# Work Server Health
# =============================================================================

class SqliteWorkServerHealthRepository(_SqliteBase, WorkServerHealthRepository):
    def __init__(self, db_path: str):
        super().__init__(db_path, "work_server_health", WorkServerHealth)

    def save_many(self, items: list[WorkServerHealth]) -> None:
        self._insert_many([item.to_row() for item in items])

    def get_latest(self) -> list[WorkServerHealth]:
        return [WorkServerHealth.from_row(r) for r in self._fetch_latest_batch()]

    def cleanup(self, before: float) -> int:
        return self._delete_before(before)


# =============================================================================
# Work Docker
# =============================================================================

class SqliteWorkDockerRepository(_SqliteBase, WorkDockerRepository):
    def __init__(self, db_path: str):
        super().__init__(db_path, "work_docker", WorkDocker)

    def save_many(self, items: list[WorkDocker]) -> None:
        self._insert_many([item.to_row() for item in items])

    def get_latest(self) -> list[WorkDocker]:
        return [WorkDocker.from_row(r) for r in self._fetch_latest_batch()]

    def cleanup(self, before: float) -> int:
        return self._delete_before(before)


# =============================================================================
# Work Nexus
# =============================================================================

class SqliteWorkNexusRepository(_SqliteBase, WorkNexusRepository):
    def __init__(self, db_path: str):
        super().__init__(db_path, "work_nexus", WorkNexus)

    def save_many(self, items: list[WorkNexus]) -> None:
        self._insert_many([item.to_row() for item in items])

    def get_latest(self) -> list[WorkNexus]:
        return [WorkNexus.from_row(r) for r in self._fetch_latest_batch()]

    def cleanup(self, before: float) -> int:
        return self._delete_before(before)


# =============================================================================
# Work Jenkins
# =============================================================================

class SqliteWorkJenkinsRepository(_SqliteBase, WorkJenkinsRepository):
    def __init__(self, db_path: str):
        super().__init__(db_path, "work_jenkins", WorkJenkins)

    def save_many(self, items: list[WorkJenkins]) -> None:
        self._insert_many([item.to_row() for item in items])

    def get_latest(self) -> list[WorkJenkins]:
        return [WorkJenkins.from_row(r) for r in self._fetch_latest_batch()]

    def cleanup(self, before: float) -> int:
        return self._delete_before(before)


# =============================================================================
# Work Postgres
# =============================================================================

class SqliteWorkPostgresRepository(_SqliteBase, WorkPostgresRepository):
    def __init__(self, db_path: str):
        super().__init__(db_path, "work_postgres", WorkPostgres)

    def save_many(self, items: list[WorkPostgres]) -> None:
        self._insert_many([item.to_row() for item in items])

    def get_latest(self) -> list[WorkPostgres]:
        return [WorkPostgres.from_row(r) for r in self._fetch_latest_batch()]

    def cleanup(self, before: float) -> int:
        return self._delete_before(before)
