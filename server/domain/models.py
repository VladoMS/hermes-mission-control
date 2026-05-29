"""Domain models — entities with behavior, no infrastructure dependencies."""

from __future__ import annotations
import json
import time
from dataclasses import dataclass, field, asdict


# =============================================================================
# Gateway
# =============================================================================

@dataclass
class GatewayState:
    collected_at: float
    pid: int
    kind: str
    argv: str
    start_time: float
    gateway_state: str
    exit_reason: str | None
    restart_requested: bool
    active_agents: int
    platforms_json: str
    updated_at: str

    @property
    def is_running(self) -> bool:
        return self.gateway_state == "running"

    @property
    def connected_platforms(self) -> list[str]:
        return [
            name
            for name, p in self._platforms().items()
            if p.get("state") == "connected"
        ]

    @property
    def has_errors(self) -> bool:
        return any(
            p.get("error_code") is not None
            for p in self._platforms().values()
        )

    def _platforms(self) -> dict:
        try:
            return json.loads(self.platforms_json)
        except (json.JSONDecodeError, TypeError):
            return {}

    @property
    def platform_count(self) -> int:
        return len(self._platforms())

    @property
    def uptime_seconds(self) -> float | None:
        if self.start_time:
            return self.collected_at - self.start_time
        return None

    COLUMNS = (
        "collected_at", "pid", "kind", "argv", "start_time",
        "gateway_state", "exit_reason", "restart_requested",
        "active_agents", "platforms_json", "updated_at",
    )

    def to_row(self) -> tuple:
        return (
            self.collected_at, self.pid, self.kind, self.argv,
            self.start_time, self.gateway_state, self.exit_reason,
            int(self.restart_requested), self.active_agents,
            self.platforms_json, self.updated_at,
        )

    @classmethod
    def from_row(cls, row: tuple) -> GatewayState:
        return cls(
            collected_at=row[0],
            pid=row[1],
            kind=row[2],
            argv=row[3],
            start_time=row[4],
            gateway_state=row[5],
            exit_reason=row[6],
            restart_requested=bool(row[7]),
            active_agents=row[8],
            platforms_json=row[9],
            updated_at=row[10],
        )

    @classmethod
    def from_gateway_dict(cls, d: dict, collected_at: float | None = None) -> GatewayState:
        return cls(
            collected_at=collected_at or time.time(),
            pid=d.get("pid", 0),
            kind=d.get("kind", ""),
            argv=json.dumps(d.get("argv", [])),
            start_time=d.get("start_time", 0),
            gateway_state=d.get("gateway_state", "unknown"),
            exit_reason=d.get("exit_reason"),
            restart_requested=d.get("restart_requested", False),
            active_agents=d.get("active_agents", 0),
            platforms_json=json.dumps(d.get("platforms", {})),
            updated_at=d.get("updated_at", ""),
        )


# =============================================================================
# Processes (opaque Hermes artifact)
# =============================================================================

@dataclass
class ProcessList:
    collected_at: float
    data_json: str

    @property
    def processes(self) -> list:
        try:
            return json.loads(self.data_json)
        except (json.JSONDecodeError, TypeError):
            return []

    @property
    def count(self) -> int:
        return len(self.processes)

    COLUMNS = ("collected_at", "data_json")

    def to_row(self) -> tuple:
        return (self.collected_at, self.data_json)

    @classmethod
    def from_row(cls, row: tuple) -> ProcessList:
        return cls(collected_at=row[0], data_json=row[1])

    @classmethod
    def from_processes_dict(cls, processes: list, collected_at: float | None = None) -> ProcessList:
        return cls(
            collected_at=collected_at or time.time(),
            data_json=json.dumps(processes),
        )


# =============================================================================
# VPS Health (hermes + prod)
# =============================================================================

