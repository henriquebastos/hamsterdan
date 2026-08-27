"""Causal whole-Hamsterdan composition over the accepted S9/S10 simulations."""

from __future__ import annotations

import hmac
import json
import sys
from dataclasses import asdict, dataclass, field
from hashlib import sha256
from pathlib import Path
from typing import Any, cast

HERE = Path(__file__).resolve().parent
SPIKES = HERE.parent
sys.path[:0] = [
    str(SPIKES / "09-simulation-runtime"),
    str(SPIKES / "03-workflow-shape"),
    str(SPIKES / "10-workflow-simulation"),
    str(SPIKES / "10-readiness-simulation"),
    str(SPIKES / "10-github-simulation"),
    str(SPIKES / "10-agents-simulation"),
    str(SPIKES / "10-host-simulation"),
]

from agents_simulation import AgentsChecker, AgentsSimulation
from github_simulation import GitHubChecker, GitHubSimulation, github_fault
from host_simulation import HostArtifactChecker, HostCheckFailed, HostSimulation
from readiness_simulation import ReadinessModule, arm_readiness_fault
from runtime import (
    ActionRef,
    Artifact,
    Budget,
    LeafOffered,
    ReplayResult,
    StepCompleted,
    Timeline,
    Waiting,
    replay,
)
from workflow_simulation import V5MutationWorkflowSimulation, WorkflowSimulation

from hamsterdan.agents.protocol import AgentProtocolError, CodingRequest, CodingResult
from hamsterdan.contracts.readiness_v5 import MutWork
from hamsterdan.host.git_publish import payload_digest
from hamsterdan.host.v5.mutation import V5MutationGate

LOCAL_MODULES = ("workflow", "readiness", "github", "agents", "host")
MOUNTED_MODULES = ("composition", *LOCAL_MODULES)

HEAD = "a" * 40
BASE = "b" * 40
CORRUPT_HEAD = "c" * 40
POLICY = "policy-1"
INCARNATION = 1
DELIVERY = "delivery-501"
ROUTE = "installation:44:repository:31"
SUBJECT = "owner:repo:pr:7"
WORKFLOW_OPERATION = "rerun:tests-red:7:1"
PUBLICATION_OPERATION = f"push:comment:501:{HEAD}:i{INCARNATION}"
SIGNING_KEY = b"experiment-11-only-signing-key"

RESOURCE_LIMITS = {
    "agents.operations": 16,
    "agents.pending": 16,
    "agents.receiver_terminals": 16,
    "agents.runtime_terminals": 16,
    "agents.terminal_declarations": 16,
    "composition.handoffs": 8,
    "composition.webhooks": 8,
    "github.authorities": 16,
    "github.calls": 128,
    "github.effects": 32,
    "github.pending": 32,
    "github.reads": 32,
    "github.retained_bytes": 262_144,
    "host.cleanup_errors": 8,
    "host.instances": 8,
    "host.loaded": 8,
    "host.readiness_operations": 64,
    "host.routes": 8,
    "host.runnable": 8,
    "readiness.calls": 32,
    "readiness.claims": 8,
    "readiness.publications": 8,
    "readiness.requests": 8,
    "readiness.terminals": 8,
    "workflow.commands": 8,
    "workflow.history_records": 256,
    "workflow.pending_activities": 16,
}

COMPOSITION_BUDGET = Budget(
    operations=1_024,
    owner_steps=256,
    eligible_actions=64,
    leaf_calls=256,
    choice_draws=256,
    active_faults=32,
    generations=8,
    logical_time_us=1_000,
    journal_entries=4_096,
    artifact_bytes=4_000_000,
    resources=RESOURCE_LIMITS,
)

WORKFLOW_BUDGET = Budget(
    operations=256,
    owner_steps=64,
    eligible_actions=1,
    leaf_calls=64,
    choice_draws=1,
    active_faults=4,
    generations=4,
    logical_time_us=0,
    journal_entries=1_024,
    artifact_bytes=1_000_000,
    resources={
        "workflow.commands": 8,
        "workflow.history_records": 128,
        "workflow.pending_activities": 1,
    },
)

WEBHOOK_FIELDS = {
    "action",
    "base",
    "delivery",
    "event",
    "head",
    "incarnation",
    "policy",
    "route",
    "signature",
    "subject",
}
WEBHOOK_BODY_FIELDS = WEBHOOK_FIELDS - {"signature"}
_WORK_FIELDS = set(MutWork.__dataclass_fields__)


class CompositionRouteError(RuntimeError):
    pass


class DeliveredAgentsCodingRunner:
    """Adapt one exact delivered agents terminal to readiness' typed runner port."""

    def __init__(self, agents: AgentsSimulation) -> None:
        self.agents = agents

    def code(
        self,
        repository_url: str,
        request: CodingRequest,
        *,
        operation: str,
        attempt: int,
        is_current: Any = None,
    ) -> CodingResult:
        if is_current is None or not is_current():
            raise AgentProtocolError("coding authority moved", canceled=True)
        delivered = self.agents.delivered(operation, attempt)
        if delivered.kind != "coding":
            raise CompositionRouteError("delivered agent execution is not a coding operation")
        if delivered.repository_url != repository_url:
            raise CompositionRouteError("delivered agent repository differs from the readiness request")
        if delivered.operation != operation or delivered.attempt != attempt:
            raise CompositionRouteError("delivered agent identity differs from the readiness request")
        if not isinstance(delivered.request, CodingRequest) or delivered.request != request:
            raise CompositionRouteError("delivered agent request differs from the readiness request")
        if not isinstance(delivered.result, CodingResult):
            raise CompositionRouteError("delivered agent terminal is not a CodingResult")
        return delivered.result


