from __future__ import annotations

import json
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

from hamsterdan.agents import AmpExecuteRunner, PiNativeRunner, UnavailablePiRunner
from hamsterdan.host.agenticus import (
    AGENTICUS_DESCRIPTORS,
    HOST_FENCED_EFFECT,
    AgentComposition,
    AgentCompositionError,
    AgentConfig,
    AgentMode,
    AgentRouteStore,
    compose_agent,
    resolve_agenticus,
    select_agent_runner,
)


def test_exact_pi_native_a2_local_api_key_profile_resolves_immutable_snapshot() -> None:
    composition = compose_agent(AgentConfig(AgentMode.AGENTICUS))

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


def test_amp_a1_and_legacy_amp_are_not_isolation() -> None:
    descriptors = tuple(
        AMP_A1 if item.identity.kind is DescriptorKind.RUNTIME else item for item in AGENTICUS_DESCRIPTORS
    )
    with pytest.raises(AgentCompositionError, match="not agent isolation"):
        resolve_agenticus(descriptors=descriptors)
    with pytest.raises(AgentCompositionError, match="cannot satisfy required agent isolation"):
        compose_agent(AgentConfig(AgentMode.LEGACY_AMP, isolation_required=True))


def test_agent_net_runner_a5_topology_is_explicitly_rejected() -> None:
    descriptors = tuple(
        AGENT_AS_NET_A5_LOCAL if item.identity.kind is DescriptorKind.RUNTIME else item
        for item in AGENTICUS_DESCRIPTORS
    )
    with pytest.raises(AgentCompositionError, match="A5 topology"):
        resolve_agenticus(descriptors=descriptors)


def test_modes_are_explicit_and_legacy_never_implicit_fallback() -> None:
    with pytest.raises(AgentCompositionError, match="must be exactly"):
        AgentConfig.from_environment({})
    legacy = compose_agent(
        AgentConfig.from_environment(
            {
                "HAMSTERDAN_AGENT_MODE": "legacy-amp",
                "HAMSTERDAN_AGENT_ISOLATION_REQUIRED": "false",
            }
        )
    )
    assert legacy.mode is AgentMode.LEGACY_AMP and legacy.snapshot is None


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
    runner = select_agent_runner(
        compose_agent(AgentConfig(AgentMode.AGENTICUS)),
        pi_runtime=runtime,
    )
    assert isinstance(runner, PiNativeRunner)
    assert runtime.probes == 1 and runtime.starts == 0


@pytest.mark.parametrize("disposition", [ProbeDisposition.NOT_INSTALLED, ProbeDisposition.UNAVAILABLE])
def test_not_ready_probe_fails_closed_without_legacy_fallback(disposition: ProbeDisposition) -> None:
    runtime = ProbeRuntime(probe_result(disposition))
    runner = select_agent_runner(
        compose_agent(AgentConfig(AgentMode.AGENTICUS)),
        pi_runtime=runtime,
    )
    assert isinstance(runner, UnavailablePiRunner)
    assert not isinstance(runner, AmpExecuteRunner)
    assert runtime.probes == 1 and runtime.starts == 0


def test_legacy_amp_is_selected_only_by_explicit_legacy_composition() -> None:
    legacy = compose_agent(AgentConfig(AgentMode.LEGACY_AMP, isolation_required=False))
    assert isinstance(select_agent_runner(legacy), AmpExecuteRunner)


def test_snapshot_persists_and_same_route_is_reconstructed_before_redispatch(tmp_path: Path) -> None:
    composition = compose_agent(AgentConfig(AgentMode.AGENTICUS))
    store = AgentRouteStore(tmp_path / "agent-routes.sqlite3")
    store.activate(composition, tmp_path / "applications")
    claimed = store.claim("review:one", composition)
    store.close()

    reopened = AgentRouteStore(tmp_path / "agent-routes.sqlite3")
    reopened.activate(composition, tmp_path / "applications")
    reconstructed = reopened.reconstruct_before_redispatch("review:one", composition)
    assert reconstructed == claimed
    assert composition.snapshot is not None
    changed = ResolutionSnapshot(composition.snapshot.catalog_revision + 1, composition.snapshot.descriptors)
    different = AgentComposition(composition.mode, composition.profile, changed)
    with pytest.raises(AgentCompositionError, match="route"):
        reopened.reconstruct_before_redispatch("review:one", different)


def test_rollback_refuses_while_agenticus_work_is_unresolved(tmp_path: Path) -> None:
    store = AgentRouteStore(tmp_path / "agent-routes.sqlite3")
    agenticus = compose_agent(AgentConfig(AgentMode.AGENTICUS))
    legacy = compose_agent(AgentConfig(AgentMode.LEGACY_AMP, isolation_required=False))
    store.activate(agenticus, tmp_path / "applications")
    store.claim("code:one", agenticus)
    with pytest.raises(AgentCompositionError, match="prior-route work is unresolved"):
        store.activate(legacy, tmp_path / "applications")
    store.resolve("code:one")
    store.activate(legacy, tmp_path / "applications")


def test_old_process_cannot_claim_after_an_atomic_route_cutover(tmp_path: Path) -> None:
    agenticus = compose_agent(AgentConfig(AgentMode.AGENTICUS))
    legacy = compose_agent(AgentConfig(AgentMode.LEGACY_AMP, isolation_required=False))
    old_process = AgentRouteStore(tmp_path / "agent-routes.sqlite3")
    old_process.activate(agenticus, tmp_path / "applications")
    new_process = AgentRouteStore(tmp_path / "agent-routes.sqlite3")
    new_process.activate(legacy, tmp_path / "applications")

    with pytest.raises(AgentCompositionError, match="no longer active"):
        old_process.claim("review:late", agenticus)


def test_terminal_history_repairs_crash_gap_before_rollback(tmp_path: Path) -> None:
    agenticus = compose_agent(AgentConfig(AgentMode.AGENTICUS))
    legacy = compose_agent(AgentConfig(AgentMode.LEGACY_AMP, isolation_required=False))
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
    reopened.activate(legacy, tmp_path / "applications")


def test_history_repair_refuses_a_mismatched_terminal_transition(tmp_path: Path) -> None:
    agenticus = compose_agent(AgentConfig(AgentMode.AGENTICUS))
    legacy = compose_agent(AgentConfig(AgentMode.LEGACY_AMP, isolation_required=False))
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
        store.activate(legacy, tmp_path / "applications")


def test_host_composition_imports_only_public_defining_modules() -> None:
    source = Path("src/hamsterdan/host/agenticus.py").read_text()
    assert "petrus.agenticus.catalog.descriptor" in source
    assert "petrus.agenticus.catalog.resolution" in source
    assert "petrus.agenticus.runtime.pi" in source
    assert "petrus.agenticus.runtime.profiles" in source
    assert "petrus.agenticus import" not in source
    assert "petrus.motus import" not in source
