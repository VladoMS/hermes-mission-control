"""Collector classes — orchestrate data collection from Hermes sources and persist to repos.

Each collector:
  1. Reads from a Hermes data source (file, SSH, API)
  2. Builds domain model(s)
  3. Saves to the appropriate repository
  4. Returns serializable data for SSE publishing
"""

from __future__ import annotations
import json
import os
import time
from dataclasses import asdict

from server.config import HERMES_HOME
from server.readers import read_json, _read_servers_config
from server.health import get_hermes_health, get_prod_health
from server.profiles import build_profiles
from server.sessions import build_unified_sessions, build_sessions_ledger, build_daily_costs
from server.servers import build_servers, _get_dokku_data, _get_server_crons
from server.kanban import read_kanban_boards
from server.work_servers import (
    collect_work_system_health as _collect_work_system_health,
    collect_work_docker as _collect_work_docker,
    collect_work_nexus as _collect_work_nexus,
    collect_work_jenkins as _collect_work_jenkins,
    collect_work_postgres as _collect_work_postgres,
)
from server.domain.repositories import (
    GatewayRepository, ProcessListRepository,
    VpsHealthRepository, CronJobRepository,
    ServerHealthRepository, DokkuAppRepository,
    ProfileRepository, ProfileStatsRepository,
    ProfileModelUsageRepository, SessionRepository,
    SessionLedgerRepository, LedgerBreakdownRepository,
    KanbanTaskRepository, OpenRouterUsageRepository,
    DailyCostRepository,
    WorkServerHealthRepository, WorkDockerRepository,
    WorkNexusRepository, WorkJenkinsRepository,
    WorkPostgresRepository,
)
from server.domain.models import (
    GatewayState, ProcessList, VpsHealth, CronJob,
    ServerHealth, DokkuApp, Profile, ProfileStats,
    ProfileModelUsage, Session, SessionLedger,
    LedgerBreakdown, KanbanTask, OpenRouterUsage,
    DailyCost,
    WorkServerHealth, WorkDocker, WorkNexus,
    WorkJenkins, WorkPostgres,
)

# =============================================================================
# OpenRouter Usage (inline)
# =============================================================================