@dataclass
class _CompositionStore:
    webhooks: dict[str, dict[str, Any]] = field(default_factory=dict)
    handoffs: dict[str, dict[str, Any]] = field(default_factory=dict)


class CompositionModule:
    name = "composition"

    def __init__(self, signing_key: bytes = SIGNING_KEY) -> None:
        self.signing_key = signing_key
        self.store = _CompositionStore()

    def open(self, _context: object) -> _CompositionGeneration:
        return _CompositionGeneration(self.store, self.signing_key)

    def drop(self, _generation: _CompositionGeneration) -> None:
        pass

    def close(self, _generation: _CompositionGeneration) -> None:
        pass

    def resource_usage(self, _generation: _CompositionGeneration | None) -> dict[str, int]:
        return {
            "composition.handoffs": len(self.store.handoffs),
            "composition.webhooks": len(self.store.webhooks),
        }


class _CompositionGeneration:
    def __init__(self, store: _CompositionStore, signing_key: bytes) -> None:
        self.store = store
        self.signing_key = signing_key

    def command(self, name: str, payload: object, context: Any) -> object:
        commands = {
            "webhook.accept": self._accept_webhook,
            "handoff.agent": self._handoff_agent,
            "handoff.readiness": self._handoff_readiness,
        }
        try:
            command = commands[name]
        except KeyError:
            raise CompositionRouteError(f"unknown composition command {name!r}") from None
        return command(payload, context)

    def observe(self, name: str, payload: object, _context: object) -> object:
        if name != "state":
            raise CompositionRouteError(f"unknown composition observation {name!r}")
        _exact(payload, set(), "composition state observation", allow_none=True)
        return {
            "handoffs": [dict(value) for _, value in sorted(self.store.handoffs.items())],
            "webhooks": [dict(value) for _, value in sorted(self.store.webhooks.items())],
        }

    def eligible_actions(self, _context: object) -> tuple[ActionRef, ...]:
        return ()

    async def step(self, _action: ActionRef, _context: Any) -> object:
        raise CompositionRouteError("composition owns no scheduled action")

    def _accept_webhook(self, payload: object, _context: Any) -> object:
        values = _exact(payload, WEBHOOK_FIELDS, "signed webhook")
        body = {name: values[name] for name in sorted(WEBHOOK_BODY_FIELDS)}
        _validate_webhook_body(body)
        expected = _signature(body, self.signing_key)
        if not hmac.compare_digest(cast(str, values["signature"]), expected):
            raise CompositionRouteError("signed webhook signature does not match its detached body")
        delivery = cast(str, body["delivery"])
        previous = self.store.webhooks.get(delivery)
        if previous is not None and previous != body:
            raise CompositionRouteError(f"webhook delivery {delivery!r} conflicts with its retained body")
        if previous is None:
            self.store.webhooks[delivery] = body
        return {"accepted": previous is None, "delivery": delivery}

    def _handoff_agent(self, payload: object, _context: Any) -> object:
        values = _exact(
            payload,
            {"delivery", "proposed_commit_message", "workflow_occurrence", "work"},
            "agent handoff",
        )
        delivery = _text(values["delivery"], "delivery")
        webhook = self._webhook(delivery)
        work = MutWork(**_exact(values["work"], _WORK_FIELDS, "workflow mutation work"))
        request = V5MutationGate.request("owner/repo", 7, work)
        occurrence = values["workflow_occurrence"]
        if type(occurrence) is not int or occurrence < 0:
            raise CompositionRouteError("workflow_occurrence must be a non-negative integer")
        expected_authority = _authority(webhook)
        if (work.head, work.base, work.policy, work.incarnation) != (
            expected_authority["head"],
            expected_authority["base"],
            expected_authority["policy"],
            expected_authority["incarnation"],
        ):
            raise CompositionRouteError("workflow mutation work differs from the signed webhook authority")
        message = _text(values["proposed_commit_message"], "proposed_commit_message")
        operation = work.op_key
        agent_operation = f"mutation:owner/repo:pr:7:{operation}"
        submission = {
            "kind": "coding",
            "repository_url": "https://example.test/owner/repo.git",
            "operation": agent_operation,
            "attempt": 1,
            "request": asdict(request),
        }
        terminal = {
            "operation": agent_operation,
            "attempt": 1,
            "result": {
                "base": request.base,
                "changed_files": ["a"],
                "diff": "diff --git a/a b/a\n",
                "epoch": request.epoch,
                "head": request.head,
                "kind": request.kind,
                "proposed_commit_message": message,
                "pull_request": request.pull_request,
                "ref": request.ref,
                "repository": request.repository,
                "reproduction_status": "not_attempted",
                "status": "changed",
                "validation_evidence": [{"command": "synthetic", "result": "passed"}],
            },
        }
        handoff = {
            "agent_operation": agent_operation,
            "authority": expected_authority,
            "delivery": delivery,
            "operation": operation,
            "request": asdict(request),
            "proposed_commit_message": message,
            "work": work.dump(),
            "workflow_occurrence": occurrence,
        }
        previous = self.store.handoffs.get(operation)
        if previous is not None:
            if any(previous.get(name) != value for name, value in handoff.items()):
                raise CompositionRouteError(f"handoff operation {operation!r} conflicts with its retained value")
            handoff = previous
        else:
            self.store.handoffs[operation] = handoff
        return {"handoff": handoff, "submission": submission, "terminal": terminal}

    def _handoff_readiness(self, payload: object, context: Any) -> object:
        values = _exact(payload, {"operation"}, "readiness handoff")
        operation = _text(values["operation"], "operation")
        try:
            handoff = self.store.handoffs[operation]
        except KeyError:
            raise CompositionRouteError(f"agent handoff {operation!r} must exist before readiness routing") from None
        authority = dict(handoff["authority"])
        faults = context.faults("handoff.authority")
        if len(faults) > 1:
            raise CompositionRouteError("handoff.authority matched more than one occurrence")
        if faults:
            fault = _exact(faults[0].payload, {"head"}, "handoff.authority fault")
            authority["head"] = _commit(fault["head"], "fault head")
        handoff["readiness_authority"] = authority
        handoff["readiness_work"] = dict(handoff["work"])
        return {"authority": authority, "work": handoff["readiness_work"]}

    def _webhook(self, delivery: str) -> dict[str, Any]:
        try:
            return self.store.webhooks[delivery]
        except KeyError:
            raise CompositionRouteError(f"signed webhook {delivery!r} must be accepted before handoff") from None