@dataclass
class VpsHealth:
    collected_at: float
    host: str
    cpu_pct: float | None = None
    mem_total_mb: float | None = None
    mem_used_mb: float | None = None
    mem_available_mb: float | None = None
    mem_pct: float | None = None
    disk_total_gb: float | None = None
    disk_used_gb: float | None = None
    disk_free_gb: float | None = None
    disk_pct: float | None = None
    uptime: float | None = None
    ssh_ok: bool | None = None

    @property
    def mem_usage_str(self) -> str:
        if self.mem_pct is not None:
            return f"{self.mem_pct:.1f}%"
        return "--"

    @property
    def disk_usage_str(self) -> str:
        if self.disk_pct is not None:
            return f"{self.disk_pct:.1f}%"
        return "--"

    @property
    def is_healthy(self) -> bool:
        cpu_ok = self.cpu_pct is None or self.cpu_pct < 90
        mem_ok = self.mem_pct is None or self.mem_pct < 90
        disk_ok = self.disk_pct is None or self.disk_pct < 90
        return cpu_ok and mem_ok and disk_ok

    COLUMNS = (
        "collected_at", "host", "cpu_pct",
        "mem_total_mb", "mem_used_mb", "mem_available_mb", "mem_pct",
        "disk_total_gb", "disk_used_gb", "disk_free_gb", "disk_pct",
        "uptime", "ssh_ok",
    )

    def to_row(self) -> tuple:
        return (
            self.collected_at, self.host, self.cpu_pct,
            self.mem_total_mb, self.mem_used_mb, self.mem_available_mb, self.mem_pct,
            self.disk_total_gb, self.disk_used_gb, self.disk_free_gb, self.disk_pct,
            self.uptime, int(self.ssh_ok) if self.ssh_ok is not None else None,
        )

    @classmethod
    def from_row(cls, row: tuple) -> VpsHealth:
        return cls(
            collected_at=row[0],
            host=row[1],
            cpu_pct=row[2],
            mem_total_mb=row[3],
            mem_used_mb=row[4],
            mem_available_mb=row[5],
            mem_pct=row[6],
            disk_total_gb=row[7],
            disk_used_gb=row[8],
            disk_free_gb=row[9],
            disk_pct=row[10],
            uptime=row[11],
            ssh_ok=bool(row[12]) if row[12] is not None else None,
        )

    @classmethod
    def from_health_dict(cls, host: str, health: dict, collected_at: float | None = None) -> VpsHealth:
        mem = health.get("mem") or {}
        disk = health.get("disk") or {}
        return cls(
            collected_at=collected_at or time.time(),
            host=host,
            cpu_pct=health.get("cpu_pct"),
            mem_total_mb=mem.get("mem_total_mb"),
            mem_used_mb=mem.get("mem_used_mb"),
            mem_available_mb=mem.get("mem_available_mb"),
            mem_pct=mem.get("mem_pct"),
            disk_total_gb=disk.get("disk_total_gb"),
            disk_used_gb=disk.get("disk_used_gb"),
            disk_free_gb=disk.get("disk_free_gb"),
            disk_pct=disk.get("disk_pct"),
            uptime=health.get("uptime"),
            ssh_ok=health.get("ssh_ok"),
        )


# =============================================================================
# Cron Jobs
# =============================================================================

@dataclass
class CronJob:
    collected_at: float
    server_name: str
    job_id: str | None
    name: str
    command: str
    schedule_display: str
    schedule_desc: str
    next_run_at: str | None
    next_run_relative: str | None
    enabled: bool
    source: str
    source_path: str | None
    user: str | None

    @property
    def summary(self) -> str:
        if self.schedule_desc:
            return f"{self.name} ({self.schedule_desc})"
        return self.name

    COLUMNS = (
        "collected_at", "server_name", "job_id", "name", "command",
        "schedule_display", "schedule_desc", "next_run_at",
        "next_run_relative", "enabled", "source", "source_path", "user",
    )

    def to_row(self) -> tuple:
        return (
            self.collected_at, self.server_name, self.job_id, self.name,
            self.command, self.schedule_display, self.schedule_desc,
            self.next_run_at, self.next_run_relative, int(self.enabled),
            self.source, self.source_path, self.user,
        )

    @classmethod
    def from_row(cls, row: tuple) -> CronJob:
        return cls(
            collected_at=row[0],
            server_name=row[1],
            job_id=row[2],
            name=row[3],
            command=row[4],
            schedule_display=row[5],
            schedule_desc=row[6],
            next_run_at=row[7],
            next_run_relative=row[8],
            enabled=bool(row[9]),
            source=row[10],
            source_path=row[11],
            user=row[12],
        )

    @classmethod
    def from_cron_dict(cls, server_name: str, d: dict, collected_at: float | None = None) -> CronJob:
        return cls(
            collected_at=collected_at or time.time(),
            server_name=server_name,
            job_id=d.get("id"),
            name=d.get("name", ""),
            command=d.get("command", ""),
            schedule_display=d.get("schedule_display", ""),
            schedule_desc=d.get("schedule_desc", ""),
            next_run_at=d.get("next_run_at"),
            next_run_relative=d.get("next_run_relative"),
            enabled=d.get("enabled", True),
            source=d.get("source", "unknown"),
            source_path=d.get("source_path"),
            user=d.get("user"),
        )


# =============================================================================
# Server Health
# =============================================================================

@dataclass
class ServerHealth:
    collected_at: float
    server_name: str
    cpu_pct: float | None = None
    mem_total_mb: float | None = None
    mem_used_mb: float | None = None
    mem_pct: float | None = None
    disk_total_gb: float | None = None
    disk_used_gb: float | None = None
    disk_pct: float | None = None
    uptime: float | None = None
    ssh_ok: bool | None = None

    @property
    def is_healthy(self) -> bool:
        cpu_ok = self.cpu_pct is None or self.cpu_pct < 90
        mem_ok = self.mem_pct is None or self.mem_pct < 90
        disk_ok = self.disk_pct is None or self.disk_pct < 90
        return cpu_ok and mem_ok and disk_ok and (self.ssh_ok is None or self.ssh_ok)

    COLUMNS = (
        "collected_at", "server_name", "cpu_pct",
        "mem_total_mb", "mem_used_mb", "mem_pct",
        "disk_total_gb", "disk_used_gb", "disk_pct",
        "uptime", "ssh_ok",
    )

    def to_row(self) -> tuple:
        return (
            self.collected_at, self.server_name, self.cpu_pct,
            self.mem_total_mb, self.mem_used_mb, self.mem_pct,
            self.disk_total_gb, self.disk_used_gb, self.disk_pct,
            self.uptime, int(self.ssh_ok) if self.ssh_ok is not None else None,
        )

    @classmethod
    def from_row(cls, row: tuple) -> ServerHealth:
        return cls(
            collected_at=row[0],
            server_name=row[1],
            cpu_pct=row[2],
            mem_total_mb=row[3],
            mem_used_mb=row[4],
            mem_pct=row[5],
            disk_total_gb=row[6],
            disk_used_gb=row[7],
            disk_pct=row[8],
            uptime=row[9],
            ssh_ok=bool(row[10]) if row[10] is not None else None,
        )

    @classmethod
    def from_server_health_dict(cls, server_name: str, health: dict, collected_at: float | None = None) -> ServerHealth:
        mem = health.get("mem") or {}
        disk = health.get("disk") or {}
        return cls(
            collected_at=collected_at or time.time(),
            server_name=server_name,
            cpu_pct=health.get("cpu_pct"),
            mem_total_mb=mem.get("mem_total_mb"),
            mem_used_mb=mem.get("mem_used_mb"),
            mem_pct=mem.get("mem_pct"),
            disk_total_gb=disk.get("disk_total_gb"),
            disk_used_gb=disk.get("disk_used_gb"),
            disk_pct=disk.get("disk_pct"),
            uptime=health.get("uptime"),
            ssh_ok=health.get("ssh_ok"),
        )


