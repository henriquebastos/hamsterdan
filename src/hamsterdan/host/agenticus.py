"""Host-owned deterministic Agenticus composition and operation routing."""

from __future__ import annotations

import json
import sqlite3
import threading
from collections.abc import Iterable, Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass
from enum import StrEnum
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
    AmpExecuteRunner,
    PiNativeRunner,
    UnavailablePiRunner,
)
from hamsterdan.agents.pi import PiWorkspaceProvider

PI_PROVIDER = "anthropic"
PI_MODEL = "claude-sonnet-4-5"
PI_PROFILE = f"pi-native-a2-local-{PI_PROVIDER}-{PI_MODEL}-api-key"
LEGACY_PROFILE = "amp-shared-orb-rollback"

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


class AgentMode(StrEnum):
    AGENTICUS = "agenticus"
    LEGACY_AMP = "legacy-amp"


class AgentCompositionError(RuntimeError):
    """The selected agent route cannot be composed without substitution."""


@dataclass(frozen=True)
class AgentConfig:
    mode: AgentMode
    isolation_required: bool = True

    @classmethod
    def from_environment(cls, environment: dict[str, str]) -> AgentConfig:
        raw_mode = environment.get("HAMSTERDAN_AGENT_MODE")
        try:
            mode = AgentMode(raw_mode)
        except TypeError, ValueError:
            raise AgentCompositionError("HAMSTERDAN_AGENT_MODE must be exactly agenticus or legacy-amp") from None
        raw_isolation = environment.get("HAMSTERDAN_AGENT_ISOLATION_REQUIRED", "true").casefold()
        if raw_isolation not in {"true", "false"}:
            raise AgentCompositionError("HAMSTERDAN_AGENT_ISOLATION_REQUIRED must be true or false")
        return cls(mode, isolation_required=raw_isolation == "true")


@dataclass(frozen=True)
class AgentComposition:
    mode: AgentMode
    profile: str
    snapshot: ResolutionSnapshot | None

    def __post_init__(self) -> None:
        if self.mode is AgentMode.AGENTICUS and (self.profile != PI_PROFILE or self.snapshot is None):
            raise ValueError("Agenticus composition requires the exact qualified profile and snapshot")
        if self.mode is AgentMode.LEGACY_AMP and (self.profile != LEGACY_PROFILE or self.snapshot is not None):
            raise ValueError("legacy Amp composition requires its rollback profile without an Agenticus snapshot")


def resolve_agenticus(
    *,
    descriptors: Iterable[CapabilityDescriptor] = AGENTICUS_DESCRIPTORS,
    enabled: Iterable[DescriptorIdentity] | None = None,
    isolation_required: bool = True,
) -> ResolutionSnapshot:
    """Resolve one host-selected static binding target without provider authority."""

    selected = tuple(descriptors)
    runtime_identities = tuple(item.identity for item in selected if item.identity.kind is DescriptorKind.RUNTIME)
    if AGENT_AS_NET_A5_LOCAL.identity in runtime_identities:
        raise AgentCompositionError("AgentNetRunner A5 topology cannot satisfy the selected Pi native A2 route")
    if isolation_required and AMP_A1.identity in runtime_identities:
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


def compose_agent(config: AgentConfig) -> AgentComposition:
    if config.mode is AgentMode.LEGACY_AMP:
        if config.isolation_required:
            raise AgentCompositionError("legacy Amp rollback cannot satisfy required agent isolation")
        return AgentComposition(config.mode, LEGACY_PROFILE, None)
    if (PI_PROVIDER, PI_MODEL) not in PI_API_KEY_CATALOG:
        raise AgentCompositionError("the exact Pi direct API-key provider and model are not qualified")
    snapshot = resolve_agenticus(isolation_required=config.isolation_required)
    return AgentComposition(config.mode, PI_PROFILE, snapshot)


def select_agent_runner(
    composition: AgentComposition,
    *,
    pi_runtime: PiA2RuntimeHost | None = None,
    pi_workspaces: PiWorkspaceProvider | None = None,
) -> AgentRunner:
    """Select execution only after an exact READY probe; never substitute a fallback."""

    if composition.mode is AgentMode.LEGACY_AMP:
        return AmpExecuteRunner()
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
    mode: AgentMode
    profile: str
    snapshot: ResolutionSnapshot | None
    resolved: bool


class AgentRouteStore:
    """Persist immutable operation routes and fence cross-mode redispatch."""

    def __init__(self, path: Path) -> None:
        path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        self._database = sqlite3.connect(path, check_same_thread=False, isolation_level=None)
        self._lock = threading.RLock()
        self._database.executescript(
            """PRAGMA journal_mode=WAL;
            CREATE TABLE IF NOT EXISTS agent_routes (
                operation TEXT PRIMARY KEY,
                mode TEXT NOT NULL,
                profile TEXT NOT NULL,
                snapshot TEXT,
                resolved INTEGER NOT NULL CHECK (resolved IN (0, 1))
            );
            CREATE TABLE IF NOT EXISTS active_agent_route (
                singleton INTEGER PRIMARY KEY CHECK (singleton = 1),
                mode TEXT NOT NULL,
                profile TEXT NOT NULL,
                snapshot TEXT
            );"""
        )

    def activate(self, composition: AgentComposition, histories: Path) -> None:
        terminal = _terminal_operations(histories)
        encoded = _snapshot_data(composition.snapshot)
        with self._transaction():
            self._settle(terminal)
            blocked = self._database.execute(
                """SELECT 1 FROM agent_routes
                WHERE resolved = 0 AND (mode != ? OR profile != ? OR snapshot IS NOT ?)
                LIMIT 1""",
                (composition.mode.value, composition.profile, encoded),
            ).fetchone()
            if blocked is not None:
                raise AgentCompositionError("agent route change refused while prior-route work is unresolved")
            self._database.execute(
                """INSERT INTO active_agent_route VALUES (1, ?, ?, ?)
                ON CONFLICT(singleton) DO UPDATE SET mode=excluded.mode, profile=excluded.profile,
                snapshot=excluded.snapshot""",
                (composition.mode.value, composition.profile, encoded),
            )

    def claim(self, operation: str, composition: AgentComposition) -> OperationRoute:
        _identifier(operation, "operation")
        encoded = _snapshot_data(composition.snapshot)
        with self._transaction():
            active = self._database.execute(
                "SELECT mode, profile, snapshot FROM active_agent_route WHERE singleton = 1"
            ).fetchone()
            if active != (composition.mode.value, composition.profile, encoded):
                raise AgentCompositionError("agent process route is no longer active")
            self._database.execute(
                "INSERT OR IGNORE INTO agent_routes VALUES (?, ?, ?, ?, 0)",
                (operation, composition.mode.value, composition.profile, encoded),
            )
            route = self._load(operation)
            if route.resolved:
                raise AgentCompositionError("resolved agent work cannot be redispatched")
        if (route.mode, route.profile, _snapshot_data(route.snapshot)) != (
            composition.mode,
            composition.profile,
            encoded,
        ):
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
            "SELECT mode, profile, snapshot, resolved FROM agent_routes WHERE operation = ?", (operation,)
        ).fetchone()
        if row is None:
            raise AgentCompositionError("agent operation route is not persisted")
        return OperationRoute(
            operation,
            AgentMode(row[0]),
            row[1],
            None if row[2] is None else ResolutionSnapshot.from_data(json.loads(row[2])),
            bool(row[3]),
        )


def _snapshot_data(snapshot: ResolutionSnapshot | None) -> str | None:
    if snapshot is None:
        return None
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