def _fetch_openrouter_usage():
    import urllib.request
    import urllib.error
    import re

    api_key = None
    env_path = os.path.join(HERMES_HOME, ".env")
    try:
        with open(env_path, "r") as f:
            for line in f:
                m = re.match(r'^OPENROUTER_API_KEY\s*=\s*(.+)$', line.strip())
                if m:
                    api_key = m.group(1).strip().strip('"').strip("'")
                    break
    except Exception:
        pass

    if not api_key:
        return {"error": "OPENROUTER_API_KEY not found in .env"}

    try:
        req = urllib.request.Request(
            "https://openrouter.ai/api/v1/auth/key",
            headers={"Authorization": f"Bearer {api_key}"}
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            body = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        return {"error": f"OpenRouter API HTTP {e.code}: {e.reason}"}
    except urllib.error.URLError as e:
        return {"error": f"OpenRouter API unreachable: {e.reason}"}
    except json.JSONDecodeError:
        return {"error": "OpenRouter API returned invalid JSON"}
    except Exception as e:
        return {"error": f"OpenRouter API error: {e}"}

    data = body.get("data", {}) if isinstance(body, dict) else {}
    rate = data.get("rate_limit", {}) or {}
    limit = data.get("limit")
    limit_remaining = data.get("limit_remaining")

    return {
        "total_usage_usd": data.get("usage", 0),
        "usage_daily_usd": data.get("usage_daily", 0),
        "usage_weekly_usd": data.get("usage_weekly", 0),
        "usage_monthly_usd": data.get("usage_monthly", 0),
        "byok_usage_usd": data.get("byok_usage", 0),
        "credit_limit_usd": limit,
        "credit_remaining_usd": limit_remaining,
        "is_free_tier": data.get("is_free_tier", False),
        "rate_limit_requests": rate.get("requests", -1),
        "rate_limit_interval": rate.get("interval", "10s"),
    }


# =============================================================================
# Gateway
# =============================================================================

class GatewayCollector:
    def __init__(self, repo: GatewayRepository, hermes_home: str = HERMES_HOME):
        self.repo = repo
        self.hermes_home = hermes_home

    def collect(self) -> dict:
        gw = read_json(os.path.join(self.hermes_home, "gateway_state.json"))
        if gw is None:
            return {"error": "gateway_state.json: read failed", "gateway_state": "unknown"}
        model = GatewayState.from_gateway_dict(gw)
        self.repo.save(model)
        result = asdict(model)
        result["platforms"] = model._platforms()
        result["is_running"] = model.is_running
        result["connected_platforms"] = model.connected_platforms
        result["has_errors"] = model.has_errors
        result["platform_count"] = model.platform_count
        result["uptime_seconds"] = model.uptime_seconds
        result["collected_at"] = model.collected_at
        return result


# =============================================================================
# Process List
# =============================================================================

class ProcessListCollector:
    def __init__(self, repo: ProcessListRepository, hermes_home: str = HERMES_HOME):
        self.repo = repo
        self.hermes_home = hermes_home

    def collect(self) -> dict:
        procs = read_json(os.path.join(self.hermes_home, "processes.json"))
        data = procs if procs is not None else []
        model = ProcessList.from_processes_dict(data)
        self.repo.save(model)
        result = asdict(model)
        result["processes"] = data
        return result


# =============================================================================
# VPS Health (hermes)
# =============================================================================

class HermesHealthCollector:
    def __init__(self, repo: VpsHealthRepository):
        self.repo = repo

    def collect(self) -> dict:
        errors = []
        result = get_hermes_health(errors)
        model = VpsHealth.from_health_dict("hermes", result)
        self.repo.save_many([model])
        enriched = asdict(model)
        enriched["mem"] = result.get("mem", {})
        enriched["disk"] = result.get("disk", {})
        enriched["errors"] = errors
        return enriched


class ProdHealthCollector:
    def __init__(self, repo: VpsHealthRepository):
        self.repo = repo

    def collect(self) -> dict:
        errors = []
        health = get_prod_health(errors)
        model = VpsHealth.from_health_dict("prod", health)
        self.repo.save_many([model])
        enriched = asdict(model)
        enriched["mem"] = health.get("mem", {})
        enriched["disk"] = health.get("disk", {})
        enriched["errors"] = errors
        return enriched


# =============================================================================
# Profiles
# =============================================================================

class ProfileCollector:
    def __init__(
        self,
        profile_repo: ProfileRepository,
        stats_repo: ProfileStatsRepository,
        model_usage_repo: ProfileModelUsageRepository,
    ):
        self.profile_repo = profile_repo
        self.stats_repo = stats_repo
        self.model_usage_repo = model_usage_repo

    def collect(self) -> list[dict]:
        raw = build_profiles([])
        collected_at = time.time()
        profiles = []
        stats_list = []
        model_usage_list = []
        enriched = []

        for d in raw:
            model = Profile.from_profile_dict(d, collected_at)
            profiles.append(model)
            sdb = d.get("state_db_stats") or {}
            enriched_profile = asdict(model)
            if sdb:
                enriched_profile["state_db_stats"] = sdb
                stats_list.append(ProfileStats.from_state_db_stats(
                    d.get("name", ""), sdb, collected_at,
                ))
                for m in sdb.get("models", []):
                    model_usage_list.append(ProfileModelUsage.from_model_dict(
                        d.get("name", ""), m, collected_at,
                    ))
            else:
                enriched_profile["state_db_stats"] = None
            enriched.append(enriched_profile)

        self.profile_repo.save_many(profiles)
        if stats_list:
            self.stats_repo.save_many(stats_list)
        if model_usage_list:
            self.model_usage_repo.save_many(model_usage_list)

        return enriched


# =============================================================================
# Sessions
# =============================================================================

class SessionCollector:
    def __init__(self, repo: SessionRepository):
        self.repo = repo

    def collect(self) -> list[dict]:
        profiles = build_profiles([])
        unified, _ = build_unified_sessions(profiles, [])
        collected_at = time.time()
        sessions = [
            Session.from_session_dict(
                "default" if not s.get("profile") else s.get("profile"),
                s, collected_at,
            ) for s in unified
        ]
        self.repo.save_many(sessions)
        enriched = []
        for raw, model in zip(unified, sessions):
            entry = asdict(model)
            entry["id"] = model.session_id
            enriched.append(entry)
        return enriched


# =============================================================================
# Session Ledger
# =============================================================================

class SessionLedgerCollector:
    def __init__(
        self,
        ledger_repo: SessionLedgerRepository,
        breakdown_repo: LedgerBreakdownRepository,
    ):
        self.ledger_repo = ledger_repo
        self.breakdown_repo = breakdown_repo

    def collect(self) -> dict:
        profiles = build_profiles([])
        unified, total_count = build_unified_sessions(profiles, [])
        ledger = build_sessions_ledger(unified, total_count)
        collected_at = time.time()

        model = SessionLedger.from_ledger_dict(ledger, collected_at)
        self.ledger_repo.save(model)

        breakdowns = []
        for kind, key in [("model", "per_model"), ("profile", "per_profile")]:
            items = ledger.get(key, {})
            if isinstance(items, dict):
                for k, v in items.items():
                    breakdowns.append(LedgerBreakdown.from_breakdown_item(kind, k, v, collected_at))
        if breakdowns:
            self.breakdown_repo.save_many(breakdowns)

        enriched = asdict(model)
        enriched["per_model"] = ledger.get("per_model", {})
        enriched["per_profile"] = ledger.get("per_profile", {})
        return enriched


# =============================================================================
# Kanban
# =============================================================================

class KanbanCollector:
    def __init__(self, repo: KanbanTaskRepository):
        self.repo = repo

    def collect(self) -> dict:
        errors = []
        result = read_kanban_boards(errors)
        collected_at = time.time()
        tasks = []
        boards = result.get("boards", {})
        for board_name, board in boards.items():
            columns = board.get("columns", {})
            for col_name, col_tasks in columns.items():
                for t in col_tasks:
                    task = KanbanTask.from_task_dict(board_name, t, collected_at)
                    if task.status == "todo" and col_name != "todo":
                        task.status = col_name
                    tasks.append(task)
        if tasks:
            self.repo.save_many(tasks)
        result["errors"] = errors
        result["_model_count"] = len(tasks)
        return result


# =============================================================================
# Dokku
# =============================================================================

class DokkuCollector:
    def __init__(self, repo: DokkuAppRepository):
        self.repo = repo

    def collect(self) -> dict:
        servers_cfg = _read_servers_config()
        for srv in servers_cfg:
            if srv.get("has_dokku"):
                data = _get_dokku_data(srv["host"])
                if data:
                    collected_at = time.time()
                    apps = data.get("apps", [])
                    containers = data.get("containers", [])
                    stats = data.get("container_stats", {})
                    dokku_apps = []
                    for app_name in apps:
                        for c in (containers or []):
                            if c.get("name", "").startswith(app_name + "."):
                                dokku_apps.append(DokkuApp.from_container_dict(
                                    srv["name"], app_name, c, stats, collected_at,
                                ))
                    if dokku_apps:
                        self.repo.save_many(dokku_apps)
                    enriched = {
                        "server": srv["name"],
                        "dokku": data,
                        "_model_count": len(dokku_apps),
                        "_collected_at": collected_at,
                    }
                    return enriched
        return {"server": None, "dokku": None}


# =============================================================================
# Server Crons
# =============================================================================

class ServerCronCollector:
    def __init__(self, repo: CronJobRepository):
        self.repo = repo

    def collect(self) -> dict:
        servers_cfg = _read_servers_config()
        crons_by_server = {}
        errors = []
        collected_at = time.time()
        all_crons = []

        for srv in servers_cfg:
            cron_dicts = _get_server_crons(srv["host"], errors)
            crons_by_server[srv["name"]] = cron_dicts
            for c in (cron_dicts or []):
                all_crons.append(CronJob.from_cron_dict(srv["name"], c, collected_at))

        if all_crons:
            self.repo.save_many(all_crons)
        return {"crons": crons_by_server, "errors": errors, "_model_count": len(all_crons)}


# =============================================================================
# Servers (health data extracted for persistence)
# =============================================================================

class ServerCollector:
    def __init__(self, repo: ServerHealthRepository):
        self.repo = repo

    def collect(self) -> list[dict]:
        raw = build_servers([])
        collected_at = time.time()
        health_entries = []

        for srv in raw:
            h = srv.get("health")
            if h and (h.get("cpu_pct") is not None or h.get("mem") is not None):
                health_entries.append(ServerHealth.from_server_health_dict(
                    srv.get("name", ""), h, collected_at,
                ))

        if health_entries:
            self.repo.save_many(health_entries)

        enriched = []
        for srv in raw:
            entry = dict(srv)
            entry["_collected_at"] = collected_at
            enriched.append(entry)
        return enriched


# =============================================================================
# OpenRouter Usage
# =============================================================================

class OpenRouterUsageCollector:
    def __init__(self, repo: OpenRouterUsageRepository):
        self.repo = repo

    def collect(self) -> dict:
        raw = _fetch_openrouter_usage()
        if "error" in raw:
            return raw
        model = OpenRouterUsage.from_api_dict(raw)
        self.repo.save(model)
        enriched = asdict(model)
        enriched["collected_at"] = model.collected_at
        return enriched


# =============================================================================
# Daily Costs
# =============================================================================

class DailyCostCollector:
    def __init__(self, repo: DailyCostRepository, or_collector: OpenRouterUsageCollector | None = None):
        self.repo = repo
        self._or_collector = or_collector

    def collect(self) -> dict:
        profiles = build_profiles([])
        if self._or_collector:
            or_raw = self._or_collector.collect()
        else:
            or_raw = _fetch_openrouter_usage()
        result = build_daily_costs(profiles, [], openrouter_usage=or_raw)
        collected_at = time.time()

        days = result.get("days", [])
        daily_avg = result.get("daily_average", 0.0)
        today_sofar = result.get("today_so_far", 0.0)
        or_daily = result.get("openrouter_daily")
        monthly_proj = result.get("monthly_projection", 0.0)

        cost_list = [
            DailyCost.from_cost_dict(d, daily_avg, today_sofar, or_daily, monthly_proj, collected_at)
            for d in days
        ]
        if cost_list:
            self.repo.save_many(cost_list)

        result["_model_count"] = len(cost_list)
        return result


# =============================================================================
# Work Servers
# =============================================================================

class WorkSystemCollector:
    def __init__(self, repo: WorkServerHealthRepository):
        self.repo = repo

    def collect(self) -> dict:
        raw = _collect_work_system_health()
        collected_at = time.time()
        items = [WorkServerHealth.from_work_dict(s, collected_at) for s in raw.get("servers", [])]
        if items:
            self.repo.save_many(items)
        return raw


class WorkDockerCollector:
    def __init__(self, repo: WorkDockerRepository):
        self.repo = repo

    def collect(self) -> dict:
        raw = _collect_work_docker()
        collected_at = time.time()
        items = [WorkDocker.from_work_dict(s, collected_at) for s in raw.get("servers", [])]
        if items:
            self.repo.save_many(items)
        return raw


class WorkNexusCollector:
    def __init__(self, repo: WorkNexusRepository):
        self.repo = repo

    def collect(self) -> dict:
        raw = _collect_work_nexus()
        collected_at = time.time()
        items = [WorkNexus.from_work_dict(s, collected_at) for s in raw.get("servers", [])]
        if items:
            self.repo.save_many(items)
        return raw


class WorkJenkinsCollector:
    def __init__(self, repo: WorkJenkinsRepository):
        self.repo = repo

    def collect(self) -> dict:
        raw = _collect_work_jenkins()
        collected_at = time.time()
        items = [WorkJenkins.from_work_dict(s, collected_at) for s in raw.get("servers", [])]
        if items:
            self.repo.save_many(items)
        return raw


class WorkPostgresCollector:
    def __init__(self, repo: WorkPostgresRepository):
        self.repo = repo

    def collect(self) -> dict:
        raw = _collect_work_postgres()
        collected_at = time.time()
        items = [WorkPostgres.from_work_dict(s, collected_at) for s in raw.get("servers", [])]
        if items:
            self.repo.save_many(items)
        return raw