# =============================================================================
# Dokku Apps
# =============================================================================

@dataclass
class DokkuApp:
    collected_at: float
    server_name: str
    app_name: str
    container_id: str
    image: str
    status: str
    container_name: str
    cpu_pct: float | None = None
    mem_pct: float | None = None
    mem_usage: str | None = None

    @property
    def container_short_id(self) -> str:
        return self.container_id[:12] if len(self.container_id) > 12 else self.container_id

    COLUMNS = (
        "collected_at", "server_name", "app_name", "container_id",
        "image", "status", "container_name", "cpu_pct", "mem_pct", "mem_usage",
    )

    def to_row(self) -> tuple:
        return (
            self.collected_at, self.server_name, self.app_name,
            self.container_id, self.image, self.status, self.container_name,
            self.cpu_pct, self.mem_pct, self.mem_usage,
        )

    @classmethod
    def from_row(cls, row: tuple) -> DokkuApp:
        return cls(
            collected_at=row[0], server_name=row[1], app_name=row[2],
            container_id=row[3], image=row[4], status=row[5],
            container_name=row[6], cpu_pct=row[7], mem_pct=row[8],
            mem_usage=row[9],
        )

    @classmethod
    def from_container_dict(
        cls, server_name: str, app_name: str, container: dict,
        stats: dict | None = None, collected_at: float | None = None,
    ) -> DokkuApp:
        cstats = (stats or {}).get(container.get("name", ""), {}) if stats else {}
        return cls(
            collected_at=collected_at or time.time(),
            server_name=server_name,
            app_name=app_name,
            container_id=container.get("id", ""),
            image=container.get("image", ""),
            status=container.get("status", ""),
            container_name=container.get("name", ""),
            cpu_pct=cstats.get("cpu_pct"),
            mem_pct=cstats.get("mem_pct"),
            mem_usage=cstats.get("mem_usage"),
        )


# =============================================================================
# Profiles
# =============================================================================

@dataclass
class Profile:
    name: str
    collected_at: float
    description: str
    description_auto: str | None = None
    model: str | None = None
    provider: str | None = None
    has_state_db: bool = False

    @property
    def is_default(self) -> bool:
        return self.name == "default"

    COLUMNS = (
        "name", "collected_at", "description", "description_auto",
        "model", "provider", "has_state_db",
    )

    def to_row(self) -> tuple:
        return (
            self.name, self.collected_at, self.description,
            self.description_auto, self.model, self.provider,
            int(self.has_state_db),
        )

    @classmethod
    def from_row(cls, row: tuple) -> Profile:
        return cls(
            name=row[0], collected_at=row[1], description=row[2],
            description_auto=row[3], model=row[4], provider=row[5],
            has_state_db=bool(row[6]),
        )

    @classmethod
    def from_profile_dict(cls, d: dict, collected_at: float | None = None) -> Profile:
        return cls(
            name=d.get("name", ""),
            collected_at=collected_at or time.time(),
            description=d.get("description", ""),
            description_auto=d.get("description_auto"),
            model=d.get("model"),
            provider=d.get("provider"),
            has_state_db=d.get("has_state_db", False),
        )


