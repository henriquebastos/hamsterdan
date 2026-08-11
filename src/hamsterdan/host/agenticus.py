"""Host-owned deterministic Agenticus composition and operation routing."""

from __future__ import annotations

import json
import sqlite3
import threading
from collections.abc import Callable, Iterable, Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

from petrus.agenticus.catalog.descriptor import CapabilityDescriptor, DescriptorIdentity, DescriptorKind
from petrus.agenticus.catalog.resolution import Catalog, ResolutionRequest, ResolutionSnapshot
from petrus.agenticus.runtime.installation import ProbeDisposition
from petrus.agenticus.runtime.pi import (
    PI_API_KEY_CATALOG,
    PI_COLLOCATED_HANDS,
    PI_CONNECTION_CAPABILITIES,
    PI_CONTINUATION_CAPABILITIES,
    PI_LOCAL_TERRITORY,
    PI_PROGRAM_CAPABILITIES,
)
from petrus.agenticus.runtime.pi_a2_host import PiA2RuntimeHost
from petrus.agenticus.runtime.profiles import AGENT_AS_NET_A5_LOCAL, AMP_A1, PI_NATIVE_A2_LOCAL
from petrus.impetus.history import ActivityCompleted, ActivityFailed, ActivityRequested
from petrus.impetus.history.codec import decode_record

from hamsterdan.agents import (
    AgentRunner,
    CodingRequest,
    CodingResult,
    ConversationRequest,
    ConversationResult,
    PiNativeRunner,
    ReviewRequest,
    ReviewResult,
    UnavailablePiRunner,
)
from hamsterdan.agents.pi import PiWorkspaceProvider

PI_PROVIDER = "anthropic"
PI_MODEL = "claude-sonnet-4-5"
PI_PROFILE = f"pi-native-a2-local-{PI_PROVIDER}-{PI_MODEL}-api-key"

HOST_FENCED_EFFECT = CapabilityDescriptor(
    DescriptorIdentity(DescriptorKind.EFFECT, "hamsterdan.host-fenced", 1),
    frozenset({"effect.host-fenced"}),
)
AGENTICUS_DESCRIPTORS = (
    PI_CONNECTION_CAPABILITIES,
    PI_PROGRAM_CAPABILITIES,
    PI_NATIVE_A2_LOCAL,
    PI_COLLOCATED_HANDS,
    PI_LOCAL_TERRITORY,
    PI_CONTINUATION_CAPABILITIES,
    HOST_FENCED_EFFECT,
)


class AgentCompositionError(RuntimeError):
    """The selected agent route cannot be composed without substitution."""


@dataclass(frozen=True)
class AgentComposition:
    profile: str
    snapshot: ResolutionSnapshot

    def __post_init__(self) -> None:
        if self.profile != PI_PROFILE:
            raise ValueError("Agenticus composition requires the exact qualified profile and snapshot")


def resolve_agenticus(
    *,
    descriptors: Iterable[CapabilityDescriptor] = AGENTICUS_DESCRIPTORS,
    enabled: Iterable[DescriptorIdentity] | None = None,
) -> ResolutionSnapshot:
    """Resolve one host-selected static binding target without provider authority."""

    selected = tuple(descriptors)
    runtime_identities = tuple(item.identity for item in selected if item.identity.kind is DescriptorKind.RUNTIME)
    if AGENT_AS_NET_A5_LOCAL.identity in runtime_identities:
        raise AgentCompositionError("AgentNetRunner A5 topology cannot satisfy the selected Pi native A2 route")
    if AMP_A1.identity in runtime_identities:
        raise AgentCompositionError("Amp A1 provider-managed territory is not agent isolation")
    catalog = Catalog()
    for descriptor in selected:
        catalog.register(descriptor)
    identities = tuple(descriptor.identity for descriptor in selected) if enabled is None else tuple(enabled)
    for identity in identities:
        catalog.enable(identity)
    resolution = catalog.resolve(ResolutionRequest(tuple(descriptor.identity for descriptor in selected)))
    if resolution.snapshot is None:
        issues = sorted({issue.code for result in resolution.incompatibilities for issue in result.issues})
        raise AgentCompositionError("Agenticus profile is unavailable: " + ",".join(issues))
    return resolution.snapshot