@dataclass(frozen=True)
class CoMountingReport:
    local_passed: dict[str, bool]
    local_violations: dict[str, tuple[str, ...]]
    cross_violations: tuple[str, ...]
    causal_blockers: tuple[str, ...]
    scope: str
    reducible_to: str | None


@dataclass(frozen=True)
class CompositionEvidence:
    artifact: Artifact
    replay: ReplayResult
    report: CoMountingReport
    metrics: dict[str, Any]


@dataclass(frozen=True)
class WorkflowFailureProof:
    artifact: Artifact
    replay: ReplayResult
    report: CoMountingReport
    reduced_artifact: Artifact
    reduced_replay: ReplayResult
    reduced_violations: tuple[str, ...]


class HamsterdanCoMounting:
    """Route typed values among independently owned local simulations."""

    def __init__(self, timeline: Timeline, modules: tuple[Any, ...]) -> None:
        self.timeline = timeline
        self.modules = {module.name: module for module in modules}

    @classmethod
    def open(cls, *, seed: int = 31, module_factory: Any = None) -> HamsterdanCoMounting:
        modules = build_modules() if module_factory is None else module_factory()
        return cls(Timeline.open(modules, COMPOSITION_BUDGET, seed=seed), modules)

    def webhook(self, *, signature: str | None = None) -> dict[str, object]:
        body: dict[str, object] = {
            "action": "created",
            "base": BASE,
            "delivery": DELIVERY,
            "event": "issue_comment",
            "head": HEAD,
            "incarnation": INCARNATION,
            "policy": POLICY,
            "route": ROUTE,
            "subject": SUBJECT,
        }
        return {**body, "signature": signature or _signature(body, SIGNING_KEY)}

    def command(self, name: str, payload: object) -> object:
        if name == "composition.signed_webhook":
            return self._accept_signed_webhook_and_project(payload)
        module, local_name = _route(name, "command")
        if module not in MOUNTED_MODULES:
            raise CompositionRouteError(f"unknown command namespace {module!r}")
        return self.timeline.command(module, local_name, payload)

    def observe(self, name: str, payload: object = None) -> Any:
        module, local_name = _route(name, "observation")
        if module not in MOUNTED_MODULES:
            raise CompositionRouteError(f"unknown observation namespace {module!r}")
        return self.timeline.observe(module, local_name, payload).value

    def fault(self, name: str, payload: object, *, occurrence: int = 1) -> object:
        if name == "readiness.git_response_lost":
            return arm_readiness_fault(
                self.timeline,
                "git_response_lost",
                payload,
                occurrence=occurrence,
            )
        if name in {"github.read.response", "github.publication.acceptance"}:
            return github_fault(self.timeline, name.removeprefix("github."), payload, occurrence=occurrence)
        if name in {"agents.runtime.loss.after_terminal", "agents.terminal.delivery.response_lost"}:
            values = _exact(payload, {"execution_id"}, f"{name} fault")
            return self.timeline.fault(
                "agents",
                name.removeprefix("agents."),
                occurrence=occurrence,
                payload=values,
            )
        if name in {"host.readiness.progress.unavailable", "host.readiness.progress.after_commit"}:
            values = _exact(payload, {"subject"}, f"{name} fault")
            host = cast(HostSimulation, self.modules["host"])
            local = name.removeprefix("host.")
            fault_payload = {"subject": _text(values["subject"], "subject")}
            if local.endswith("after_commit"):
                fault_payload["response_lost"] = True
            return host.arm_fault(
                self.timeline,
                local,
                payload=fault_payload,
                occurrence=occurrence,
            )
        if name == "workflow.terminal.rerun.corrupt_operation":
            values = _exact(payload, {"replacement"}, f"{name} fault")
            return self.timeline.fault(
                "workflow",
                "terminal.rerun.corrupt_operation",
                occurrence=occurrence,
                payload=values,
            )
        if name == "composition.handoff.authority":
            values = _exact(payload, {"head"}, f"{name} fault")
            _commit(values["head"], "fault head")
            return self.timeline.fault(
                "composition",
                "handoff.authority",
                occurrence=occurrence,
                payload=values,
            )
        raise CompositionRouteError(f"unknown fault {name!r}")

    def route_workflow_mutation(
        self,
        *,
        proposed_commit_message: str,
        substitute_work_instruction: str | None = None,
    ) -> str:
        workflow = cast(dict[str, Any], self.observe("workflow.state"))
        pending = cast(dict[str, Any] | None, workflow["pending"])
        if pending is None or pending["activity"] != "git_gate":
            raise CompositionRouteError("real workflow must expose one pending git_gate before agent handoff")
        work = dict(cast(dict[str, Any], pending["work"]))
        if substitute_work_instruction is not None:
            work["instruction"] = substitute_work_instruction
        routed = cast(
            dict[str, Any],
            self.timeline.command(
                "composition",
                "handoff.agent",
                {
                    "delivery": DELIVERY,
                    "proposed_commit_message": proposed_commit_message,
                    "workflow_occurrence": pending["occurrence"],
                    "work": work,
                },
            ),
        )
        self.timeline.command("agents", "submit", routed["submission"])
        self.timeline.command("agents", "terminal", routed["terminal"])
        return cast(str, routed["handoff"]["agent_operation"])

    def route_delivered_mutation_to_readiness(self, *, operation: str = PUBLICATION_OPERATION) -> None:
        state = cast(dict[str, Any], self.observe("composition.state"))
        [handoff] = [item for item in state["handoffs"] if item["operation"] == operation]
        agent_operation = cast(str, handoff["agent_operation"])
        agent = cast(
            dict[str, Any],
            self.observe(
                "agents.operation",
                {"operation": agent_operation, "attempt": 1},
            ),
        )
        if agent["state"] != "delivered":
            raise CompositionRouteError("agent terminal must be delivered before readiness handoff")
        routed = cast(
            dict[str, Any],
            self.timeline.command("composition", "handoff.readiness", {"operation": operation}),
        )
        self.timeline.command("readiness", "admit_grant", routed["authority"])
        self.timeline.command("readiness", "set_provider_authority", routed["authority"])
        self.timeline.command("readiness", "request_mutation", routed["work"])
        self.timeline.command(
            "host",
            "wake",
            {"subject": SUBJECT, "reason": f"mutation:{operation}", "at_us": self.timeline.now_us},
        )
        self.timeline.command(
            "github",
            "authority.read",
            {"request": "authority-before-mutation", "at_us": self.timeline.now_us},
        )

    def settle_workflow_mutation(self, *, operation: str = PUBLICATION_OPERATION) -> None:
        composition = cast(dict[str, Any], self.observe("composition.state"))
        [handoff] = [item for item in composition["handoffs"] if item["operation"] == operation]
        readiness = cast(dict[str, Any], self.observe("readiness.state"))
        [terminal] = [item for item in readiness["terminals"] if item["operation"] == operation]
        if terminal["variant"] != "Pushed":
            raise CompositionRouteError("readiness did not return Pushed for the workflow mutation")
        self.timeline.command(
            "workflow",
            "terminal.mutation",
            {"occurrence": handoff["workflow_occurrence"], "value": terminal["value"]},
        )

    def check(self, scenario_id: str) -> tuple[CoMountingReport, Artifact, dict[str, Any]]:
        states = {
            "composition": cast(dict[str, Any], self.observe("composition.state")),
            "workflow": cast(dict[str, Any], self.observe("workflow.state")),
            "workflow_check": cast(dict[str, Any], self.observe("workflow.check")),
            "readiness": cast(dict[str, Any], self.observe("readiness.state")),
            "readiness_check": cast(dict[str, Any], self.observe("readiness.check")),
            "github": cast(dict[str, Any], self.observe("github.state")),
            "agents": cast(dict[str, Any], self.observe("agents.state")),
            "host": cast(dict[str, Any], self.observe("host.state")),
        }
        artifact = self.timeline.artifact(scenario_id)
        workflow_violations = tuple(cast(list[str], states["workflow_check"]["violations"]))
        readiness_violations = tuple(
            f"{item['operation']}:{item['rule']}"
            for item in cast(list[dict[str, Any]], states["readiness_check"]["violations"])
        )
        github_violations = GitHubChecker().check(states["github"])
        agents_violations = AgentsChecker.check(artifact).violations
        try:
            HostArtifactChecker.check(artifact)
        except HostCheckFailed as error:
            host_violations = (str(error),)
        else:
            host_violations = ()
        local_violations = {
            "agents": agents_violations,
            "github": github_violations,
            "host": host_violations,
            "readiness": readiness_violations,
            "workflow": workflow_violations,
        }
        local_passed = {name: not violations for name, violations in local_violations.items()}
        cross = _cross_violations(artifact, states)
        causal_blockers: tuple[str, ...] = ()
        failed = [name for name, passed in local_passed.items() if not passed]
        if cross or len(failed) != 1:
            scope = "co_mounting"
            reducible_to = None
        else:
            [scope] = failed
            reducible_to = scope
        return (
            CoMountingReport(
                local_passed=local_passed,
                local_violations=local_violations,
                cross_violations=cross,
                causal_blockers=causal_blockers,
                scope=scope,
                reducible_to=reducible_to,
            ),
            artifact,
            states,
        )

    def _accept_signed_webhook_and_project(self, payload: object) -> object:
        result = self.timeline.command("composition", "webhook.accept", payload)
        values = _exact(payload, WEBHOOK_FIELDS, "signed webhook")
        authority = {
            "phase": "running",
            "incarnation": values["incarnation"],
            "head": values["head"],
            "base": values["base"],
            "policy": values["policy"],
        }
        commands = (
            ("host", "register_route", {"route": values["route"]}),
            ("host", "register_instance", {"subject": values["subject"], "route": values["route"]}),
            (
                "host",
                "wake",
                {
                    "subject": values["subject"],
                    "reason": f"webhook:{values['delivery']}",
                    "at_us": self.timeline.now_us,
                },
            ),
            (
                "workflow",
                "observe.head",
                {
                    "identity": f"{values['delivery']}:head",
                    "head": values["head"],
                    "base": values["base"],
                    "policy": values["policy"],
                    "mergeable": True,
                    "strict_base": False,
                    "base_current": True,
                },
            ),
            (
                "github",
                "authority.set",
                {
                    "epoch": values["incarnation"],
                    "head": values["head"],
                    "base": values["base"],
                    "policy": values["policy"],
                },
            ),
            (
                "github",
                "authority.read",
                {"request": f"authority:{values['delivery']}", "at_us": self.timeline.now_us},
            ),
            ("readiness", "admit_grant", authority),
            ("readiness", "set_provider_authority", authority),
        )
        for module, command, command_payload in commands:
            self.timeline.command(module, command, command_payload)
        return result