@dataclass
class ProfileStats:
    collected_at: float
    profile_name: str
    session_count: int
    message_count: int
    total_input_tokens: int
    total_output_tokens: int
    total_cache_read_tokens: int
    total_cache_write_tokens: int
    total_estimated_cost_usd: float
    active_sessions: int
    completed_sessions: int

    @property
    def total_tokens(self) -> int:
        return (
            self.total_input_tokens + self.total_output_tokens
            + self.total_cache_read_tokens + self.total_cache_write_tokens
        )

    @property
    def avg_cost_per_session(self) -> float | None:
        if self.session_count > 0:
            return self.total_estimated_cost_usd / self.session_count
        return None

    COLUMNS = (
        "collected_at", "profile_name", "session_count",
        "message_count", "total_input_tokens", "total_output_tokens",
        "total_cache_read_tokens", "total_cache_write_tokens",
        "total_estimated_cost_usd", "active_sessions", "completed_sessions",
    )

    def to_row(self) -> tuple:
        return (
            self.collected_at, self.profile_name, self.session_count,
            self.message_count, self.total_input_tokens, self.total_output_tokens,
            self.total_cache_read_tokens, self.total_cache_write_tokens,
            self.total_estimated_cost_usd, self.active_sessions,
            self.completed_sessions,
        )

    @classmethod
    def from_row(cls, row: tuple) -> ProfileStats:
        return cls(
            collected_at=row[0], profile_name=row[1], session_count=row[2],
            message_count=row[3], total_input_tokens=row[4],
            total_output_tokens=row[5], total_cache_read_tokens=row[6],
            total_cache_write_tokens=row[7],
            total_estimated_cost_usd=row[8], active_sessions=row[9],
            completed_sessions=row[10],
        )

    @classmethod
    def from_state_db_stats(cls, profile_name: str, stats: dict, collected_at: float | None = None) -> ProfileStats:
        return cls(
            collected_at=collected_at or time.time(),
            profile_name=profile_name,
            session_count=stats.get("session_count", 0),
            message_count=stats.get("message_count", 0),
            total_input_tokens=stats.get("total_input_tokens", 0),
            total_output_tokens=stats.get("total_output_tokens", 0),
            total_cache_read_tokens=stats.get("total_cache_read_tokens", 0),
            total_cache_write_tokens=stats.get("total_cache_write_tokens", 0),
            total_estimated_cost_usd=stats.get("total_estimated_cost_usd", 0.0),
            active_sessions=stats.get("active_sessions", 0),
            completed_sessions=stats.get("completed_sessions", 0),
        )


@dataclass
class ProfileModelUsage:
    collected_at: float
    profile_name: str
    model: str
    sessions: int

    COLUMNS = ("collected_at", "profile_name", "model", "sessions")

    def to_row(self) -> tuple:
        return (self.collected_at, self.profile_name, self.model, self.sessions)

    @classmethod
    def from_row(cls, row: tuple) -> ProfileModelUsage:
        return cls(
            collected_at=row[0], profile_name=row[1],
            model=row[2], sessions=row[3],
        )

    @classmethod
    def from_model_dict(cls, profile_name: str, d: dict, collected_at: float | None = None) -> ProfileModelUsage:
        return cls(
            collected_at=collected_at or time.time(),
            profile_name=profile_name,
            model=d.get("model", ""),
            sessions=d.get("sessions", 0),
        )


# =============================================================================
# Sessions
# =============================================================================

@dataclass
class Session:
    collected_at: float
    session_id: str
    profile: str
    title: str | None = None
    model: str | None = None
    source: str | None = None
    started_at: float | None = None
    ended_at: float | None = None
    end_reason: str | None = None
    message_count: int | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    cache_read_tokens: int | None = None
    cache_write_tokens: int | None = None
    estimated_cost_usd: float | None = None
    tool_call_count: int | None = None
    billing_provider: str | None = None
    display_name: str | None = None

    @property
    def duration_seconds(self) -> float | None:
        if self.started_at is not None and self.ended_at is not None:
            return self.ended_at - self.started_at
        return None

    @property
    def total_tokens(self) -> int:
        return (
            (self.input_tokens or 0) + (self.output_tokens or 0)
            + (self.cache_read_tokens or 0) + (self.cache_write_tokens or 0)
        )

    @property
    def cost_per_token(self) -> float | None:
        t = self.total_tokens
        return (self.estimated_cost_usd / t) if t and self.estimated_cost_usd else None

    @property
    def is_active(self) -> bool:
        return self.ended_at is None

    @property
    def age_hours(self) -> float | None:
        if self.started_at is not None:
            return (self.collected_at - self.started_at) / 3600
        return None

    COLUMNS = (
        "collected_at", "session_id", "profile", "title", "model",
        "source", "started_at", "ended_at", "end_reason",
        "message_count", "input_tokens", "output_tokens",
        "cache_read_tokens", "cache_write_tokens",
        "estimated_cost_usd", "tool_call_count", "billing_provider",
        "display_name",
    )

    def to_row(self) -> tuple:
        return (
            self.collected_at, self.session_id, self.profile, self.title,
            self.model, self.source, self.started_at, self.ended_at,
            self.end_reason, self.message_count, self.input_tokens,
            self.output_tokens, self.cache_read_tokens,
            self.cache_write_tokens, self.estimated_cost_usd,
            self.tool_call_count, self.billing_provider, self.display_name,
        )

    @classmethod
    def from_row(cls, row: tuple) -> Session:
        return cls(
            collected_at=row[0], session_id=row[1], profile=row[2],
            title=row[3], model=row[4], source=row[5],
            started_at=row[6], ended_at=row[7], end_reason=row[8],
            message_count=row[9], input_tokens=row[10],
            output_tokens=row[11], cache_read_tokens=row[12],
            cache_write_tokens=row[13],
            estimated_cost_usd=row[14], tool_call_count=row[15],
            billing_provider=row[16], display_name=row[17],
        )

    @classmethod
    def from_session_dict(cls, profile: str, d: dict, collected_at: float | None = None) -> Session:
        return cls(
            collected_at=collected_at or time.time(),
            session_id=d.get("id", ""),
            profile=profile,
            title=d.get("title"),
            model=d.get("model"),
            source=d.get("source"),
            started_at=d.get("started_at"),
            ended_at=d.get("ended_at"),
            end_reason=d.get("end_reason"),
            message_count=d.get("message_count"),
            input_tokens=d.get("input_tokens"),
            output_tokens=d.get("output_tokens"),
            cache_read_tokens=d.get("cache_read_tokens"),
            cache_write_tokens=d.get("cache_write_tokens"),
            estimated_cost_usd=d.get("estimated_cost_usd"),
            tool_call_count=d.get("tool_call_count"),
            billing_provider=d.get("billing_provider"),
            display_name=d.get("display_name"),
        )