def compose_agent(environment: Mapping[str, str] | None = None) -> AgentComposition:
    """Resolve Hamsterdan's sole isolated Pi composition."""

    removed = {"HAMSTERDAN_AGENT_MODE", "HAMSTERDAN_AGENT_ISOLATION_REQUIRED"}
    configured = removed.intersection(environment or {})
    if configured:
        raise AgentCompositionError(
            f"{', '.join(sorted(configured))} is no longer supported; isolated Agenticus Pi is the only agent route"
        )
    if (PI_PROVIDER, PI_MODEL) not in PI_API_KEY_CATALOG:
        raise AgentCompositionError("the exact Pi direct API-key provider and model are not qualified")
    return AgentComposition(PI_PROFILE, resolve_agenticus())


def compose_agent_runner(
    *,
    pi_runtime: PiA2RuntimeHost | None = None,
    pi_workspaces: PiWorkspaceProvider | None = None,
) -> AgentRunner:
    """Compose Pi execution only after an exact READY probe; never substitute a fallback."""

    if pi_runtime is None or pi_workspaces is None:
        return UnavailablePiRunner()
    try:
        probe = pi_runtime.probe()
    except Exception:  # noqa: BLE001 - a probe failure selects only the fail-closed runner
        return UnavailablePiRunner()
    installation = probe.installation
    required = {"runtime.cancel", "runtime.continue", "runtime.harness-owned", "runtime.local"}
    if (
        probe.disposition is not ProbeDisposition.READY
        or probe.runtime != PI_NATIVE_A2_LOCAL.identity
        or installation is None
        or installation.runtime != PI_NATIVE_A2_LOCAL.identity
        or installation.adapter_contract_version != 1
        or not required <= installation.capabilities
    ):
        return UnavailablePiRunner()
    return PiNativeRunner(pi_runtime, pi_workspaces)


@dataclass(frozen=True)
class OperationRoute:
    operation: str
    profile: str
    snapshot: ResolutionSnapshot
    resolved: bool


