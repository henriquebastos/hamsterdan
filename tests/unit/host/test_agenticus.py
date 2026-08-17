from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest
from petrus.agenticus.catalog.descriptor import CapabilityDescriptor, DescriptorKind
from petrus.agenticus.catalog.resolution import ResolutionSnapshot
from petrus.agenticus.runtime.installation import (
    InstalledComponent,
    ProbeDisposition,
    ProbeIssue,
    RuntimeInstallation,
    RuntimeProbeResult,
)
from petrus.agenticus.runtime.pi import PI_API_KEY_CATALOG
from petrus.agenticus.runtime.profiles import AGENT_AS_NET_A5_LOCAL, AMP_A1, PI_NATIVE_A2_LOCAL
from petrus.impetus.history import ActivityCompleted, ActivityRequested
from petrus.impetus.history.codec import encode_record
from petrus.impetus.petrinet import NetPath
from petrus.motus.activity import ExecutionPolicy

from hamsterdan.agents import PiNativeRunner, UnavailablePiRunner
from hamsterdan.host import __main__ as host_main
from hamsterdan.host.__main__ import _close_owned_resources, _compose_agent_runtime
from hamsterdan.host.agenticus import (
    AGENTICUS_DESCRIPTORS,
    HOST_FENCED_EFFECT,
    AgentComposition,
    AgentCompositionError,
    AgentRouteStore,
    RoutedAgentRunner,
    compose_agent,
    compose_agent_runner,
    resolve_agenticus,
)
from hamsterdan.host.pi_a2 import PiA2InstallationConfig


def test_exact_pi_native_a2_local_api_key_profile_resolves_immutable_snapshot() -> None:
    composition = compose_agent()

    assert composition.profile == "pi-native-a2-local-anthropic-claude-sonnet-4-5-api-key"
    assert ("anthropic", "claude-sonnet-4-5") in PI_API_KEY_CATALOG
    assert composition.snapshot is not None
    assert {item.identity.name for item in composition.snapshot.descriptors} == {
        "pi.compatible-api-key",
        "pi.harness-owned",
        "pi.native.a2.local",
        "pi.collocated",
        "motus.local",
        "pi.native",
        "hamsterdan.host-fenced",
    }
    assert composition.snapshot == type(composition.snapshot).from_data(composition.snapshot.to_data())


@pytest.mark.parametrize(
    ("provider", "model", "profile"),
    [
        ("anthropic", "claude-sonnet-4-5", "pi-native-a2-local-anthropic-claude-sonnet-4-5-api-key"),
        ("openai", "gpt-5.6-sol", "pi-native-a2-local-openai-gpt-5.6-sol-api-key"),
        (
            "openrouter",
            "anthropic/claude-sonnet-4.5",
            "pi-native-a2-local-openrouter-anthropic/claude-sonnet-4.5-api-key",
        ),
    ],
)
def test_agent_route_profile_uses_the_exact_qualified_installation_selection(
    provider: str, model: str, profile: str
) -> None:
    assert compose_agent(provider=provider, model=model).profile == profile


def test_unqualified_agent_provider_model_pair_fails_closed() -> None:
    with pytest.raises(AgentCompositionError, match="not qualified"):
        compose_agent(provider="openai", model="claude-sonnet-4-5")


def test_supplied_environment_cannot_trigger_an_implicit_provider_selection() -> None:
    with pytest.raises(AgentCompositionError, match="explicit provider and model"):
        compose_agent({})


def test_missing_disabled_and_incompatible_profiles_refuse_deterministically() -> None:
    without_hands = tuple(item for item in AGENTICUS_DESCRIPTORS if item.identity.kind is not DescriptorKind.HANDS)
    with pytest.raises(AgentCompositionError, match="missing-selection"):
        resolve_agenticus(descriptors=without_hands)

    enabled = tuple(item.identity for item in AGENTICUS_DESCRIPTORS if item is not HOST_FENCED_EFFECT)
    with pytest.raises(AgentCompositionError, match="not-enabled"):
        resolve_agenticus(enabled=enabled)

    incompatible_effect = CapabilityDescriptor(HOST_FENCED_EFFECT.identity, frozenset())
    descriptors = tuple(incompatible_effect if item is HOST_FENCED_EFFECT else item for item in AGENTICUS_DESCRIPTORS)
    with pytest.raises(AgentCompositionError, match="missing-capability"):
        resolve_agenticus(descriptors=descriptors)