# =============================================================================
# Session Ledger
# =============================================================================

@dataclass
class SessionLedger:
    collected_at: float
    total_input_tokens: int
    total_output_tokens: int
    total_cache_read_tokens: int
    total_cache_write_tokens: int
    total_estimated_cost_usd: float
    cache_hit_rate_pct: float
    session_count: int

    @property
    def total_tokens(self) -> int:
        return (
            self.total_input_tokens + self.total_output_tokens
            + self.total_cache_read_tokens + self.total_cache_write_tokens
        )

    COLUMNS = (
        "collected_at", "total_input_tokens", "total_output_tokens",
        "total_cache_read_tokens", "total_cache_write_tokens",
        "total_estimated_cost_usd", "cache_hit_rate_pct", "session_count",
    )

    def to_row(self) -> tuple:
        return (
            self.collected_at, self.total_input_tokens,
            self.total_output_tokens, self.total_cache_read_tokens,
            self.total_cache_write_tokens, self.total_estimated_cost_usd,
            self.cache_hit_rate_pct, self.session_count,
        )

    @classmethod
    def from_row(cls, row: tuple) -> SessionLedger:
        return cls(
            collected_at=row[0], total_input_tokens=row[1],
            total_output_tokens=row[2], total_cache_read_tokens=row[3],
            total_cache_write_tokens=row[4],
            total_estimated_cost_usd=row[5],
            cache_hit_rate_pct=row[6], session_count=row[7],
        )

    @classmethod
    def from_ledger_dict(cls, d: dict, collected_at: float | None = None) -> SessionLedger:
        return cls(
            collected_at=collected_at or time.time(),
            total_input_tokens=d.get("total_input_tokens", 0),
            total_output_tokens=d.get("total_output_tokens", 0),
            total_cache_read_tokens=d.get("total_cache_read_tokens", 0),
            total_cache_write_tokens=d.get("total_cache_write_tokens", 0),
            total_estimated_cost_usd=d.get("total_estimated_cost_usd", 0.0),
            cache_hit_rate_pct=d.get("cache_hit_rate_pct", 0.0),
            session_count=d.get("session_count", 0),
        )


@dataclass
class LedgerBreakdown:
    collected_at: float
    kind: str
    key: str
    input_tokens: int
    output_tokens: int
    cache_read_tokens: int
    cache_write_tokens: int
    sessions: int
    estimated_cost_usd: float

    @property
    def total_tokens(self) -> int:
        return (
            self.input_tokens + self.output_tokens
            + self.cache_read_tokens + self.cache_write_tokens
        )

    COLUMNS = (
        "collected_at", "kind", "key", "input_tokens", "output_tokens",
        "cache_read_tokens", "cache_write_tokens", "sessions",
        "estimated_cost_usd",
    )

    def to_row(self) -> tuple:
        return (
            self.collected_at, self.kind, self.key, self.input_tokens,
            self.output_tokens, self.cache_read_tokens,
            self.cache_write_tokens, self.sessions,
            self.estimated_cost_usd,
        )

    @classmethod
    def from_row(cls, row: tuple) -> LedgerBreakdown:
        return cls(
            collected_at=row[0], kind=row[1], key=row[2],
            input_tokens=row[3], output_tokens=row[4],
            cache_read_tokens=row[5], cache_write_tokens=row[6],
            sessions=row[7], estimated_cost_usd=row[8],
        )

    @classmethod
    def from_breakdown_item(cls, kind: str, key: str, item: dict, collected_at: float | None = None) -> LedgerBreakdown:
        return cls(
            collected_at=collected_at or time.time(),
            kind=kind, key=key,
            input_tokens=item.get("input_tokens", 0),
            output_tokens=item.get("output_tokens", 0),
            cache_read_tokens=item.get("cache_read_tokens", 0),
            cache_write_tokens=item.get("cache_write_tokens", 0),
            sessions=item.get("sessions", 0),
            estimated_cost_usd=item.get("estimated_cost_usd", 0.0),
        )


# =============================================================================
# Kanban Tasks
# =============================================================================