class AgentRouteStore:
    """Persist immutable operation composition across Attempts and restart."""

    def __init__(self, path: Path) -> None:
        path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        self._database = sqlite3.connect(path, check_same_thread=False, isolation_level=None)
        self._lock = threading.RLock()
        try:
            self._database.execute("PRAGMA journal_mode=WAL")
            self._initialize()
        except BaseException:
            self._database.close()
            raise

    def _initialize(self) -> None:
        columns = {row[1] for row in self._database.execute("PRAGMA table_info(agent_routes)")}
        self._legacy_schema = "mode" in columns
        if self._legacy_schema:
            return
        self._database.executescript(
            """
            CREATE TABLE IF NOT EXISTS agent_routes (
                operation TEXT PRIMARY KEY,
                profile TEXT NOT NULL,
                snapshot TEXT NOT NULL,
                resolved INTEGER NOT NULL CHECK (resolved IN (0, 1))
            );
            CREATE TABLE IF NOT EXISTS active_agent_route (
                singleton INTEGER PRIMARY KEY CHECK (singleton = 1),
                profile TEXT NOT NULL,
                snapshot TEXT NOT NULL
            );"""
        )

    def _migrate_legacy_schema(self) -> None:
        """Preserve Agenticus custody while deleting the retired Amp route."""

        unresolved = self._database.execute(
            "SELECT 1 FROM agent_routes WHERE mode != 'agenticus' AND resolved = 0 LIMIT 1"
        ).fetchone()
        if unresolved is not None:
            raise AgentCompositionError("unresolved legacy Amp work cannot be resumed")
        incomplete = self._database.execute(
            "SELECT 1 FROM agent_routes WHERE mode = 'agenticus' AND resolved = 0 AND snapshot IS NULL LIMIT 1"
        ).fetchone()
        if incomplete is not None:
            raise AgentCompositionError("unresolved Agenticus work lacks reconstructible composition")
        statements = (
            """CREATE TABLE agent_routes_v2 (
                    operation TEXT PRIMARY KEY,
                    profile TEXT NOT NULL,
                    snapshot TEXT NOT NULL,
                    resolved INTEGER NOT NULL CHECK (resolved IN (0, 1))
            )""",
            """INSERT INTO agent_routes_v2
                    SELECT operation, profile, snapshot, resolved FROM agent_routes
                    WHERE mode = 'agenticus' AND snapshot IS NOT NULL""",
            """CREATE TABLE active_agent_route_v2 (
                    singleton INTEGER PRIMARY KEY CHECK (singleton = 1),
                    profile TEXT NOT NULL,
                    snapshot TEXT NOT NULL
            )""",
            """INSERT INTO active_agent_route_v2
                    SELECT singleton, profile, snapshot FROM active_agent_route
                    WHERE mode = 'agenticus' AND snapshot IS NOT NULL""",
            "DROP TABLE active_agent_route",
            "DROP TABLE agent_routes",
            "ALTER TABLE agent_routes_v2 RENAME TO agent_routes",
            "ALTER TABLE active_agent_route_v2 RENAME TO active_agent_route",
        )
        for statement in statements:
            self._database.execute(statement)
        self._legacy_schema = False

    def activate(self, composition: AgentComposition, histories: Path) -> None:
        terminal = _terminal_operations(histories)
        encoded = _snapshot_data(composition.snapshot)
        with self._transaction():
            self._settle(terminal)
            if self._legacy_schema:
                self._migrate_legacy_schema()
            blocked = self._database.execute(
                """SELECT 1 FROM agent_routes
                WHERE resolved = 0 AND (profile != ? OR snapshot IS NOT ?)
                LIMIT 1""",
                (composition.profile, encoded),
            ).fetchone()
            if blocked is not None:
                raise AgentCompositionError("agent route change refused while prior-route work is unresolved")
            self._database.execute(
                """INSERT INTO active_agent_route VALUES (1, ?, ?)
                ON CONFLICT(singleton) DO UPDATE SET profile=excluded.profile, snapshot=excluded.snapshot""",
                (composition.profile, encoded),
            )

    def claim(self, operation: str, composition: AgentComposition) -> OperationRoute:
        _identifier(operation, "operation")
        encoded = _snapshot_data(composition.snapshot)
        with self._transaction():
            active = self._database.execute(
                "SELECT profile, snapshot FROM active_agent_route WHERE singleton = 1"
            ).fetchone()
            if active != (composition.profile, encoded):
                raise AgentCompositionError("agent process route is no longer active")
            self._database.execute(
                "INSERT OR IGNORE INTO agent_routes VALUES (?, ?, ?, 0)",
                (operation, composition.profile, encoded),
            )
            route = self._load(operation)
            if route.resolved:
                raise AgentCompositionError("resolved agent work cannot be redispatched")
        if (route.profile, _snapshot_data(route.snapshot)) != (composition.profile, encoded):
            raise AgentCompositionError("operation is already fenced to a different agent route")
        return route

    def settle(self, operations: Iterable[str]) -> None:
        with self._transaction():
            self._settle(operations)

    def close(self) -> None:
        with self._lock:
            self._database.close()

    @contextmanager
    def _transaction(self) -> Iterator[None]:
        with self._lock:
            self._database.execute("BEGIN IMMEDIATE")
            try:
                yield
            except BaseException:
                self._database.rollback()
                raise
            else:
                self._database.commit()

    def _settle(self, operations: Iterable[str]) -> None:
        values = tuple((_identifier(operation, "operation"),) for operation in set(operations))
        self._database.executemany("UPDATE agent_routes SET resolved = 1 WHERE operation = ?", values)

    def _load(self, operation: str) -> OperationRoute:
        row = self._database.execute(
            "SELECT profile, snapshot, resolved FROM agent_routes WHERE operation = ?", (operation,)
        ).fetchone()
        if row is None:
            raise AgentCompositionError("agent operation route is not persisted")
        return OperationRoute(
            operation,
            row[0],
            ResolutionSnapshot.from_data(json.loads(row[1])),
            bool(row[2]),
        )