def build_modules() -> tuple[Any, ...]:
    agents = AgentsSimulation()
    return (
        CompositionModule(),
        V5MutationWorkflowSimulation.fresh(),
        ReadinessModule(runner=DeliveredAgentsCodingRunner(agents)),
        GitHubSimulation(),
        agents,
        HostSimulation(),
    )


def build_failure_modules() -> tuple[Any, ...]:
    return (
        CompositionModule(),
        WorkflowSimulation.fresh(),
        ReadinessModule(),
        GitHubSimulation(),
        AgentsSimulation(),
        HostSimulation(),
    )


def run_causal_composition(
    *,
    proposed_commit_message: str = "Apply requested change",
    corrupt_handoff_authority: bool = False,
    substitute_work_instruction: str | None = None,
) -> CompositionEvidence:
    whole = HamsterdanCoMounting.open()
    whole.command("composition.signed_webhook", whole.webhook())
    _run_until(
        whole,
        lambda: cast(dict[str, Any], whole.observe("workflow.state"))["life_state"]["head"] == HEAD,
    )
    whole.command(
        "workflow.observe.comment",
        {
            "identity": f"{DELIVERY}:comment",
            "id": "501",
            "kind": "change",
            "arg": "rename the config key",
            "authorized": True,
        },
    )
    _run_until(
        whole,
        lambda: cast(dict[str, Any], whole.observe("workflow.state"))["pending"] is not None,
    )
    requested = cast(dict[str, Any], whole.observe("workflow.state"))
    held_at_request = list(requested["held_activities"])
    agent_operation = whole.route_workflow_mutation(
        proposed_commit_message=proposed_commit_message,
        substitute_work_instruction=substitute_work_instruction,
    )
    _run_until(
        whole,
        lambda: (
            cast(
                dict[str, Any],
                whole.observe("agents.operation", {"operation": agent_operation, "attempt": 1}),
            )["state"]
            == "delivered"
        ),
    )
    whole.route_delivered_mutation_to_readiness()
    whole.fault("readiness.git_response_lost", {"operation": PUBLICATION_OPERATION})
    _start_module(whole, "readiness")
    whole.timeline.execute()
    whole.timeline.crash("host_crash_after_git_acceptance")
    whole.timeline = whole.timeline.restart()
    _run_until(
        whole,
        lambda: bool(cast(dict[str, Any], whole.observe("readiness.state"))["terminals"]),
    )
    whole.settle_workflow_mutation()
    _run_until(
        whole,
        lambda: (
            cast(dict[str, Any], whole.observe("workflow.state"))["mutation_state"] is not None
            and cast(dict[str, Any], whole.observe("workflow.state"))["mutation_state"]["state"] == "idle"
            and bool(cast(dict[str, Any], whole.observe("workflow.state"))["life_state"]["expected"])
        ),
    )
    _run_until_waiting(whole)
    if corrupt_handoff_authority:
        whole.fault("composition.handoff.authority", {"head": CORRUPT_HEAD})
        whole.command("composition.handoff.readiness", {"operation": PUBLICATION_OPERATION})
    if corrupt_handoff_authority:
        scenario_id = "hamsterdan-causal-composition-authority-mismatch"
    elif substitute_work_instruction is not None:
        scenario_id = "hamsterdan-causal-composition-work-substitution"
    else:
        scenario_id = "hamsterdan-causal-composition"
    report, artifact, states = whole.check(scenario_id)
    replayed = replay(Artifact.decode(artifact.encode()), build_modules)
    return CompositionEvidence(
        artifact,
        replayed,
        report,
        _metrics(artifact, states) | {"held_activities_at_request": held_at_request},
    )


