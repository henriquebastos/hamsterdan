from __future__ import annotations

import ast
import sys
from dataclasses import replace
from pathlib import Path

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
    COMPOSITION_BUDGET,
    LOCAL_MODULES,
    PUBLICATION_OPERATION,
    RESOURCE_LIMITS,
    CompositionRouteError,
    HamsterdanCoMounting,
    build_modules,
    run_causal_composition,
    run_workflow_failure_proof,
)
from runtime import Timeline


class TestNamespacedCompositionSurface:
    """Composition keeps routing explicit and budgets the exact mounted resource union."""

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


class TestCausalComposition:
    """One workflow-declared mutation and one delivered agent result cause the published effect."""

    def test_real_workflow_result_flows_through_all_five_local_checkers(self) -> None:
        proof = run_causal_composition()

        assert proof.replay.exact
        assert proof.report.local_passed == {
            "agents": True,
            "github": True,
            "host": True,
            "readiness": True,
            "workflow": True,
        }
        assert proof.report.cross_violations == ()
        assert proof.report.causal_blockers == ()
        assert proof.metrics["operation"] == PUBLICATION_OPERATION
        assert proof.metrics["workflow_work"] == proof.metrics["readiness_work"]
        assert proof.metrics["delivered_request"] == proof.metrics["readiness_request"]
        assert proof.metrics["delivered_result_digest"] == proof.metrics["publication_coding_result_digest"]
        assert proof.metrics["accepted_git_effects"] == 1
        assert proof.metrics["provider_call_kinds"] == [
            "reconcile",
            "claim",
            "agent",
            "claim",
            "claim",
            "publish_accepted",
            "reconcile",
        ]
        assert proof.metrics["readiness_agent_calls"] == 1
        assert proof.metrics["agent_runtime_starts"] == 1
        assert proof.metrics["agent_deliveries"] == 1
        assert proof.metrics["lookup_recoveries"] == 1
        assert proof.metrics["final_generation"] == 2
        assert proof.metrics["crash_phases"] == ["executed"]
        assert proof.metrics["workflow_terminal"] == "Pushed"
        assert proof.metrics["workflow_expected_head"] == proof.metrics["publication_result_head"]
        assert "git_gate" not in proof.metrics["final_held_activities"]
        assert set(proof.metrics["held_activities_at_request"]) > {"git_gate"}

    def test_publication_is_sensitive_to_the_exact_delivered_coding_result(self) -> None:
        first = run_causal_composition(proposed_commit_message="Apply requested change")
        second = run_causal_composition(proposed_commit_message="Apply bounded rename")

        assert first.metrics["workflow_work"] == second.metrics["workflow_work"]
        assert first.metrics["delivered_request"] == second.metrics["delivered_request"]
        assert first.metrics["publication_payload_digest"] == second.metrics["publication_payload_digest"]
        assert first.metrics["delivered_result_digest"] != second.metrics["delivered_result_digest"]
        assert first.metrics["publication_result_head"] != second.metrics["publication_result_head"]
        assert first.metrics["publication_coding_result_digest"] != second.metrics["publication_coding_result_digest"]
        assert first.replay.exact and second.replay.exact

    def test_cross_checker_rejects_composition_substitution_of_workflow_instruction(self) -> None:
        proof = run_causal_composition(
            substitute_work_instruction="composition substituted this instruction",
        )

        assert proof.replay.exact
        assert all(proof.report.local_passed.values())
        assert proof.report.causal_blockers == ()
        assert proof.report.scope == "co_mounting"
        assert proof.report.cross_violations == ("composition handoff altered the real workflow-declared MutWork",)
        assert proof.metrics["workflow_work"]["instruction"] == "rename the config key"
        assert proof.metrics["readiness_work"]["instruction"] == "composition substituted this instruction"
        assert proof.metrics["workflow_terminal"] == "Pushed"
        assert proof.metrics["accepted_git_effects"] == 1


class TestCheckerOwnershipAndLocalization:
    """Local failures reduce locally; the one value-flow rule remains composition-owned."""

    def test_workflow_failure_reduces_to_the_unchanged_s3_workflow_simulation(self) -> None:
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

    def test_authority_mismatch_is_cross_state_and_replays_at_composition_scope(self) -> None:
        proof = run_causal_composition(corrupt_handoff_authority=True)

        assert proof.replay.exact
        assert all(proof.report.local_passed.values())
        assert proof.report.scope == "co_mounting"
        assert proof.report.reducible_to is None
        assert proof.report.causal_blockers == ()
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
