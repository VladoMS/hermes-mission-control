"""Repository interfaces (ABCs) for all domain models.

Each repo defines the contract for persisting and retrieving a single domain
aggregate. Concrete SQLite implementations live in infrastructure/repositories.py.
"""

from __future__ import annotations
from abc import ABC, abstractmethod
from server.domain.models import (
    GatewayState,
    ProcessList,
    VpsHealth,
    CronJob,
    ServerHealth,
    DokkuApp,
    Profile,
    ProfileStats,
    ProfileModelUsage,
    Session,
    SessionLedger,
    LedgerBreakdown,
    KanbanTask,
    OpenRouterUsage,
    OpenRouterKey,
    DailyCost,
    WorkServerHealth,
    WorkDocker,
    WorkNexus,
    WorkJenkins,
    WorkPostgres,
)


class GatewayRepository(ABC):
    @abstractmethod
    def save(self, state: GatewayState) -> None: ...
    @abstractmethod
    def get_latest(self) -> GatewayState | None: ...
    @abstractmethod
    def cleanup(self, before: float) -> int: ...


class ProcessListRepository(ABC):
    @abstractmethod
    def save(self, proc: ProcessList) -> None: ...
    @abstractmethod
    def get_latest(self) -> ProcessList | None: ...
    @abstractmethod
    def cleanup(self, before: float) -> int: ...


class VpsHealthRepository(ABC):
    @abstractmethod
    def save_many(self, items: list[VpsHealth]) -> None: ...
    @abstractmethod
    def get_latest(self) -> list[VpsHealth]: ...
    @abstractmethod
    def cleanup(self, before: float) -> int: ...


class CronJobRepository(ABC):
    @abstractmethod
    def save_many(self, items: list[CronJob]) -> None: ...
    @abstractmethod
    def get_latest(self) -> list[CronJob]: ...
    @abstractmethod
    def cleanup(self, before: float) -> int: ...


class ServerHealthRepository(ABC):
    @abstractmethod
    def save_many(self, items: list[ServerHealth]) -> None: ...
    @abstractmethod
    def get_latest(self) -> list[ServerHealth]: ...
    @abstractmethod
    def cleanup(self, before: float) -> int: ...


class DokkuAppRepository(ABC):
    @abstractmethod
    def save_many(self, items: list[DokkuApp]) -> None: ...
    @abstractmethod
    def get_latest(self) -> list[DokkuApp]: ...
    @abstractmethod
    def cleanup(self, before: float) -> int: ...


class ProfileRepository(ABC):
    @abstractmethod
    def save_many(self, items: list[Profile]) -> None: ...
    @abstractmethod
    def get_latest(self) -> list[Profile]: ...
    @abstractmethod
    def cleanup(self, before: float) -> int: ...


class ProfileStatsRepository(ABC):
    @abstractmethod
    def save_many(self, items: list[ProfileStats]) -> None: ...
    @abstractmethod
    def get_latest(self) -> list[ProfileStats]: ...
    @abstractmethod
    def cleanup(self, before: float) -> int: ...


class ProfileModelUsageRepository(ABC):
    @abstractmethod
    def save_many(self, items: list[ProfileModelUsage]) -> None: ...
    @abstractmethod
    def get_latest(self) -> list[ProfileModelUsage]: ...
    @abstractmethod
    def cleanup(self, before: float) -> int: ...


class SessionRepository(ABC):
    @abstractmethod
    def save_many(self, items: list[Session]) -> None: ...
    @abstractmethod
    def get_latest(self, limit: int = 50) -> list[Session]: ...
    @abstractmethod
    def cleanup(self, before: float) -> int: ...


class SessionLedgerRepository(ABC):
    @abstractmethod
    def save(self, ledger: SessionLedger) -> None: ...
    @abstractmethod
    def get_latest(self) -> SessionLedger | None: ...
    @abstractmethod
    def cleanup(self, before: float) -> int: ...


class LedgerBreakdownRepository(ABC):
    @abstractmethod
    def save_many(self, items: list[LedgerBreakdown]) -> None: ...
    @abstractmethod
    def get_latest(self) -> list[LedgerBreakdown]: ...
    @abstractmethod
    def cleanup(self, before: float) -> int: ...


class KanbanTaskRepository(ABC):
    @abstractmethod
    def save_many(self, items: list[KanbanTask]) -> None: ...
    @abstractmethod
    def get_latest(self) -> list[KanbanTask]: ...
    @abstractmethod
    def cleanup(self, before: float) -> int: ...


class OpenRouterUsageRepository(ABC):
    @abstractmethod
    def save(self, usage: OpenRouterUsage) -> None: ...
    @abstractmethod
    def get_latest(self) -> OpenRouterUsage | None: ...
    @abstractmethod
    def cleanup(self, before: float) -> int: ...


class OpenRouterActivityRepository(ABC):
    @abstractmethod
    def save_many(self, items: list[OpenRouterActivity]) -> None: ...
    @abstractmethod
    def get_latest_batch(self) -> list[OpenRouterActivity]: ...
    @abstractmethod
    def cleanup(self, before: float) -> int: ...


class OpenRouterKeyRepository(ABC):
    @abstractmethod
    def save_many(self, items: list[OpenRouterKey]) -> None: ...
    @abstractmethod
    def get_latest(self) -> list[OpenRouterKey]: ...
    @abstractmethod
    def cleanup(self, before: float) -> int: ...


class DailyCostRepository(ABC):
    @abstractmethod
    def save_many(self, items: list[DailyCost]) -> None: ...
    @abstractmethod
    def get_latest(self) -> list[DailyCost]: ...
    @abstractmethod
    def cleanup(self, before: float) -> int: ...


class WorkServerHealthRepository(ABC):
    @abstractmethod
    def save_many(self, items: list[WorkServerHealth]) -> None: ...
    @abstractmethod
    def get_latest(self) -> list[WorkServerHealth]: ...
    @abstractmethod
    def cleanup(self, before: float) -> int: ...


class WorkDockerRepository(ABC):
    @abstractmethod
    def save_many(self, items: list[WorkDocker]) -> None: ...
    @abstractmethod
    def get_latest(self) -> list[WorkDocker]: ...
    @abstractmethod
    def cleanup(self, before: float) -> int: ...


class WorkNexusRepository(ABC):
    @abstractmethod
    def save_many(self, items: list[WorkNexus]) -> None: ...
    @abstractmethod
    def get_latest(self) -> list[WorkNexus]: ...
    @abstractmethod
    def cleanup(self, before: float) -> int: ...


class WorkJenkinsRepository(ABC):
    @abstractmethod
    def save_many(self, items: list[WorkJenkins]) -> None: ...
    @abstractmethod
    def get_latest(self) -> list[WorkJenkins]: ...
    @abstractmethod
    def cleanup(self, before: float) -> int: ...


class WorkPostgresRepository(ABC):
    @abstractmethod
    def save_many(self, items: list[WorkPostgres]) -> None: ...
    @abstractmethod
    def get_latest(self) -> list[WorkPostgres]: ...
    @abstractmethod
    def cleanup(self, before: float) -> int: ...