def run_workflow_failure_proof() -> WorkflowFailureProof:
    whole = HamsterdanCoMounting.open(module_factory=build_failure_modules)
    whole.command("workflow.observe.head", _workflow_head())
    whole.command("workflow.observe.run", _workflow_run())
    _run_until(whole, lambda: cast(dict[str, Any], whole.observe("workflow.state"))["pending"] is not None)
    whole.fault(
        "workflow.terminal.rerun.corrupt_operation",
        {"replacement": "rerun:other:99:9"},
    )
    whole.command(
        "workflow.terminal.rerun",
        {"operation": WORKFLOW_OPERATION, "variant": "landed"},
    )
    _run_until(
        whole,
        lambda: cast(dict[str, Any], whole.observe("workflow.state"))["ladder"]["settled"] == "landed",
    )
    _run_until_waiting(whole)
    report, artifact, _states = whole.check("hamsterdan-co-mounting-workflow-correlation-failure")
    replayed = replay(Artifact.decode(artifact.encode()), build_failure_modules)
    reduced, reduced_violations = _reduced_workflow_failure()
    reduced_replay = replay(Artifact.decode(reduced.encode()), lambda: (WorkflowSimulation.fresh(),))
    return WorkflowFailureProof(
        artifact,
        replayed,
        report,
        reduced,
        reduced_replay,
        reduced_violations,
    )