@dataclass
class KanbanTask:
    collected_at: float
    board_name: str
    task_id: str
    title: str
    body: str
    status: str
    priority: int
    priority_name: str
    assignee: str
    created_at: float | None
    started_at: float | None
    completed_at: float | None
    workspace_path: str
    skills: str
    result: str
    created_by: str
    model_override: str

    COMPLETED_STATUSES = {"done", "archived"}

    @property
    def is_complete(self) -> bool:
        return self.status in self.COMPLETED_STATUSES

    @property
    def is_blocked(self) -> bool:
        return self.status == "blocked"

    @property
    def priority_label(self) -> str:
        return self.priority_name or ["low", "medium", "high", "critical"][min(self.priority, 3)]

    @property
    def age_days(self) -> float | None:
        if self.created_at is not None:
            return (self.collected_at - self.created_at) / 86400
        return None

    COLUMNS = (
        "collected_at", "board_name", "task_id", "title", "body",
        "status", "priority", "priority_name", "assignee",
        "created_at", "started_at", "completed_at",
        "workspace_path", "skills", "result", "created_by",
        "model_override",
    )

    def to_row(self) -> tuple:
        return (
            self.collected_at, self.board_name, self.task_id, self.title,
            self.body, self.status, self.priority, self.priority_name,
            self.assignee, self.created_at, self.started_at,
            self.completed_at, self.workspace_path, self.skills,
            self.result, self.created_by, self.model_override,
        )

    @classmethod
    def from_row(cls, row: tuple) -> KanbanTask:
        return cls(
            collected_at=row[0], board_name=row[1], task_id=str(row[2]),
            title=row[3], body=row[4], status=row[5], priority=row[6],
            priority_name=row[7], assignee=row[8], created_at=row[9],
            started_at=row[10], completed_at=row[11],
            workspace_path=row[12], skills=row[13], result=row[14],
            created_by=row[15], model_override=row[16],
        )

    @classmethod
    def from_task_dict(cls, board_name: str, d: dict, collected_at: float | None = None) -> KanbanTask:
        return cls(
            collected_at=collected_at or time.time(),
            board_name=board_name,
            task_id=str(d.get("id", "")),
            title=d.get("title", ""),
            body=d.get("body", ""),
            status=d.get("status", "todo"),
            priority=d.get("priority", 0),
            priority_name=d.get("priority_name", ""),
            assignee=d.get("assignee", ""),
            created_at=d.get("created_at"),
            started_at=d.get("started_at"),
            completed_at=d.get("completed_at"),
            workspace_path=d.get("workspace_path", ""),
            skills=d.get("skills", ""),
            result=d.get("result", ""),
            created_by=d.get("created_by", ""),
            model_override=d.get("model_override", ""),
        )


# =============================================================================
# OpenRouter Usage
# =============================================================================

@dataclass
class OpenRouterUsage:
    collected_at: float
    total_usage_usd: float
    usage_daily_usd: float
    usage_weekly_usd: float
    usage_monthly_usd: float
    byok_usage_usd: float
    credit_limit_usd: float | None
    credit_remaining_usd: float | None
    is_free_tier: bool
    rate_limit_requests: int
    rate_limit_interval: str

    @property
    def credit_used_pct(self) -> float | None:
        if self.credit_limit_usd and self.credit_limit_usd > 0:
            used = self.credit_limit_usd - (self.credit_remaining_usd or 0)
            return (used / self.credit_limit_usd) * 100
        return None

    COLUMNS = (
        "collected_at", "total_usage_usd", "usage_daily_usd",
        "usage_weekly_usd", "usage_monthly_usd", "byok_usage_usd",
        "credit_limit_usd", "credit_remaining_usd", "is_free_tier",
        "rate_limit_requests", "rate_limit_interval",
    )

    def to_row(self) -> tuple:
        return (
            self.collected_at, self.total_usage_usd, self.usage_daily_usd,
            self.usage_weekly_usd, self.usage_monthly_usd,
            self.byok_usage_usd, self.credit_limit_usd,
            self.credit_remaining_usd, int(self.is_free_tier),
            self.rate_limit_requests, self.rate_limit_interval,
        )

    @classmethod
    def from_row(cls, row: tuple) -> OpenRouterUsage:
        return cls(
            collected_at=row[0], total_usage_usd=row[1],
            usage_daily_usd=row[2], usage_weekly_usd=row[3],
            usage_monthly_usd=row[4], byok_usage_usd=row[5],
            credit_limit_usd=row[6], credit_remaining_usd=row[7],
            is_free_tier=bool(row[8]), rate_limit_requests=row[9],
            rate_limit_interval=row[10],
        )

    @classmethod
    def from_api_dict(cls, d: dict, collected_at: float | None = None) -> OpenRouterUsage:
        return cls(
            collected_at=collected_at or time.time(),
            total_usage_usd=d.get("total_usage_usd", 0.0),
            usage_daily_usd=d.get("usage_daily_usd", 0.0),
            usage_weekly_usd=d.get("usage_weekly_usd", 0.0),
            usage_monthly_usd=d.get("usage_monthly_usd", 0.0),
            byok_usage_usd=d.get("byok_usage_usd", 0.0),
            credit_limit_usd=d.get("credit_limit_usd"),
            credit_remaining_usd=d.get("credit_remaining_usd"),
            is_free_tier=d.get("is_free_tier", False),
            rate_limit_requests=d.get("rate_limit_requests", 0),
            rate_limit_interval=d.get("rate_limit_interval", "10s"),
        )


# =============================================================================
# OpenRouter Activity (per-day per-model usage from Analytics API)
# =============================================================================