def test_amp_a1_is_not_isolation() -> None:
    descriptors = tuple(
        AMP_A1 if item.identity.kind is DescriptorKind.RUNTIME else item for item in AGENTICUS_DESCRIPTORS
    )
    with pytest.raises(AgentCompositionError, match="not agent isolation"):
        resolve_agenticus(descriptors=descriptors)


def test_agent_net_runner_a5_topology_is_explicitly_rejected() -> None:
    descriptors = tuple(
        AGENT_AS_NET_A5_LOCAL if item.identity.kind is DescriptorKind.RUNTIME else item
        for item in AGENTICUS_DESCRIPTORS
    )
    with pytest.raises(AgentCompositionError, match="A5 topology"):
        resolve_agenticus(descriptors=descriptors)


@pytest.mark.parametrize("name", ["HAMSTERDAN_AGENT_MODE", "HAMSTERDAN_AGENT_ISOLATION_REQUIRED"])
def test_removed_agent_route_settings_fail_clearly(name: str) -> None:
    with pytest.raises(AgentCompositionError, match="no longer supported"):
        compose_agent({name: "legacy-amp"})


class ProbeRuntime:
    def __init__(self, result: RuntimeProbeResult):
        self.result = result
        self.probes = 0
        self.starts = 0

    def probe(self):
        self.probes += 1
        return self.result

    def start(self, invocation):
        self.starts += 1
        raise AssertionError("runner selection must not start provider work")


def probe_result(disposition: ProbeDisposition, *, runtime=PI_NATIVE_A2_LOCAL.identity) -> RuntimeProbeResult:
    if disposition is ProbeDisposition.READY:
        installation = RuntimeInstallation(
            runtime,
            1,
            (InstalledComponent("pi", "1", "qualified:test"),),
            "linux",
            "x86_64",
            frozenset({"runtime.cancel", "runtime.continue", "runtime.harness-owned", "runtime.local"}),
        )
        return RuntimeProbeResult(runtime, disposition, installation)
    return RuntimeProbeResult(runtime, disposition, issues=(ProbeIssue("runtime-unavailable", "pi"),))


def test_exact_ready_probe_selects_pi_without_starting_authority() -> None:
    runtime = ProbeRuntime(probe_result(ProbeDisposition.READY))
    runner = compose_agent_runner(
        pi_runtime=runtime,
        pi_workspaces=object(),  # type: ignore[arg-type]
    )
    assert isinstance(runner, PiNativeRunner)
    assert runtime.probes == 1 and runtime.starts == 0


@pytest.mark.parametrize("disposition", [ProbeDisposition.NOT_INSTALLED, ProbeDisposition.UNAVAILABLE])
def test_not_ready_probe_fails_closed(disposition: ProbeDisposition) -> None:
    runtime = ProbeRuntime(probe_result(disposition))
    runner = compose_agent_runner(
        pi_runtime=runtime,
        pi_workspaces=object(),  # type: ignore[arg-type]
    )
    assert isinstance(runner, UnavailablePiRunner)
    assert runtime.probes == 1 and runtime.starts == 0