def _reduced_workflow_failure() -> tuple[Artifact, tuple[str, ...]]:
    timeline = Timeline.open((WorkflowSimulation.fresh(),), WORKFLOW_BUDGET, seed=31)
    timeline.command("workflow", "observe.head", _workflow_head())
    timeline.command("workflow", "observe.run", _workflow_run())
    _run_workflow_until(
        timeline, lambda: cast(dict[str, Any], timeline.observe("workflow", "state").value)["pending"] is not None
    )
    timeline.fault(
        "workflow",
        "terminal.rerun.corrupt_operation",
        payload={"replacement": "rerun:other:99:9"},
    )
    timeline.command(
        "workflow",
        "terminal.rerun",
        {"operation": WORKFLOW_OPERATION, "variant": "landed"},
    )
    _run_workflow_until(
        timeline,
        lambda: cast(dict[str, Any], timeline.observe("workflow", "state").value)["ladder"]["settled"] == "landed",
    )
    check = cast(dict[str, Any], timeline.observe("workflow", "check").value)
    timeline.observe("workflow", "state")
    return timeline.artifact("workflow-correlation-failure-reduced"), tuple(check["violations"])


def _run_until(whole: HamsterdanCoMounting, done: Any, *, steps: int = 128) -> None:
    for _ in range(steps):
        if done():
            return
        result = whole.timeline.step()
        if isinstance(result, Waiting):
            raise TypeError("co-mounting scenario became waiting before its target state")
    raise AssertionError(f"co-mounting scenario exceeded {steps} bounded steps")


def _run_until_waiting(whole: HamsterdanCoMounting, *, steps: int = 128) -> None:
    for _ in range(steps):
        if isinstance(whole.timeline.step(), Waiting):
            return
    raise AssertionError(f"co-mounting scenario did not become waiting within {steps} bounded steps")


def _start_module(whole: HamsterdanCoMounting, module: str, *, steps: int = 128) -> LeafOffered:
    for _ in range(steps):
        started = whole.timeline.start()
        if isinstance(started, Waiting):
            raise TypeError(f"co-mounting scenario became waiting before {module!r} was selected")
        if isinstance(started, StepCompleted):
            continue
        if started.action.module == module:
            return started
        whole.timeline.execute()
        whole.timeline.finish()
    raise AssertionError(f"co-mounting scenario did not select {module!r} within {steps} bounded steps")


def _run_workflow_until(timeline: Timeline, done: Any, *, steps: int = 64) -> None:
    for _ in range(steps):
        if done():
            return
        result = timeline.step()
        if isinstance(result, Waiting):
            raise TypeError("reduced workflow became waiting before its target state")
    raise AssertionError(f"reduced workflow exceeded {steps} bounded steps")