@dataclass
class OpenRouterActivity:
    collected_at: float
    date: str
    model: str
    model_permaslug: str
    endpoint_id: str
    provider_name: str
    usage: float
    byok_usage_inference: float
    requests: int
    prompt_tokens: int
    completion_tokens: int
    reasoning_tokens: int
    key_name: str = ""

    COLUMNS = (
        "collected_at", "date", "model", "model_permaslug", "endpoint_id",
        "provider_name", "usage", "byok_usage_inference", "requests",
        "prompt_tokens", "completion_tokens", "reasoning_tokens",
        "key_name",
    )

    def to_row(self) -> tuple:
        return (
            self.collected_at, self.date, self.model, self.model_permaslug,
            self.endpoint_id, self.provider_name, self.usage,
            self.byok_usage_inference, self.requests,
            self.prompt_tokens, self.completion_tokens, self.reasoning_tokens,
            self.key_name,
        )

    @classmethod
    def from_row(cls, row: tuple) -> OpenRouterActivity:
        return cls(
            collected_at=row[0], date=row[1], model=row[2],
            model_permaslug=row[3], endpoint_id=row[4],
            provider_name=row[5], usage=row[6],
            byok_usage_inference=row[7], requests=row[8],
            prompt_tokens=row[9], completion_tokens=row[10],
            reasoning_tokens=row[11],
            key_name=row[12] if len(row) > 12 else "",
        )

    @classmethod
    def from_api_item(cls, item: dict, collected_at: float | None = None) -> OpenRouterActivity:
        return cls(
            collected_at=collected_at or time.time(),
            date=item.get("date", ""),
            model=item.get("model", ""),
            model_permaslug=item.get("model_permaslug", ""),
            endpoint_id=item.get("endpoint_id", ""),
            provider_name=item.get("provider_name", ""),
            usage=item.get("usage", 0.0),
            byok_usage_inference=item.get("byok_usage_inference", 0.0),
            requests=item.get("requests", 0),
            prompt_tokens=item.get("prompt_tokens", 0),
            completion_tokens=item.get("completion_tokens", 0),
            reasoning_tokens=item.get("reasoning_tokens", 0),
            key_name=item.get("key_name", ""),
        )


# =============================================================================
# OpenRouter Key Listing (from GET /api/v1/keys)
# =============================================================================

@dataclass
class OpenRouterKey:
    collected_at: float
    key_hash: str
    key_name: str
    label: str
    usage: float
    usage_daily: float
    usage_weekly: float
    usage_monthly: float
    disabled: bool

    COLUMNS = (
        "collected_at", "key_hash", "key_name", "label",
        "usage", "usage_daily", "usage_weekly", "usage_monthly",
        "disabled",
    )

    def to_row(self) -> tuple:
        return (
            self.collected_at, self.key_hash, self.key_name, self.label,
            self.usage, self.usage_daily, self.usage_weekly, self.usage_monthly,
            int(self.disabled),
        )

    @classmethod
    def from_row(cls, row: tuple) -> OpenRouterKey:
        return cls(
            collected_at=row[0], key_hash=row[1], key_name=row[2],
            label=row[3], usage=row[4], usage_daily=row[5],
            usage_weekly=row[6], usage_monthly=row[7],
            disabled=bool(row[8]),
        )

    @classmethod
    def from_api_dict(cls, d: dict, collected_at: float | None = None) -> OpenRouterKey:
        return cls(
            collected_at=collected_at or time.time(),
            key_hash=d.get("hash", ""),
            key_name=d.get("name", ""),
            label=d.get("label", ""),
            usage=d.get("usage", 0.0),
            usage_daily=d.get("usage_daily", 0.0),
            usage_weekly=d.get("usage_weekly", 0.0),
            usage_monthly=d.get("usage_monthly", 0.0),
            disabled=d.get("disabled", False),
        )


# =============================================================================
# Daily Costs
# =============================================================================

@dataclass
class DailyCost:
    collected_at: float
    date: str
    cost: float
    prediction: bool
    daily_average: float
    today_so_far: float
    openrouter_daily: float | None
    monthly_projection: float

    @property
    def is_prediction(self) -> bool:
        return bool(self.prediction)

    @property
    def projected_overrun(self) -> float | None:
        if self.daily_average > 0:
            return self.monthly_projection - (self.daily_average * 30)
        return None

    COLUMNS = (
        "collected_at", "date", "cost", "prediction",
        "daily_average", "today_so_far", "openrouter_daily",
        "monthly_projection",
    )

    def to_row(self) -> tuple:
        return (
            self.collected_at, self.date, self.cost, int(bool(self.prediction)),
            self.daily_average, self.today_so_far, self.openrouter_daily,
            self.monthly_projection,
        )

    @classmethod
    def from_row(cls, row: tuple) -> DailyCost:
        return cls(
            collected_at=row[0], date=row[1], cost=row[2],
            prediction=bool(row[3]), daily_average=row[4],
            today_so_far=row[5], openrouter_daily=row[6],
            monthly_projection=row[7],
        )

    @classmethod
    def from_cost_dict(cls, d: dict, daily_average: float, today_so_far: float,
                       openrouter_daily: float | None, monthly_projection: float,
                       collected_at: float | None = None) -> DailyCost:
        return cls(
            collected_at=collected_at or time.time(),
            date=d.get("date", ""),
            cost=d.get("cost", 0.0),
            prediction=bool(d.get("prediction", False)),
            daily_average=daily_average,
            today_so_far=today_so_far,
            openrouter_daily=openrouter_daily,
            monthly_projection=monthly_projection,
        )