def test_production_runtime_constructs_workspace_before_owned_runtime(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    key = tmp_path / "authority"
    key.write_bytes(b"synthetic-direct-authority")
    key.chmod(0o600)
    environment = {
        "HAMSTERDAN_PI_PROVIDER": "anthropic",
        "HAMSTERDAN_PI_MODEL": "claude-sonnet-4-5",
        "HAMSTERDAN_PI_API_KEY_FILE": str(key),
        "HAMSTERDAN_PI_CLI_PATH": str(tmp_path / "cli"),
        "HAMSTERDAN_PI_NODE_PATH": str(tmp_path / "node"),
        "HAMSTERDAN_PI_PACKAGE_ROOT": str(tmp_path / "package"),
    }
    installation = PiA2InstallationConfig.from_environment(environment)
    runtimes = 0

    def compose(*args: object) -> object:
        nonlocal runtimes
        runtimes += 1
        return object()

    monkeypatch.setattr(host_main, "compose_owned_pi_a2", compose)
    monkeypatch.setattr(
        host_main,
        "GitPiWorkspaceProvider",
        lambda path: (_ for _ in ()).throw(ValueError("synthetic workspace failure")),
    )

    with pytest.raises(ValueError, match="synthetic workspace failure"):
        _compose_agent_runtime(tmp_path / "state", installation)
    assert runtimes == 0


def test_startup_cleanup_attempts_every_independently_owned_resource() -> None:
    closed: list[str] = []

    class Resource:
        def __init__(self, name: str, fail: bool = False) -> None:
            self.name, self.fail = name, fail

        def close(self) -> None:
            closed.append(self.name)
            if self.fail:
                raise RuntimeError("synthetic")

    with pytest.raises(RuntimeError, match="cleanup is unverified"):
        _close_owned_resources(None, Resource("runtime", True), Resource("routes"))  # type: ignore[arg-type]
    assert closed == ["runtime", "routes"]


def test_snapshot_persists_and_claim_reconstructs_same_route_after_restart(tmp_path: Path) -> None:
    composition = compose_agent()
    store = AgentRouteStore(tmp_path / "agent-routes.sqlite3")
    store.activate(composition, tmp_path / "applications")
    claimed = store.claim("review:one", composition)
    store.close()

    reopened = AgentRouteStore(tmp_path / "agent-routes.sqlite3")
    reopened.activate(composition, tmp_path / "applications")
    reconstructed = reopened.claim("review:one", composition)
    assert reconstructed == claimed
    assert composition.snapshot is not None
    changed = ResolutionSnapshot(composition.snapshot.catalog_revision + 1, composition.snapshot.descriptors)
    different = AgentComposition(composition.provider, composition.model, composition.profile, changed)
    with pytest.raises(AgentCompositionError, match="route"):
        reopened.claim("review:one", different)


def legacy_route_database(path: Path, composition: AgentComposition) -> tuple[sqlite3.Connection, str]:
    snapshot = json.dumps(composition.snapshot.to_data(), sort_keys=True, separators=(",", ":"))
    database = sqlite3.connect(path)
    database.executescript(
        """CREATE TABLE agent_routes (
            operation TEXT PRIMARY KEY, mode TEXT NOT NULL, profile TEXT NOT NULL,
            snapshot TEXT, resolved INTEGER NOT NULL
        );
        CREATE TABLE active_agent_route (
            singleton INTEGER PRIMARY KEY, mode TEXT NOT NULL, profile TEXT NOT NULL, snapshot TEXT
        );"""
    )
    return database, snapshot


def test_legacy_schema_preserves_only_agenticus_operation_custody(tmp_path: Path) -> None:
    path = tmp_path / "agent-routes.sqlite3"
    composition = compose_agent()
    database, snapshot = legacy_route_database(path, composition)
    database.execute(
        "INSERT INTO agent_routes VALUES (?, 'agenticus', ?, ?, 0)",
        ("review:existing", composition.profile, snapshot),
    )
    database.execute("INSERT INTO agent_routes VALUES ('review:old', 'legacy-amp', 'old', NULL, 1)")
    database.execute(
        "INSERT INTO active_agent_route VALUES (1, 'agenticus', ?, ?)",
        (composition.profile, snapshot),
    )
    database.commit()
    database.close()

    store = AgentRouteStore(path)
    store.activate(composition, tmp_path / "applications")

    assert store.claim("review:existing", composition).operation == "review:existing"
    columns = {row[1] for row in store._database.execute("PRAGMA table_info(agent_routes)")}
    assert columns == {"operation", "profile", "snapshot", "resolved"}
    assert store._database.execute("SELECT 1 FROM agent_routes WHERE operation = 'review:old'").fetchone() is None


def test_terminal_history_repairs_legacy_crash_gap_before_migration(tmp_path: Path) -> None:
    path = tmp_path / "agent-routes.sqlite3"
    composition = compose_agent()
    database, _ = legacy_route_database(path, composition)
    database.execute("INSERT INTO agent_routes VALUES ('review:terminal', 'legacy-amp', 'old', NULL, 0)")
    database.execute("INSERT INTO active_agent_route VALUES (1, 'legacy-amp', 'old', NULL)")
    database.commit()
    database.close()
    history = tmp_path / "applications/1/2/3/history.jsonl"
    history.parent.mkdir(parents=True)
    requested = ActivityRequested(
        NetPath("execute.review"),
        activity="review",
        input={"work": {"operation": "review:terminal"}},
        policy=ExecutionPolicy(1, 30),
        correlation="review:terminal",
        idempotency="review:terminal",
        occurrence=1,
    )
    completed = ActivityCompleted(NetPath("execute.review"), {}, occurrence=1)
    history.write_text("\n".join(json.dumps(encode_record(record)) for record in (requested, completed)) + "\n")

    store = AgentRouteStore(path)
    store.activate(composition, tmp_path / "applications")

    assert store._database.execute("SELECT 1 FROM agent_routes").fetchone() is None


@pytest.mark.parametrize("mode", ["legacy-amp", "agenticus"])
def test_unreconstructible_unresolved_legacy_schema_is_refused_atomically(tmp_path: Path, mode: str) -> None:
    path = tmp_path / "agent-routes.sqlite3"
    composition = compose_agent()
    database, _ = legacy_route_database(path, composition)
    database.execute("INSERT INTO agent_routes VALUES ('review:blocked', ?, 'old', NULL, 0)", (mode,))
    database.execute("INSERT INTO active_agent_route VALUES (1, ?, 'old', NULL)", (mode,))
    database.commit()
    database.close()

    store = AgentRouteStore(path)
    with pytest.raises(AgentCompositionError, match="cannot be resumed|lacks reconstructible composition"):
        store.activate(composition, tmp_path / "applications")
    store.close()

    unchanged = sqlite3.connect(path)
    columns = {row[1] for row in unchanged.execute("PRAGMA table_info(agent_routes)")}
    assert "mode" in columns
    assert unchanged.execute("SELECT mode, resolved FROM agent_routes").fetchone() == (mode, 0)
    unchanged.close()


def test_routed_runner_claims_and_forwards_each_explicit_attempt_without_changing_identity(tmp_path: Path) -> None:
    composition = compose_agent()
    store = AgentRouteStore(tmp_path / "agent-routes.sqlite3")
    store.activate(composition, tmp_path / "applications")
    calls: list[tuple[str, int]] = []

    class Runner:
        def review(self, repository, request, *, operation, attempt, is_current=None):
            calls.append((operation, attempt))
            return object()

    subject = RoutedAgentRunner(Runner(), store, composition)  # type: ignore[arg-type]
    for attempt in (1, 2):
        subject.review("repository", object(), operation="review:one", attempt=attempt)  # type: ignore[arg-type]

    assert calls == [("review:one", 1), ("review:one", 2)]
    assert store.claim("review:one", composition).operation == "review:one"


def test_routed_runner_claims_before_fault(tmp_path: Path) -> None:
    agenticus = compose_agent()
    store = AgentRouteStore(tmp_path / "agent-routes.sqlite3")
    store.activate(agenticus, tmp_path / "applications")
    calls: list[str] = []

    class Runner:
        def review(self, *args, **kwargs):
            calls.append("provider")

    def fail(kind: str, operation: str, attempt: int) -> None:
        assert (kind, operation, attempt) == ("review", "review:fault", 1)
        raise RuntimeError("qualified fault")

    subject = RoutedAgentRunner(Runner(), store, agenticus, before_call=fail)  # type: ignore[arg-type]
    with pytest.raises(RuntimeError, match="qualified fault"):
        subject.review("repository", object(), operation="review:fault", attempt=1)  # type: ignore[arg-type]

    assert calls == []


def test_old_process_cannot_claim_after_an_atomic_composition_change(tmp_path: Path) -> None:
    agenticus = compose_agent()
    changed = AgentComposition(
        agenticus.provider,
        agenticus.model,
        agenticus.profile,
        ResolutionSnapshot(agenticus.snapshot.catalog_revision + 1, agenticus.snapshot.descriptors),
    )
    old_process = AgentRouteStore(tmp_path / "agent-routes.sqlite3")
    old_process.activate(agenticus, tmp_path / "applications")
    new_process = AgentRouteStore(tmp_path / "agent-routes.sqlite3")
    new_process.activate(changed, tmp_path / "applications")

    with pytest.raises(AgentCompositionError, match="no longer active"):
        old_process.claim("review:late", agenticus)


def test_terminal_history_repairs_crash_gap_before_composition_change(tmp_path: Path) -> None:
    agenticus = compose_agent()
    store = AgentRouteStore(tmp_path / "agent-routes.sqlite3")
    store.activate(agenticus, tmp_path / "applications")
    store.claim("review:terminal", agenticus)
    store.close()
    history = tmp_path / "applications/1/2/3/history.jsonl"
    history.parent.mkdir(parents=True)
    request = ActivityRequested(
        NetPath("execute.review"),
        activity="review",
        input={"work": {"operation": "review:terminal"}},
        policy=ExecutionPolicy(1, 30),
        correlation="review:terminal",
        idempotency="review:terminal",
        occurrence=1,
    )
    completed = ActivityCompleted(NetPath("execute.review"), {}, occurrence=1)
    history.write_text("\n".join(json.dumps(encode_record(record)) for record in (request, completed)) + "\n")

    reopened = AgentRouteStore(tmp_path / "agent-routes.sqlite3")
    reopened.activate(agenticus, tmp_path / "applications")


def test_v5_review_terminal_history_repairs_the_global_agent_route(tmp_path: Path) -> None:
    agenticus = compose_agent()
    operation = "review:github:1:2:pr:3:" + "a" * 40 + ":i1"
    store = AgentRouteStore(tmp_path / "agent-routes.sqlite3")
    store.activate(agenticus, tmp_path / "applications")
    store.claim(operation, agenticus)
    store.close()
    history = tmp_path / "applications/1/2/3/history.jsonl"
    history.parent.mkdir(parents=True)
    request = ActivityRequested(
        NetPath("review.agent"),
        activity="review_agent",
        input={"work": {"operation": operation}},
        policy=ExecutionPolicy(1, 300),
        correlation=operation,
        idempotency=operation,
        occurrence=1,
    )
    completed = ActivityCompleted(NetPath("review.agent"), {"$variant": "RoundUnable"}, occurrence=1)
    history.write_text("\n".join(json.dumps(encode_record(record)) for record in (request, completed)) + "\n")

    reopened = AgentRouteStore(tmp_path / "agent-routes.sqlite3")
    reopened.activate(agenticus, tmp_path / "applications")

    assert reopened._database.execute(
        "SELECT resolved FROM agent_routes WHERE operation = ?", (operation,)
    ).fetchone() == (1,)


def test_v5_deferred_review_history_keeps_the_global_agent_route_recoverable(tmp_path: Path) -> None:
    agenticus = compose_agent()
    operation = "review:github:1:2:pr:3:" + "a" * 40 + ":i1"
    store = AgentRouteStore(tmp_path / "agent-routes.sqlite3")
    store.activate(agenticus, tmp_path / "applications")
    store.claim(operation, agenticus)
    store.close()
    history = tmp_path / "applications/1/2/3/history.jsonl"
    history.parent.mkdir(parents=True)
    request = ActivityRequested(
        NetPath("review.agent"),
        activity="review_agent",
        input={"work": {"operation": operation}},
        policy=ExecutionPolicy(1, 300),
        correlation=operation,
        idempotency=operation,
        occurrence=1,
    )
    completed = ActivityCompleted(NetPath("review.agent"), {"$variant": "RoundDeferred"}, occurrence=1)
    history.write_text("\n".join(json.dumps(encode_record(record)) for record in (request, completed)) + "\n")

    reopened = AgentRouteStore(tmp_path / "agent-routes.sqlite3")
    reopened.activate(agenticus, tmp_path / "applications")

    assert reopened.claim(operation, agenticus).resolved is False


@pytest.mark.parametrize("variant", ["Pushed", "MovedM", "DeclinedM"])
def test_v5_mutation_known_terminal_repairs_the_global_agent_route(tmp_path: Path, variant: str) -> None:
    agenticus = compose_agent()
    op_key = "push:comment:9:" + "a" * 40 + ":i1"
    operation = f"mutation:owner/repo:pr:3:{op_key}"
    store = AgentRouteStore(tmp_path / "agent-routes.sqlite3")
    store.activate(agenticus, tmp_path / "applications")
    store.claim(operation, agenticus)
    store.close()
    root = tmp_path / "applications/1/2/3"
    root.mkdir(parents=True)
    (root / "binding.json").write_text(
        json.dumps(
            {
                "instance_id": "github:1:2:pr:3",
                "repository": "owner/repo",
                "pull_request": 3,
                "topology": "v5",
            }
        )
    )
    request = ActivityRequested(
        NetPath("mut.git_gate"),
        activity="git_gate",
        input={"work": {"op_key": op_key}},
        policy=ExecutionPolicy(1, 300),
        correlation=op_key,
        idempotency=op_key,
        occurrence=1,
    )
    completed = ActivityCompleted(NetPath("mut.git_gate"), {"$variant": variant}, occurrence=1)
    (root / "history.jsonl").write_text(
        "\n".join(json.dumps(encode_record(record)) for record in (request, completed)) + "\n"
    )

    reopened = AgentRouteStore(tmp_path / "agent-routes.sqlite3")
    reopened.activate(agenticus, tmp_path / "applications")

    assert reopened._database.execute(
        "SELECT resolved FROM agent_routes WHERE operation = ?", (operation,)
    ).fetchone() == (1,)


def test_v5_mutation_fault_keeps_the_agent_route_recoverable(tmp_path: Path) -> None:
    agenticus = compose_agent()
    op_key = "push:comment:9:" + "a" * 40 + ":i1"
    operation = f"mutation:owner/repo:pr:3:{op_key}"
    store = AgentRouteStore(tmp_path / "agent-routes.sqlite3")
    store.activate(agenticus, tmp_path / "applications")
    store.claim(operation, agenticus)
    store.close()
    root = tmp_path / "applications/1/2/3"
    root.mkdir(parents=True)
    (root / "binding.json").write_text(
        json.dumps({"instance_id": "github:1:2:pr:3", "repository": "owner/repo", "pull_request": 3})
    )
    request = ActivityRequested(
        NetPath("mut.git_gate"),
        activity="git_gate",
        input={"work": {"op_key": op_key}},
        policy=ExecutionPolicy(1, 300),
        correlation=op_key,
        idempotency=op_key,
        occurrence=1,
    )
    completed = ActivityCompleted(NetPath("mut.git_gate"), {"$variant": "FaultM"}, occurrence=1)
    (root / "history.jsonl").write_text(
        "\n".join(json.dumps(encode_record(record)) for record in (request, completed)) + "\n"
    )

    reopened = AgentRouteStore(tmp_path / "agent-routes.sqlite3")
    reopened.activate(agenticus, tmp_path / "applications")

    assert reopened.claim(operation, agenticus).resolved is False


def test_history_repair_refuses_a_mismatched_terminal_transition(tmp_path: Path) -> None:
    agenticus = compose_agent()
    store = AgentRouteStore(tmp_path / "agent-routes.sqlite3")
    store.activate(agenticus, tmp_path / "applications")
    store.claim("review:mismatched", agenticus)
    request = ActivityRequested(
        NetPath("execute.review"),
        activity="review",
        input={"work": {"operation": "review:mismatched"}},
        policy=ExecutionPolicy(1, 30),
        correlation="review:mismatched",
        idempotency="review:mismatched",
        occurrence=1,
    )
    completed = ActivityCompleted(NetPath("execute.change"), {}, occurrence=1)
    history = tmp_path / "applications/1/2/3/history.jsonl"
    history.parent.mkdir(parents=True)
    history.write_text("\n".join(json.dumps(encode_record(record)) for record in (request, completed)) + "\n")

    with pytest.raises(AgentCompositionError, match="mismatched terminal"):
        store.activate(agenticus, tmp_path / "applications")


def test_host_composition_imports_only_public_defining_modules() -> None:
    source = Path("src/hamsterdan/host/agenticus.py").read_text()
    assert "petrus.agenticus.catalog.descriptor" in source
    assert "petrus.agenticus.catalog.resolution" in source
    assert "petrus.agenticus.runtime.pi" in source
    assert "petrus.agenticus.runtime.profiles" in source
    assert "petrus.agenticus import" not in source
    assert "petrus.motus import" not in source