def _cross_violations(artifact: Artifact, states: dict[str, Any]) -> tuple[str, ...]:
    composition = states["composition"]
    if not composition["webhooks"] or not composition["handoffs"]:
        return ()
    [webhook] = composition["webhooks"]
    [handoff] = composition["handoffs"]
    violations = []
    workflow_request = states["workflow"]["request"]
    if (
        workflow_request is None
        or handoff["workflow_occurrence"] != workflow_request["occurrence"]
        or handoff["operation"] != workflow_request["correlation"]
        or handoff["operation"] != workflow_request["idempotency"]
    ):
        violations.append("composition handoff does not identify the real workflow mutation request")
    if workflow_request is not None and handoff["work"] != workflow_request["work"]:
        violations.append("composition handoff altered the real workflow-declared MutWork")
    readiness_authority = handoff.get("readiness_authority")
    signed_authority = _authority(webhook)
    github_authority = states["github"]["authority"]
    readiness_grant = states["readiness"]["grant"]
    if (
        readiness_authority != signed_authority
        or readiness_grant != signed_authority
        or github_authority
        != {
            "epoch": signed_authority["incarnation"],
            "head": signed_authority["head"],
            "base": signed_authority["base"],
            "policy": signed_authority["policy"],
        }
    ):
        violations.append("readiness authority differs from the signed webhook and GitHub authority")
    operation = handoff["operation"]
    work = handoff["work"]
    expected_request = asdict(V5MutationGate.request("owner/repo", 7, MutWork(**work)))
    requests = states["readiness"]["requests"]
    publications = states["readiness"]["provider"]["publications"]
    if requests != [{"operation": operation, "value": work}]:
        violations.append("readiness did not receive the unchanged workflow-declared MutWork")
    if len(publications) != 1 or publications[0]["operation"] != operation:
        violations.append("accepted Git effect does not share the workflow operation")
    submission = _one_command_payload(artifact, "agents", "submit")
    terminal_declaration = _one_command_payload(artifact, "agents", "terminal")
    if (
        submission["operation"] != handoff["agent_operation"]
        or submission["attempt"] != 1
        or submission["request"] != expected_request
        or handoff["request"] != expected_request
    ):
        violations.append("agents did not receive the canonical request for the workflow-declared MutWork")
    agent_operations = states["agents"]["operations"]
    if (
        len(agent_operations) != 1
        or agent_operations[0]["operation"] != handoff["agent_operation"]
        or agent_operations[0]["state"] != "delivered"
    ):
        violations.append("agent terminal is not delivered under the workflow operation")
    if publications:
        delivered_digest = payload_digest({"schema_version": 1, "coding_result": terminal_declaration["result"]})
        if publications[0]["coding_result_digest"] != delivered_digest:
            violations.append("Git publication did not consume the exact delivered agents CodingResult")
    readiness_terminals = states["readiness"]["terminals"]
    workflow_terminal = states["workflow"]["terminal"]
    if (
        len(readiness_terminals) != 1
        or workflow_terminal is None
        or workflow_terminal["operation"] != operation
        or workflow_terminal["occurrence"] != handoff["workflow_occurrence"]
        or workflow_terminal["value"] != readiness_terminals[0]["value"]
    ):
        violations.append("readiness Pushed did not close the original workflow occurrence")
    host_subject = states["host"]["subjects"].get(webhook["subject"])
    if host_subject is None or host_subject["route"] != webhook["route"]:
        violations.append("host route custody does not match the signed webhook")
    agent_delivered = _action_position(artifact, "agents", "deliver")
    readiness_requested = _command_position(artifact, "readiness", "request_mutation")
    if agent_delivered is None or readiness_requested is None or agent_delivered >= readiness_requested:
        violations.append("readiness mutation was routed before the agent terminal was delivered")
    return tuple(violations)


def _metrics(artifact: Artifact, states: dict[str, Any]) -> dict[str, Any]:
    readiness = states["readiness"]
    provider = readiness["provider"]
    agents = states["agents"]["operations"]
    workflow = states["workflow"]
    interleaving = [
        choice
        for operation in artifact.operations
        for choice in operation["choices"]
        if choice["stream"] == "runtime:event_order"
    ]
    selected_modules = {choice["selected"].split(":", 1)[0] for choice in interleaving}
    resource_peaks: dict[str, int] = {}
    for entry in artifact.journal:
        if entry["kind"] != "resources":
            continue
        for name, value in entry["value"]["usage"].items():
            resource_peaks[name] = max(resource_peaks.get(name, 0), value)
    [publication] = provider["publications"]
    [agent] = agents
    [handoff] = states["composition"]["handoffs"]
    [request] = readiness["requests"]
    workflow_request_projection = workflow["request"]
    if workflow_request_projection is None:
        raise ValueError("causal composition metrics require one real workflow mutation request")
    submission = _one_command_payload(artifact, "agents", "submit")
    terminal_declaration = _one_command_payload(artifact, "agents", "terminal")
    workflow_request = V5MutationGate.request("owner/repo", 7, MutWork(**request["value"]))
    return {
        "accepted_git_effects": len(provider["publications"]),
        "agent_deliveries": agent["accepted_deliveries"],
        "agent_runtime_starts": agent["runtime_starts"],
        "artifact_bytes": len(artifact.encode()),
        "crash_phases": [
            operation["result"]["phase"] for operation in artifact.operations if operation["kind"] == "crash"
        ],
        "final_generation": artifact.generation,
        "interleaved_modules": sorted(selected_modules),
        "interleaving_draws": len(interleaving),
        "journal_digest": artifact.journal_digest,
        "journal_entries": len(artifact.journal),
        "lookup_recoveries": int(publication["recovered"]),
        "delivered_request": submission["request"],
        "delivered_result_digest": payload_digest(
            {"schema_version": 1, "coding_result": terminal_declaration["result"]}
        ),
        "final_held_activities": workflow["held_activities"],
        "operations": len(artifact.operations),
        "operation": handoff["operation"],
        "provider_call_kinds": [call["kind"] for call in provider["calls"]],
        "publication_coding_result_digest": publication["coding_result_digest"],
        "publication_payload_digest": publication["payload_digest"],
        "publication_result_head": publication["result_head"],
        "readiness_request": asdict(workflow_request),
        "readiness_work": request["value"],
        "readiness_agent_calls": sum(call["kind"] == "agent" for call in provider["calls"]),
        "resource_peaks": resource_peaks,
        "signed_webhooks": len(states["composition"]["webhooks"]),
        "workflow_terminal": workflow["terminal"]["variant"],
        "workflow_expected_head": workflow["life_state"]["expected"],
        "workflow_work": workflow_request_projection["work"],
    }