# =============================================================================
# Work Servers
# =============================================================================

@dataclass
class WorkServerHealth:
    collected_at: float
    server_name: str
    ansible_group: str
    hostname: str
    health_json: str

    COLUMNS = ("collected_at", "server_name", "ansible_group", "hostname", "health_json")

    def to_row(self) -> tuple:
        return (self.collected_at, self.server_name, self.ansible_group, self.hostname, self.health_json)

    @classmethod
    def from_row(cls, row: tuple) -> WorkServerHealth:
        return cls(
            collected_at=row[0], server_name=row[1],
            ansible_group=row[2], hostname=row[3], health_json=row[4],
        )

    @classmethod
    def from_work_dict(cls, srv: dict, collected_at: float | None = None) -> WorkServerHealth:
        return cls(
            collected_at=collected_at or time.time(),
            server_name=srv.get("server_name", ""),
            ansible_group=srv.get("ansible_group", ""),
            hostname=srv.get("hostname", ""),
            health_json=json.dumps(srv.get("health", {})),
        )


@dataclass
class WorkDocker:
    collected_at: float
    server_name: str
    hostname: str
    docker_json: str

    COLUMNS = ("collected_at", "server_name", "hostname", "docker_json")

    def to_row(self) -> tuple:
        return (self.collected_at, self.server_name, self.hostname, self.docker_json)

    @classmethod
    def from_row(cls, row: tuple) -> WorkDocker:
        return cls(
            collected_at=row[0], server_name=row[1],
            hostname=row[2], docker_json=row[3],
        )

    @classmethod
    def from_work_dict(cls, srv: dict, collected_at: float | None = None) -> WorkDocker:
        return cls(
            collected_at=collected_at or time.time(),
            server_name=srv.get("server_name", ""),
            hostname=srv.get("hostname", ""),
            docker_json=json.dumps(srv.get("docker", {})),
        )


@dataclass
class WorkNexus:
    collected_at: float
    server_name: str
    hostname: str
    nexus_json: str

    COLUMNS = ("collected_at", "server_name", "hostname", "nexus_json")

    def to_row(self) -> tuple:
        return (self.collected_at, self.server_name, self.hostname, self.nexus_json)

    @classmethod
    def from_row(cls, row: tuple) -> WorkNexus:
        return cls(
            collected_at=row[0], server_name=row[1],
            hostname=row[2], nexus_json=row[3],
        )

    @classmethod
    def from_work_dict(cls, srv: dict, collected_at: float | None = None) -> WorkNexus:
        return cls(
            collected_at=collected_at or time.time(),
            server_name=srv.get("server_name", ""),
            hostname=srv.get("hostname", ""),
            nexus_json=json.dumps(srv.get("nexus", {})),
        )


@dataclass
class WorkJenkins:
    collected_at: float
    server_name: str
    hostname: str
    jenkins_type: str
    jenkins_json: str

    COLUMNS = ("collected_at", "server_name", "hostname", "jenkins_type", "jenkins_json")

    def to_row(self) -> tuple:
        return (
            self.collected_at, self.server_name, self.hostname,
            self.jenkins_type, self.jenkins_json,
        )

    @classmethod
    def from_row(cls, row: tuple) -> WorkJenkins:
        return cls(
            collected_at=row[0], server_name=row[1],
            hostname=row[2], jenkins_type=row[3],
            jenkins_json=row[4],
        )

    @classmethod
    def from_work_dict(cls, srv: dict, collected_at: float | None = None) -> WorkJenkins:
        return cls(
            collected_at=collected_at or time.time(),
            server_name=srv.get("server_name", ""),
            hostname=srv.get("hostname", ""),
            jenkins_type=srv.get("jenkins_type", ""),
            jenkins_json=json.dumps(srv.get("jenkins", {})),
        )


@dataclass
class WorkPostgres:
    collected_at: float
    server_name: str
    hostname: str
    postgres_json: str
    patroni_json: str
    etcd_json: str

    COLUMNS = (
        "collected_at", "server_name", "hostname",
        "postgres_json", "patroni_json", "etcd_json",
    )

    def to_row(self) -> tuple:
        return (
            self.collected_at, self.server_name, self.hostname,
            self.postgres_json, self.patroni_json, self.etcd_json,
        )

    @classmethod
    def from_row(cls, row: tuple) -> WorkPostgres:
        return cls(
            collected_at=row[0], server_name=row[1],
            hostname=row[2], postgres_json=row[3],
            patroni_json=row[4], etcd_json=row[5],
        )

    @classmethod
    def from_work_dict(cls, srv: dict, collected_at: float | None = None) -> WorkPostgres:
        return cls(
            collected_at=collected_at or time.time(),
            server_name=srv.get("server_name", ""),
            hostname=srv.get("hostname", ""),
            postgres_json=json.dumps(srv.get("postgres", {})),
            patroni_json=json.dumps(srv.get("patroni", {})),
            etcd_json=json.dumps(srv.get("etcd", {})),
        )
