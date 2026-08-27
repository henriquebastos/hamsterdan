from __future__ import annotations

import ast
import sys
from dataclasses import replace
from pathlib import Path
from typing import Any, cast

import pytest

HERE = Path(__file__).resolve().parent
SPIKES = HERE.parent
LOCAL_SPIKES = {
    "agents": SPIKES / "10-agents-simulation" / "agents_simulation.py",
    "github": SPIKES / "10-github-simulation" / "github_simulation.py",
    "host": SPIKES / "10-host-simulation" / "host_simulation.py",
    "readiness": SPIKES / "10-readiness-simulation" / "readiness_simulation.py",
    "workflow": SPIKES / "10-workflow-simulation" / "workflow_simulation.py",
}
sys.path[:0] = [str(HERE), str(SPIKES / "09-simulation-runtime")]

from composition import (
    CAUSAL_VERTICAL_BLOCKER,
    COMPOSITION_BUDGET,
    LOCAL_MODULES,
    RESOURCE_LIMITS,
    CompositionRouteError,
    HamsterdanCoMounting,
    build_modules,
    run_co_mounting_counterexample,
    run_workflow_failure_proof,
)
from runtime import Timeline


class TestNamespacedCoMountingSurface:
    """Co-mounting commands, observations, and faults retain strict module ownership."""

    def test_namespaces_and_signed_webhooks_fail_before_state_change(self) -> None:
        whole = HamsterdanCoMounting.open()

        with pytest.raises(CompositionRouteError) as unknown_command:
            whole.command("invented.command", {})
        with pytest.raises(CompositionRouteError) as unknown_observation:
            whole.observe("invented.state")
        with pytest.raises(CompositionRouteError) as unknown_fault:
            whole.fault("invented.response_lost", {})
        with pytest.raises(CompositionRouteError) as bad_signature:
            whole.command("composition.signed_webhook", whole.webhook(signature="sha256:" + "0" * 64))

        assert unknown_command.value.args == ("unknown command namespace 'invented'",)
        assert unknown_observation.value.args == ("unknown observation namespace 'invented'",)
        assert unknown_fault.value.args == ("unknown fault 'invented.response_lost'",)
        assert bad_signature.value.args == ("signed webhook signature does not match its detached body",)
        assert whole.observe("composition.state")["webhooks"] == []

    def test_budget_is_the_exact_union_of_every_mounted_resource(self) -> None:
        modules = build_modules()
        actual = {name for module in modules for name in module.resource_usage(None)}

        assert tuple(module.name for module in modules if module.name != "composition") == LOCAL_MODULES
        assert actual == set(RESOURCE_LIMITS)

        missing = dict(RESOURCE_LIMITS)
        missing.pop("workflow.commands")
        with pytest.raises(ValueError) as incomplete:
            Timeline.open(build_modules(), replace(COMPOSITION_BUDGET, resources=missing))

        assert incomplete.value.args == (
            "module resource usage must exactly match the budget; missing=[], additional=['workflow.commands']",
        )

    def test_exact_handoff_replay_survives_later_readiness_enrichment(self) -> None:
        whole = HamsterdanCoMounting.open()
        webhook = whole.webhook()
        whole.command("composition.signed_webhook", webhook)
        operation = f"push:comment:501:{webhook['head']}:i{webhook['incarnation']}"
        payload = {
            "delivery": webhook["delivery"],
            "instruction": "rename the config key",
            "operation": operation,
            "workflow_operation": "rerun:tests-red:7:1",
        }

        first_agent = cast(dict[str, Any], whole.command("composition.handoff.agent", payload))
        first_readiness = whole.command("composition.handoff.readiness", {"operation": operation})
        repeated_agent = cast(dict[str, Any], whole.command("composition.handoff.agent", payload))
        repeated_readiness = whole.command("composition.handoff.readiness", {"operation": operation})

        assert repeated_agent["submission"] == first_agent["submission"]
        assert repeated_agent["terminal"] == first_agent["terminal"]
        assert repeated_readiness == first_readiness