class RoutedAgentRunner:
    """Claim logical operation ownership before delegating one explicit Attempt."""

    def __init__(
        self,
        runner: AgentRunner,
        routes: AgentRouteStore,
        composition: AgentComposition,
        *,
        before_call: Callable[[str, str, int], None] | None = None,
    ) -> None:
        self._runner, self._routes, self._composition = runner, routes, composition
        self._before_call = before_call

    def review(
        self,
        repository_url: str,
        request: ReviewRequest,
        *,
        operation: str,
        attempt: int,
        is_current: Callable[[], bool] | None = None,
    ) -> ReviewResult:
        self._claim("review", operation, attempt)
        return self._runner.review(repository_url, request, operation=operation, attempt=attempt, is_current=is_current)

    def converse(
        self,
        repository_url: str,
        request: ConversationRequest,
        *,
        operation: str,
        attempt: int,
        is_current: Callable[[], bool] | None = None,
    ) -> ConversationResult:
        self._claim("conversation", operation, attempt)
        return self._runner.converse(
            repository_url, request, operation=operation, attempt=attempt, is_current=is_current
        )

    def code(
        self,
        repository_url: str,
        request: CodingRequest,
        *,
        operation: str,
        attempt: int,
        is_current: Callable[[], bool] | None = None,
    ) -> CodingResult:
        self._claim(request.kind, operation, attempt)
        return self._runner.code(repository_url, request, operation=operation, attempt=attempt, is_current=is_current)

    def _claim(self, kind: str, operation: str, attempt: int) -> None:
        if type(attempt) is not int or attempt < 1:
            raise AgentCompositionError("agent attempt must be a positive integer")
        self._routes.claim(operation, self._composition)
        if self._before_call is not None:
            self._before_call(kind, operation, attempt)


def _snapshot_data(snapshot: ResolutionSnapshot) -> str:
    return json.dumps(snapshot.to_data(), sort_keys=True, separators=(",", ":"))


def _identifier(value: object, name: str) -> str:
    if (
        not isinstance(value, str)
        or not value
        or len(value.encode()) > 1024
        or not value.isascii()
        or not value.isprintable()
    ):
        raise ValueError(f"agent route {name} is malformed")
    return value


def _terminal_operations(histories: Path) -> set[str]:
    operations: set[str] = set()
    for path in histories.glob("*/*/*/history.jsonl") if histories.is_dir() else ():
        if path.stat().st_size > 16 * 1024 * 1024:
            raise AgentCompositionError("agent route repair History exceeds its bound")
        requests: dict[int, tuple[str, str]] = {}
        terminal: dict[int, str] = {}
        try:
            for line in path.read_text(encoding="utf-8").splitlines():
                payload = json.loads(line)
                if not isinstance(payload, Mapping):
                    raise TypeError("History record must be an object")
                record = decode_record(payload)
                if isinstance(record, ActivityRequested):
                    work = (
                        record.input.get("work", record.input.get("command"))
                        if isinstance(record.input, dict)
                        else None
                    )
                    operation = work.get("operation") if isinstance(work, dict) else None
                    transition = str(record.transition)
                    if transition in {"execute.review", "execute.conversation", "execute.repair", "execute.change"}:
                        if not isinstance(operation, str) or record.occurrence in requests:
                            raise ValueError("agent Activity request is ambiguous")
                        requests[record.occurrence] = transition, operation
                elif isinstance(record, (ActivityCompleted, ActivityFailed)):
                    if record.occurrence in terminal:
                        raise ValueError("terminal Activity occurrence is ambiguous")
                    terminal[record.occurrence] = str(record.transition)
        except OSError, UnicodeError, json.JSONDecodeError, TypeError, ValueError, AttributeError:
            raise AgentCompositionError("agent route repair History is malformed") from None
        for occurrence in terminal.keys() & requests.keys():
            transition, operation = requests[occurrence]
            if terminal[occurrence] != transition:
                raise AgentCompositionError("agent route repair History has a mismatched terminal Activity")
            operations.add(operation)
    return operations