def _one_command_payload(artifact: Artifact, module: str, name: str) -> dict[str, Any]:
    payloads = [
        operation["request"]["payload"]
        for operation in artifact.operations
        if operation["kind"] == "command"
        and operation["request"]["module"] == module
        and operation["request"]["name"] == name
    ]
    if len(payloads) != 1:
        raise CompositionRouteError(f"expected one {module}.{name} command, observed {len(payloads)}")
    return cast(dict[str, Any], payloads[0])


def _action_position(artifact: Artifact, module: str, name: str) -> int | None:
    positions = []
    for operation in artifact.operations:
        if operation["kind"] not in {"start", "finish"}:
            continue
        result = operation["result"]
        action = result.get("action")
        if (
            action is not None
            and action["module"] == module
            and action["name"] == name
            and (operation["kind"] == "finish" or result["status"] == "completed")
        ):
            positions.append(operation["position"])
    return positions[-1] if positions else None


def _command_position(artifact: Artifact, module: str, name: str) -> int | None:
    positions = [
        operation["position"]
        for operation in artifact.operations
        if operation["kind"] == "command"
        and operation["request"]["module"] == module
        and operation["request"]["name"] == name
    ]
    return positions[-1] if positions else None


def _signature(body: dict[str, object], signing_key: bytes) -> str:
    payload = json.dumps(body, allow_nan=False, separators=(",", ":"), sort_keys=True).encode()
    return "sha256:" + hmac.new(signing_key, payload, sha256).hexdigest()


def _validate_webhook_body(body: dict[str, Any]) -> None:
    if body["event"] != "issue_comment" or body["action"] != "created":
        raise CompositionRouteError("causal composition accepts only an issue_comment created webhook")
    for name in ("delivery", "route", "subject", "policy"):
        _text(body[name], name)
    _commit(body["head"], "head")
    _commit(body["base"], "base")
    if type(body["incarnation"]) is not int or body["incarnation"] < 1:
        raise CompositionRouteError("incarnation must be a positive integer")


def _authority(webhook: dict[str, Any]) -> dict[str, object]:
    return {
        "phase": "running",
        "incarnation": webhook["incarnation"],
        "head": webhook["head"],
        "base": webhook["base"],
        "policy": webhook["policy"],
    }


def _workflow_head() -> dict[str, object]:
    return {
        "identity": "head-1",
        "head": "abc123",
        "base": "def456",
        "policy": "required-ci",
        "incarnation": 1,
    }


def _workflow_run() -> dict[str, object]:
    return {
        "identity": "run-7-1",
        "head": "abc123",
        "run_id": 7,
        "attempt": 1,
        "conclusion": "failure",
        "fingerprint": "tests-red",
    }


def _route(value: str, kind: str) -> tuple[str, str]:
    if type(value) is not str or "." not in value:
        raise CompositionRouteError(f"{kind} must be namespaced as '<module>.<name>'")
    module, local_name = value.split(".", 1)
    if not module or not local_name:
        raise CompositionRouteError(f"{kind} must be namespaced as '<module>.<name>'")
    return module, local_name


def _exact(value: object, keys: set[str], subject: str, *, allow_none: bool = False) -> dict[str, Any]:
    if allow_none and value is None and not keys:
        return {}
    if type(value) is not dict or set(cast(dict[object, object], value)) != keys:
        raise CompositionRouteError(f"{subject} must contain exactly {sorted(keys)!r}")
    return cast(dict[str, Any], value)


def _text(value: object, subject: str) -> str:
    if type(value) is not str or not value or not value.isascii() or not value.isprintable():
        raise CompositionRouteError(f"{subject} must be non-empty printable ASCII")
    return value


def _commit(value: object, subject: str) -> str:
    if type(value) is not str or len(value) != 40 or any(character not in "0123456789abcdef" for character in value):
        raise CompositionRouteError(f"{subject} must be a 40-character lowercase hexadecimal commit")
    return value


__all__ = [
    "COMPOSITION_BUDGET",
    "LOCAL_MODULES",
    "PUBLICATION_OPERATION",
    "RESOURCE_LIMITS",
    "CompositionRouteError",
    "HamsterdanCoMounting",
    "build_modules",
    "run_causal_composition",
    "run_workflow_failure_proof",
]