class TestHamsterdanCoMounting:
    """Five local scenarios co-mount and recover without proving one causal vertical."""

    def test_counterexample_composes_local_checkers_and_recorded_interleavings(self) -> None:
        proof = run_co_mounting_counterexample()

        assert proof.replay.exact
        assert proof.report.local_passed == {
            "agents": True,
            "github": True,
            "host": True,
            "readiness": True,
            "workflow": True,
        }
        assert proof.report.cross_violations == ()
        assert proof.report.causal_blockers == (CAUSAL_VERTICAL_BLOCKER,)
        commands = {
            (operation["request"]["module"], operation["request"]["name"]): operation["request"]["payload"]
            for operation in proof.artifact.operations
            if operation["kind"] == "command"
        }
        rerun = commands[("workflow", "terminal.rerun")]
        handoff = commands[("composition", "handoff.agent")]
        mutation = commands[("readiness", "request_mutation")]
        assert handoff["workflow_operation"] == rerun["operation"] == "rerun:tests-red:7:1"
        assert handoff["operation"] == mutation["op_key"]
        assert handoff["instruction"] == mutation["instruction"] == "rename the config key"
        assert mutation["op_key"] != rerun["operation"]
        assert proof.metrics["signed_webhooks"] == 1
        assert proof.metrics["accepted_git_effects"] == 1
        assert proof.metrics["readiness_agent_calls"] == 1
        assert proof.metrics["agent_runtime_starts"] == 1
        assert proof.metrics["agent_deliveries"] == 1
        assert proof.metrics["lookup_recoveries"] == 1
        assert proof.metrics["final_generation"] == 2
        assert proof.metrics["crash_phases"] == ["executed"]
        assert proof.metrics["interleaving_draws"] > 0
        assert len(proof.metrics["interleaved_modules"]) > 1
        assert proof.metrics["workflow_terminal"] == "RerunLanded"


class TestCheckerOwnershipAndLocalization:
    """Local failures reduce locally; composition-owned observations replay while co-mounted."""

    def test_workflow_failure_reduces_to_the_unchanged_workflow_simulation(self) -> None:
        proof = run_workflow_failure_proof()

        assert proof.replay.exact
        assert proof.report.scope == "workflow"
        assert proof.report.local_passed == {
            "agents": True,
            "github": True,
            "host": True,
            "readiness": True,
            "workflow": False,
        }
        assert proof.report.cross_violations == ()
        assert proof.reduced_artifact.modules == ("workflow",)
        assert proof.reduced_replay.exact
        assert proof.reduced_violations == proof.report.local_violations["workflow"]

    def test_authority_mismatch_is_cross_state_and_replays_at_co_mounting_scope(self) -> None:
        proof = run_co_mounting_counterexample(corrupt_handoff_authority=True)

        assert proof.replay.exact
        assert all(proof.report.local_passed.values())
        assert proof.report.scope == "co_mounting"
        assert proof.report.reducible_to is None
        assert proof.report.causal_blockers == (CAUSAL_VERTICAL_BLOCKER,)
        assert proof.report.cross_violations == (
            "readiness authority differs from the signed webhook and GitHub authority",
        )


class TestLocalSimulationIndependence:
    """Accepted local simulations do not import one another to enable composition."""

    def test_only_the_composition_owner_imports_all_five_local_implementations(self) -> None:
        local_names = {path.stem for path in LOCAL_SPIKES.values()}
        edges = {}
        for owner, path in LOCAL_SPIKES.items():
            tree = ast.parse(path.read_text())
            imports = {
                alias.name for node in ast.walk(tree) if isinstance(node, ast.Import) for alias in node.names
            } | {node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom) and node.module is not None}
            cross_imports = sorted(name for name in imports if name in local_names)
            if cross_imports:
                edges[owner] = cross_imports

        assert edges == {}
