"""Deterministic external world around the real non-sharded V5 HostService.

Petrus owns scheduling, crash generations, checker cadence, and strict replay.
This module owns only Hamsterdan commands, modeled provider truth, detached
observations, and the independent readiness comparison.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import math
import re
import sqlite3
import uuid
import weakref
from collections import Counter
from contextlib import closing
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Self, cast

from fastapi.testclient import TestClient
from petrus.testing.dst import (
    ApplyResult,
    BudgetV4,
    CheckResult,
    Command,
    Disposition,
    Fault,
    FaultDisposition,
    GenerationStart,
    Observation,
    ObservationRequest,
    ReplayResult,
    ResourceUsage,
    ScenarioArtifact,
    ScenarioContext,
    ScenarioRegistry,
    ScheduledCommand,
    StaleGeneration,
    Timeline,
    World,
    replay,
)
from pydantic import JsonValue

from hamsterdan.github_app.config import HostConfig
from hamsterdan.host.agenticus import AgentRouteStore, compose_agent
from hamsterdan.host.api import create_app
from hamsterdan.host.service import HostService
from hamsterdan.host.v5.application import PrReadinessV5Application
from hamsterdan.testing.readiness import (
    AuthorityClaim,
    AuthorityFacts,
    ChangeAuthorization,
    CheckFacts,
    CiFacts,
    EffectObligation,
    HumanFacts,
    MutationFacts,
    ReadinessFacts,
    ReadinessModel,
    ReviewFacts,
    TimerObligation,
)

from ._readiness_contract import (
    BASE,
    CHECKER_IDENTITY,
    COMMAND_KEYS,
    DEFAULT_BUDGET,
    EFFECT_KINDS,
    EVENTS,
    HEAD,
    HOST_COMMANDS,
    NAME,
    OPERATION,
    PROFILE_IDENTITY,
    PROFILE_LIMITS,
    PROFILE_RESOURCE_LIMITS,
    READINESS_POLICY_DIGEST,
    REMINDER_DELAY,
    SHA,
    SUBJECT,
    WEBHOOK_SECRET,
    ProfileDisposition,
    bounded_json,
    bounded_text,
    parse_authority,
    strict_digest,
    strict_object,
)
from ._readiness_provider import (
    AgentRunner,
    ModeledGitPublisher,
    ProviderClients,
    ProviderTransport,
    ReadinessProviderTruth,
    _Emitted,
    webhook_body,
)


@dataclass
class _Generation:
    host: HostService
    client: TestClient
    context: dict[str, ScenarioContext | None]
    proposed: set[tuple[str, int]] = field(default_factory=set)


class ReadinessScenarioProfile:
    """Petrus profile over one opaque real non-sharded V5 HostService generation."""

    identity = PROFILE_IDENTITY

    def __init__(self, root: Path) -> None:
        self.root = root
        self.truth = ReadinessProviderTruth()
        self._dropped: list[weakref.ReferenceType[_Generation]] = []
        self._host_followups = 0

    def validate(self, command: Command) -> Command:
        keys = COMMAND_KEYS.get(command.name)
        if keys is None:
            raise ValueError(f"unknown readiness command {command.name!r}")
        bounded_json(command.payload, PROFILE_LIMITS["payload_bytes"], command.name)
        payload = strict_object(command.payload, keys, command.name)
        if (
            command.name not in HOST_COMMANDS
            and command.name != "readiness.time.advance"
            and command.name != "readiness.github.webhook.deliver"
            and payload.get("subject") != SUBJECT
        ):
            raise ValueError("readiness command subject is outside this profile")
        if command.name == "readiness.github.pr.set":
            authority = parse_authority(payload["authority"])
            bounded_text(authority.head, "pull request head", pattern=SHA)
            bounded_text(authority.base, "pull request base", pattern=SHA)
            bounded_text(authority.policy, "pull request policy", pattern=re.compile(r"[0-9a-f]{64}"))
        elif command.name == "readiness.github.ci.set":
            bounded_text(payload["head"], "CI head", pattern=SHA)
            required, checks = payload["required_checks"], payload["checks"]
            if type(required) is not list or len(required) > PROFILE_LIMITS["checks"]:
                raise ValueError("required_checks must be a bounded list")
            names = [bounded_text(item, "required check", pattern=NAME) for item in required]
            if len(names) != len(set(names)):
                raise ValueError("required_checks must be unique")
            if type(checks) is not list or len(checks) > PROFILE_LIMITS["checks"]:
                raise ValueError("checks must be a bounded list")
            for item in checks:
                check = strict_object(item, {"name", "run", "attempt", "status"}, command.name)
                bounded_text(check["name"], "check name", pattern=NAME)
                if type(check["run"]) is not int or type(check["attempt"]) is not int:
                    raise ValueError("check run and attempt must be positive integers")
                if check["run"] <= 0 or check["attempt"] <= 0:
                    raise ValueError("check run and attempt must be positive integers")
                if check["status"] not in {
                    "queued",
                    "running",
                    "success",
                    "failure",
                    "canceled",
                    "unavailable",
                }:
                    raise ValueError("unsupported CI status")
        elif command.name == "readiness.github.review.set":
            bounded_text(payload["head"], "review head", pattern=SHA)
            if payload["status"] not in {"pending", "clear", "blocking", "unable"}:
                raise ValueError("unsupported review status")
            if type(payload["findings"]) is not list or len(payload["findings"]) > PROFILE_LIMITS["findings"]:
                raise ValueError("review findings must be a bounded list")
        elif command.name == "readiness.github.human.review":
            bounded_text(payload["reviewer"], "reviewer", pattern=NAME)
            bounded_text(payload["head"], "human review head", pattern=SHA)
            if type(payload["review"]) is not int or payload["review"] <= 0:
                raise ValueError("human review identity must be positive")
            if payload["state"] not in {"APPROVED", "CHANGES_REQUESTED", "DISMISSED"}:
                raise ValueError("unsupported human review state")
        elif command.name == "readiness.github.human.resolve_thread":
            bounded_text(payload["thread"], "review thread", pattern=NAME)
            bounded_text(payload["resolver"], "thread resolver", pattern=NAME)
            if type(payload["resolved"]) is not bool:
                raise ValueError("thread resolution must be boolean")
        elif command.name == "readiness.github.human.comment":
            if type(payload["comment"]) is not int or payload["comment"] <= 0:
                raise ValueError("comment identity must be positive")
            bounded_text(payload["author"], "comment author", pattern=NAME)
            fixture = bounded_text(payload["fixture"], "comment fixture", pattern=NAME)
            if fixture != "change" and not fixture.startswith("recover:"):
                raise ValueError("unsupported human comment fixture")
            if fixture.startswith("recover:"):
                bounded_text(fixture.removeprefix("recover:"), "recovery operation", pattern=OPERATION)
            if payload["digest"] != strict_digest({"fixture": fixture}):
                raise ValueError("comment fixture digest does not match")
        elif command.name == "readiness.agent.terminal":
            bounded_text(payload["operation"], "agent operation", pattern=OPERATION)
            if type(payload["attempt"]) is not int or payload["attempt"] <= 0:
                raise ValueError("agent attempt must be positive")
            if payload["status"] not in {"clear", "blocking", "unable", "changed", "unchanged"}:
                raise ValueError("unsupported agent terminal status")
            fixture = bounded_text(payload["fixture"], "agent fixture", pattern=NAME)
            if fixture not in {"review", "conversation_change", "conversation_recover", "coding"}:
                raise ValueError("unsupported agent fixture")
            if payload["digest"] != strict_digest({"fixture": fixture, "status": payload["status"]}):
                raise ValueError("agent fixture digest does not match")
        elif command.name == "readiness.github.webhook.emit":
            try:
                uuid.UUID(cast(str, payload["delivery"]))
            except TypeError, ValueError:
                raise ValueError("webhook delivery must be an exact UUID") from None
            event = bounded_text(payload["event"], "webhook event", pattern=NAME)
            if event not in EVENTS:
                raise ValueError("unsupported webhook event")
            fixture = bounded_text(payload["fixture"], "webhook fixture")
            if not fixture.startswith(f"{event}:") or payload["digest"] != strict_digest(
                {"event": event, "fixture": fixture}
            ):
                raise ValueError("webhook fixture digest does not match")
        elif command.name == "readiness.github.webhook.deliver":
            try:
                uuid.UUID(cast(str, payload["delivery"]))
            except TypeError, ValueError:
                raise ValueError("webhook delivery must be an exact UUID") from None
        elif command.name == "readiness.github.effect.reveal":
            bounded_text(payload["operation"], "effect operation", pattern=NAME)
        elif command.name == "readiness.time.advance":
            seconds = payload["seconds"]
            if type(seconds) is not int or not 0 < seconds <= DEFAULT_BUDGET.logical_instant:
                raise ValueError("logical time advance is outside the profile bound")
        return command

    def validate_fault(self, fault: Fault) -> Fault:
        bounded_json(fault.payload, 4096, fault.name)
        if fault.name == "readiness.git.publish":
            if not fault.target.startswith("git:") or fault.disposition != FaultDisposition.RAISE.value:
                raise ValueError("unsupported readiness Git publication fault")
            bounded_text(fault.target.removeprefix("git:"), "Git publication operation", pattern=OPERATION)
            payload = strict_object(fault.payload, {"cut"}, fault.name)
            if payload["cut"] != "ref_cas":
                raise ValueError("unsupported readiness Git publication cut")
            return fault
        if (
            fault.name != "readiness.github.effect"
            or not fault.target.startswith("effect:")
            or fault.disposition != FaultDisposition.RAISE.value
        ):
            raise ValueError("unsupported readiness fault")
        if fault.target.removeprefix("effect:") not in EFFECT_KINDS:
            raise ValueError("unsupported readiness effect target")
        payload = strict_object(fault.payload, {"cut"}, fault.name)
        if payload["cut"] not in {
            "before_acceptance",
            "after_acceptance_before_response",
            "before_visibility",
            "identity_collision",
        }:
            raise ValueError("unsupported readiness effect cut")
        return fault

    def create(self, context: ScenarioContext) -> GenerationStart[_Generation]:
        return self._start(context)

    def load(self, context: ScenarioContext) -> GenerationStart[_Generation]:
        return self._start(context)

    def _start(self, context: ScenarioContext) -> GenerationStart[_Generation]:
        self.root.mkdir(mode=0o700, parents=True, exist_ok=True)
        routes = AgentRouteStore(self.root / "agent-routes.sqlite3")
        agent_composition = compose_agent()
        routes.activate(agent_composition, self.root / "applications")
        context_holder: dict[str, ScenarioContext | None] = {"value": None}

        def transport_factory(_client: object) -> ProviderTransport:
            return ProviderTransport(self.truth, context_holder)

        def application_factory(*args: Any, **kwargs: Any) -> PrReadinessV5Application:
            kwargs["mutation_publisher"] = ModeledGitPublisher(self.truth, context_holder)
            return PrReadinessV5Application(*args, **kwargs)

        host = HostService(
            _config(self.root),
            clients=cast(Any, ProviderClients()),
            runner=cast(Any, AgentRunner(self.truth)),
            agent_composition=agent_composition,
            agent_routes=routes,
            application_factory=application_factory,
            reminder_delay=REMINDER_DELAY,
            clock=lambda: float(context.now()),
            transport_factory=transport_factory,
        )
        host.registry.reconcile(44, ((31, "owner/repo"),))
        generation = _Generation(host, TestClient(create_app(host, reconcile_startup=False)), context_holder)
        return GenerationStart(generation, tuple(self._followups(generation, context)))

    def apply(self, generation: _Generation, command: Command, context: ScenarioContext) -> ApplyResult:
        generation.context["value"] = context
        generation.proposed.discard((command.name, context.now()))
        try:
            if command.name not in HOST_COMMANDS and command.name != "readiness.time.advance":
                self.truth.provider_truth_changes += 1
            value, disposition = self._apply(generation, command, context)
            if self.truth.harness_errors:
                raise AssertionError(self.truth.harness_errors[-1])
            scheduled = self._followups(generation, context)
            if command.name == "readiness.time.advance":
                target = context.now() + cast(int, cast(dict[str, JsonValue], command.payload)["seconds"])
                proposal = ("readiness.host.drive_one", target)
                if proposal not in generation.proposed:
                    generation.proposed.add(proposal)
                    scheduled.append(
                        ScheduledCommand(
                            instant=target,
                            command=Command(profile=self.identity, name="readiness.host.drive_one", payload={}),
                        )
                    )
                    self._host_followups += 1
            return ApplyResult(disposition=disposition, value=value, scheduled=scheduled)
        finally:
            generation.context["value"] = None

    def _apply(
        self,
        generation: _Generation,
        command: Command,
        context: ScenarioContext,
    ) -> tuple[JsonValue, ProfileDisposition]:
        payload = cast(dict[str, JsonValue], command.payload)
        name = command.name
        if name == "readiness.github.pr.set":
            authority = parse_authority(payload["authority"])
            disposition: ProfileDisposition = "idempotent" if authority == self.truth.authority else "applied"
            self.truth.set_authority(authority)
            return {"authority": authority.dump()}, disposition
        if name == "readiness.github.ci.set":
            required = payload["required_checks"]
            checks = payload["checks"]
            if type(required) is not list or not all(type(item) is str and item for item in required):
                raise ValueError("required_checks must be bounded names")
            if type(checks) is not list:
                raise ValueError("checks must be a list")
            normalized = []
            for item in checks:
                value = strict_object(item, {"name", "run", "attempt", "status"}, name)
                if value["status"] not in {"queued", "running", "success", "failure", "canceled", "unavailable"}:
                    raise ValueError("unsupported CI status")
                normalized.append(value)
            self.truth.required_checks = tuple(cast(list[str], required))
            self.truth.checks = normalized
            self.truth.review_head = cast(str, payload["head"])
            return {"checks": len(normalized)}, "applied"
        if name == "readiness.github.review.set":
            findings = payload["findings"]
            if type(findings) is not list:
                raise ValueError("review findings must be a list")
            status = payload["status"]
            if status not in {"pending", "clear", "blocking", "unable"}:
                raise ValueError("unsupported review status")
            self.truth.review_head = cast(str, payload["head"])
            self.truth.review_status = cast(str, status)
            self.truth.findings = cast(list[dict[str, JsonValue]], findings)
            self.truth.review_terminal = {
                "kind": "review",
                "status": status,
                "findings": findings,
            }
            return {"status": status, "findings": len(findings)}, "applied"
        if name == "readiness.github.human.review":
            reviewer, state = cast(str, payload["reviewer"]), cast(str, payload["state"])
            if state not in {"APPROVED", "CHANGES_REQUESTED", "DISMISSED"}:
                raise ValueError("unsupported human review state")
            self.truth.human_reviews[reviewer] = (f"{context.now():020d}", state)
            return {"reviewer": reviewer, "state": state}, "applied"
        if name == "readiness.github.human.resolve_thread":
            self.truth.review_threads[cast(str, payload["thread"])] = cast(bool, payload["resolved"])
            return {"thread": payload["thread"], "resolved": payload["resolved"]}, "applied"
        if name == "readiness.github.human.comment":
            self.truth.set_human_comment(
                cast(int, payload["comment"]),
                cast(str, payload["author"]),
                cast(str, payload["fixture"]),
            )
            return {"comment": payload["comment"]}, "applied"
        if name == "readiness.agent.terminal":
            operation = cast(str, payload["operation"])
            self.truth.agent_terminals[operation] = {
                "kind": cast(str, payload["fixture"]),
                "operation": operation,
                "attempt": cast(int, payload["attempt"]),
                "status": payload["status"],
                "findings": [],
            }
            return {"operation": payload["operation"], "status": payload["status"]}, "applied"
        if name == "readiness.github.webhook.emit":
            delivery = cast(str, payload["delivery"])
            event = cast(str, payload["event"])
            fixture = cast(str, payload["fixture"])
            if payload["digest"] != strict_digest({"event": event, "fixture": fixture}):
                raise ValueError("webhook fixture digest does not match")
            action = fixture.partition(":")[2]
            comment = self.truth.human_comments[-1] if event == "issue_comment" and self.truth.human_comments else None
            emitted = _Emitted(delivery, event, action, self.truth.authority, comment)
            existing = self.truth.emitted.get(delivery)
            if existing is not None and existing != emitted:
                return {"delivery": delivery}, "quarantined"
            self.truth.emitted[delivery] = emitted
            return {"delivery": delivery}, "idempotent" if existing is not None else "applied"
        if name == "readiness.github.webhook.deliver":
            delivery = cast(str, payload["delivery"])
            emitted = self.truth.emitted.get(delivery)
            if emitted is None:
                raise ValueError("cannot deliver an unknown webhook")
            body = webhook_body(emitted)
            signature = hmac.new(WEBHOOK_SECRET.encode(), body, hashlib.sha256).hexdigest()
            response = generation.client.post(
                "/github/webhooks",
                content=body,
                headers={
                    "content-type": "application/json",
                    "content-length": str(len(body)),
                    "x-hub-signature-256": f"sha256={signature}",
                    "x-github-delivery": delivery,
                    "x-github-event": emitted.event,
                },
            )
            self.truth.delivery_attempts[delivery] += 1
            if response.status_code != 202:
                raise AssertionError(f"real webhook ingress refused safe fixture with status {response.status_code}")
            result = response.json()
            if result["disposition"] != "duplicate" and delivery not in self.truth.custodied:
                self.truth.custodied.append(delivery)
            return {
                "delivery": delivery,
                "disposition": str(result["disposition"]),
            }, "idempotent" if result["disposition"] == "duplicate" else "applied"
        if name == "readiness.github.effect.reveal":
            operation = cast(str, payload["operation"])
            effect = next((item for item in self.truth.effects if item.operation == operation), None)
            if effect is None:
                return {"operation": operation}, "refused_expected"
            effect.visible = True
            return {"operation": operation}, "applied"
        if name == "readiness.time.advance":
            seconds = payload["seconds"]
            if type(seconds) is not int or not 0 < seconds <= 2_000_000:
                raise ValueError("logical time advance must be an integer from 1 through 2000000 seconds")
            return {"target": context.now() + seconds}, "applied"
        if name == "readiness.host.custody_one":
            admitted = {item.delivery for item in self.truth.admitted}
            candidate = next(
                (self.truth.emitted[delivery] for delivery in self.truth.custodied if delivery not in admitted),
                None,
            )
            admission_authority = self.truth.authority
            self.truth.active_admission = candidate
            try:
                observed = generation.host.process_one()
            finally:
                self.truth.active_admission = None
            expected = None if candidate is None else {"delivery": candidate.delivery, "disposition": "completed"}
            observed_value = (
                None if observed is None else {"delivery": observed.delivery_id, "disposition": observed.disposition}
            )
            if candidate is not None and observed_value == expected:
                self.truth.admit(candidate, context.now(), admission_authority)
            self.truth.custody_actions.append({"expected": expected, "observed": observed_value})
            return {"custody": observed_value}, "applied" if observed is not None else "refused_expected"
        if name == "readiness.host.activity_one":
            self._bind_readiness_effect_authorities()
            processed = generation.host.run_one_activity()
            return {"processed": processed}, "applied" if processed else "refused_expected"
        if name == "readiness.host.drive_one":
            processed = generation.host.run_due(limit=1)
            return {"processed": processed}, "applied" if processed else "refused_expected"
        if name == "readiness.host.reconcile_one":
            processed = generation.host.reconcile_one("dst")
            if processed and (not self.truth.admitted or self.truth.admitted[-1].authority != self.truth.authority):
                identity = f"github-reconcile:{len(self.truth.admitted) + 1}"
                self.truth.admit(
                    _Emitted(
                        delivery=identity,
                        event="reconciliation",
                        action="provider_snapshot",
                        authority=self.truth.authority,
                        source_identity=identity,
                    ),
                    context.now(),
                    self.truth.authority,
                )
            return {"processed": processed}, "applied" if processed else "refused_expected"
        raise AssertionError(f"validated command has no readiness implementation: {name}")

    def _followups(self, generation: _Generation, context: ScenarioContext) -> list[ScheduledCommand]:
        state = generation.host.work_state()
        due = cast(float | None, state["runnable_due"])
        candidates: list[tuple[str, int, bool]] = [
            ("readiness.host.custody_one", context.now(), cast(bool, state["pending_custody"])),
            ("readiness.host.reconcile_one", context.now(), cast(bool, state["unloaded_application"])),
            (
                "readiness.host.drive_one",
                context.now(),
                due is not None and math.ceil(due) <= context.now(),
            ),
            (
                "readiness.host.activity_one",
                context.now(),
                cast(bool, state["unresolved_activity"]) and self._activity_terminal_ready(),
            ),
        ]
        scheduled = []
        for name, instant, eligible in candidates:
            proposal = (name, instant)
            if not eligible or proposal in generation.proposed:
                continue
            generation.proposed.add(proposal)
            self._host_followups += 1
            scheduled.append(
                ScheduledCommand(
                    instant=instant,
                    command=Command(profile=self.identity, name=name, payload={}),
                )
            )
        return scheduled

    def _activity_terminal_ready(self) -> bool:
        records = _history_records(self.root)
        terminal = {
            record.get("occurrence")
            for record in records
            if record.get("record") in {"ActivityCompleted", "ActivityFailed", "ActivityTerminalQuarantined"}
        }
        request = next(
            (
                record
                for record in records
                if record.get("record") == "ActivityRequested" and record.get("occurrence") not in terminal
            ),
            None,
        )
        if request is None:
            return False
        activity = request.get("activity")
        if activity == "review_agent":
            return self.truth.review_terminal is not None and self.truth.review_terminal.get("kind") == "review"
        if activity != "git_gate":
            return True
        payload = request.get("input")
        work = payload.get("work") if isinstance(payload, dict) else None
        op_key = work.get("op_key") if isinstance(work, dict) else None
        if not isinstance(op_key, str):
            raise TypeError("V5 Git Activity request has no strict operation key")
        if any(item.operation == op_key for item in self.truth.git_publications):
            return True
        operation = f"mutation:owner/repo:pr:7:{op_key}"
        terminal_value = self.truth.agent_terminals.get(operation)
        return (
            terminal_value is not None
            and terminal_value.get("kind") == "coding"
            and terminal_value.get("operation") == operation
            and terminal_value.get("attempt") == 1
        )

    def observe(
        self,
        generation: _Generation,
        request: ObservationRequest,
        context: ScenarioContext,
    ) -> JsonValue:
        if request.name != "readiness.state" or request.payload not in (None, {}):
            raise ValueError("readiness profile exposes only readiness.state without parameters")
        return self._state(generation, context.now())

    def _state(self, generation: _Generation, instant: int) -> dict[str, JsonValue]:
        custody = {delivery: generation.host.custody.status(delivery) for delivery in sorted(self.truth.emitted)}
        timer_expectations = self._expected_timers(instant)
        facts = self._facts(timer_expectations)
        expected = ReadinessModel().evaluate(facts)
        detached = generation.host.subject_state(44, 31, 7)
        host = {"ready": None, "snapshot": None} if detached is None else cast(dict[str, JsonValue], detached)
        snapshot = host["snapshot"]
        current_readiness = False
        if type(snapshot) is dict and snapshot.get("phase") == "running" and type(snapshot.get("incarnation")) is int:
            operation = f"ready:{self.truth.authority.head}:i{snapshot['incarnation']}"
            current_readiness = any(
                effect.kind == "readiness"
                and effect.operation == operation
                and effect.authority == self.truth.authority
                and effect.provider_authority_at_acceptance == self.truth.authority
                for effect in self.truth.effects
            )
        history, terminal_operations = _history(self.root)
        state: dict[str, JsonValue] = {
            "subject": SUBJECT,
            "expected": expected.dump(),
            "facts": facts.dump(),
            "actual": {"readiness_published": current_readiness},
            "host": host,
            "provider": self.truth.observation(),
            "custody": cast(dict[str, JsonValue], custody),
            "timer_expectations": cast(list[JsonValue], timer_expectations),
            "timer_custody": _timer_custody(self.root),
            "history": history,
            "motus": _motus(self.root),
            "git_custody": _git_custody(self.root),
            "terminal_operations": terminal_operations,
            "work": cast(dict[str, JsonValue], generation.host.work_state()),
            "bounds": {
                "limits": cast(dict[str, JsonValue], PROFILE_RESOURCE_LIMITS),
                "usage": self._usage(generation),
            },
        }
        bounded_json(state, PROFILE_LIMITS["observation_bytes"], "readiness observation")
        return state

    def resource_usage(self, generation: _Generation | None) -> ResourceUsage:
        """Account for all profile-retained data and hidden pending work."""
        return ResourceUsage(values=self._usage(generation))

    def _usage(self, generation: _Generation | None) -> dict[str, int]:
        history = _history_records(self.root)
        history_bytes = sum(
            path.stat().st_size for path in (self.root / "applications").glob("*/*/*/history.jsonl") if path.is_file()
        )
        sqlite_rows, sqlite_bytes, sqlite_counts = _sqlite_retained(self.root)
        terminal_occurrences = {
            record.get("occurrence")
            for record in history
            if record.get("record") in {"ActivityCompleted", "ActivityFailed", "ActivityTerminalQuarantined"}
            and type(record.get("occurrence")) is int
        }
        requested_occurrences = {
            record.get("occurrence")
            for record in history
            if record.get("record") == "ActivityRequested" and type(record.get("occurrence")) is int
        }
        return {
            "retained.host.history_bytes": history_bytes,
            "retained.host.history_records": len(history),
            "retained.host.sqlite_bytes": sqlite_bytes,
            "retained.host.sqlite_rows": sqlite_rows,
            "retained.profile.dropped_generations": len(self._dropped),
            "retained.profile.followups": self._host_followups,
            "retained.provider.admissions": len(self.truth.admitted),
            "retained.provider.agent_operations": len(self.truth.agent_calls),
            "retained.provider.authorities": len(self.truth.authorities),
            "retained.provider.bytes": self.truth.retained_bytes(),
            "retained.provider.calls": len(self.truth.calls),
            "retained.provider.checks": len(self.truth.checks),
            "retained.provider.collisions": len(self.truth.collisions),
            "retained.provider.comments": len(self.truth.comments),
            "retained.provider.custody_actions": len(self.truth.custody_actions),
            "retained.provider.delivery_attempts": sum(self.truth.delivery_attempts.values()),
            "retained.provider.effect_bindings": len(self.truth.effect_authorities),
            "retained.provider.effects": len(self.truth.effects),
            "retained.provider.findings": len(self.truth.findings),
            "retained.provider.git_publications": len(self.truth.git_publications),
            "retained.provider.git_reconciliations": self.truth.git_reconciliations,
            "retained.provider.reviews": len(self.truth.human_reviews),
            "retained.provider.threads": len(self.truth.review_threads),
            "retained.provider.truth_changes": self.truth.provider_truth_changes,
            "retained.provider.webhooks": len(self.truth.emitted),
            "pending.host.activities": len(requested_occurrences - terminal_occurrences),
            "pending.host.custody": sqlite_counts.get("inbox.pending", 0),
            "pending.host.dispatch": sqlite_counts.get("impetus_local_dispatch.pending", 0),
            "pending.host.runnable": sqlite_counts.get("wakes", 0),
            "pending.host.timer_acks": sqlite_counts.get("v5_timer_operations.pending_ack", 0),
            "pending.host.timer_maturities": sqlite_counts.get("v5_timers.pending_maturity", 0),
            "pending.host.timers": sqlite_counts.get("v5_timers.armed", 0),
            "pending.profile.proposals": 0 if generation is None else len(generation.proposed),
        }

    def _facts(self, timer_expectations: list[dict[str, JsonValue]]) -> ReadinessFacts:
        admitted_events = self.truth.admitted
        admitted = admitted_events[-1].authority if admitted_events else None
        generations = 0
        prior: AuthorityClaim | None = None
        for emitted in admitted_events:
            if prior is None or emitted.authority != prior:
                generations += 1
            prior = emitted.authority
        checks = tuple(CheckFacts(str(item["name"]), cast(Any, item["status"])) for item in self.truth.checks)
        review_calls = [item for item in self.truth.agent_calls if item["kind"] == "review"]
        review = (
            ReviewFacts()
            if not review_calls
            else ReviewFacts(
                head=cast(str, review_calls[-1]["head"]),
                status=cast(Any, review_calls[-1]["status"]),
                findings=(),
            )
        )
        latest_reviews = {reviewer: state for reviewer, (_submitted, state) in self.truth.human_reviews.items()}
        approvals = sum(state == "APPROVED" for state in latest_reviews.values())
        changes = any(state == "CHANGES_REQUESTED" for state in latest_reviews.values())
        mutation, mutation_effect = self._expected_mutation()
        effects = (
            *(
                EffectObligation(
                    kind=cast(
                        Any,
                        "findings"
                        if effect.kind == "finding"
                        else effect.kind
                        if effect.kind in {"dashboard", "conversation", "readiness", "reminder", "rerun"}
                        else "dashboard",
                    ),
                    operation=effect.operation,
                    authority=effect.authority,
                    content_digest=effect.content_digest,
                    status="settled" if effect.recovered else "accepted",
                    provider_authority_at_acceptance=effect.provider_authority_at_acceptance,
                    blocks_readiness=False,
                )
                for effect in self.truth.effects
            ),
            *((mutation_effect,) if mutation_effect is not None else ()),
        )
        record_identities = tuple(
            event.source_identity or f"github-delivery:{event.delivery}" for event in admitted_events
        )
        return ReadinessFacts(
            subject=SUBJECT,
            authority=AuthorityFacts(generations, admitted, self.truth.authority),
            admitted_observations=record_identities,
            ci=CiFacts(
                head=self.truth.review_head,
                required_checks=self.truth.required_checks,
                checks=checks,
            ),
            review=review,
            human=HumanFacts(
                approvals=approvals,
                required_approvals=0,
                changes_requested=changes,
                unresolved_conversations=sum(not value for value in self.truth.review_threads.values()),
            ),
            mutation=mutation,
            effects=effects,
            timers=tuple(
                TimerObligation(
                    identity=cast(str, timer["identity"]),
                    status=cast(Any, timer["status"]),
                    blocks_readiness=False,
                )
                for timer in timer_expectations
            ),
        )

    def _expected_mutation(self) -> tuple[MutationFacts, EffectObligation | None]:
        change = next(
            (
                event
                for event in reversed(self.truth.admitted)
                if event.comment is not None and event.comment.get("fixture") == "change"
            ),
            None,
        )
        if change is None or change.comment is None:
            return MutationFacts(), None
        incarnation = 0
        prior: AuthorityClaim | None = None
        for admitted in self.truth.admitted:
            if prior is None or admitted.authority != prior:
                incarnation += 1
            prior = admitted.authority
            if admitted is change:
                break
        comment = cast(dict[str, JsonValue], change.comment)
        identity = f"github-delivery:{change.delivery}"
        operation = f"push:comment:{comment['id']}:{change.authority.head}:i{incarnation}"
        authorization = ChangeAuthorization(
            identity=identity,
            operation=operation,
            authority=change.authority,
            intent="change",
            intent_digest=strict_digest({"fixture": comment["fixture"]}),
        )
        publication = next((item for item in self.truth.git_publications if item.operation == operation), None)
        if publication is None:
            return (
                MutationFacts(
                    status="requested",
                    operation=operation,
                    head=change.authority.head,
                    authorization=authorization,
                ),
                None,
            )
        admitted = self.truth.admitted[-1].authority if self.truth.admitted else None
        recovery_identity = self.truth.recovery_identity(operation)
        recovered_with_grant = publication.recovered and publication.recovery_identity == recovery_identity != ""
        if publication.response_lost and not recovered_with_grant:
            status = "ambiguous"
        elif admitted is None or admitted.head != publication.result_head:
            status = "accepted_pending_admission"
        else:
            return MutationFacts(), None
        return (
            MutationFacts(
                status=status,
                operation=operation,
                head=change.authority.head,
                result_head=publication.result_head,
                authorization=authorization,
            ),
            EffectObligation(
                kind="git_mutation",
                operation=operation,
                authority=change.authority,
                content_digest=publication.payload_digest,
                status="ambiguous" if status == "ambiguous" else "accepted",
                provider_authority_at_acceptance=publication.authority,
                authorization=identity,
                blocks_readiness=False,
            ),
        )

    def _expected_timers(self, instant: int) -> list[dict[str, JsonValue]]:
        """Fold authored admissions and provider effects into expected reminder custody."""
        timers: list[dict[str, JsonValue]] = []
        current: dict[str, JsonValue] | None = None
        phase = "running"
        head = ""
        incarnation = 0

        def cancel() -> None:
            nonlocal current
            if current is not None and current["status"] in {"scheduled", "due"}:
                current["status"] = "canceled"
            current = None

        def arm(at: int, timer_head: str, sequence: int = 0) -> dict[str, JsonValue]:
            timer = {
                "identity": f"timer:{SUBJECT}:i{incarnation}:s{sequence}",
                "incarnation": incarnation,
                "sequence": sequence,
                "head": timer_head,
                "due_at": at + REMINDER_DELAY,
                "status": "scheduled",
                "matured_at": None,
            }
            timers.append(timer)
            return timer

        ordered: list[tuple[int, str, object]] = [
            (event.semantic_order, "admission", event) for event in self.truth.admitted
        ]
        ordered.extend(
            (effect.semantic_order, "reminder", effect) for effect in self.truth.effects if effect.kind == "reminder"
        )
        for _order, kind, value in sorted(ordered, key=lambda item: item[0]):
            if kind == "admission":
                event = cast(_Emitted, value)
                authority = event.authority
                if authority.lifecycle in {"closed", "merged"}:
                    cancel()
                    phase = "terminal"
                    continue
                if phase == "terminal":
                    continue
                if phase == "quiescent":
                    head = authority.head
                elif authority.head != head:
                    cancel()
                    incarnation += 1
                    head = authority.head
                    phase = "running"
                    current = arm(event.instant, head)
                if authority.lifecycle == "draft":
                    if phase == "running":
                        cancel()
                    phase = "quiescent"
                elif phase == "quiescent":
                    phase = "running"
                    incarnation += 1
                    current = arm(event.instant, head)
                continue

            effect = cast(Any, value)
            timer_id = effect.operation.removeprefix("reminder:")
            matched = next((timer for timer in timers if timer["identity"] == timer_id), None)
            if matched is None or matched["status"] == "canceled":
                continue
            matched["status"] = "acknowledged"
            matched["matured_at"] = effect.accepted_at
            if current is matched and phase == "running":
                sequence = cast(int, matched["sequence"]) + 1
                current = arm(effect.accepted_at, cast(str, matched["head"]), sequence)

        if current is not None and current["status"] == "scheduled" and cast(int, current["due_at"]) <= instant:
            current["status"] = "due"
            current["matured_at"] = instant
            current = arm(instant, cast(str, current["head"]), cast(int, current["sequence"]) + 1)
        return timers

    def _bind_readiness_effect_authorities(self) -> None:
        records = _history_records(self.root)
        terminal_occurrences = {
            record.get("occurrence")
            for record in records
            if record.get("record") in {"ActivityCompleted", "ActivityFailed", "ActivityTerminalQuarantined"}
            and type(record.get("occurrence")) is int
        }
        for record in records:
            occurrence = record.get("occurrence")
            if (
                record.get("record") != "ActivityRequested"
                or record.get("activity") != "announce_gate"
                or type(occurrence) is not int
                or occurrence in terminal_occurrences
            ):
                continue
            payload = record.get("input")
            work = payload.get("work") if isinstance(payload, dict) else None
            if not isinstance(work, dict):
                raise TypeError("V5 readiness Activity request has no strict work payload")
            operation = work.get("op")
            matches = []
            for admitted in self.truth.admitted:
                authority = admitted.authority
                if (
                    isinstance(operation, str)
                    and authority.lifecycle == "active"
                    and authority.mergeable
                    and authority.head == work.get("head")
                    and authority.base == work.get("base")
                    and authority.policy == work.get("policy")
                    and authority.strict_base is work.get("strict_base")
                    and authority.base_current is work.get("base_current")
                    and authority not in matches
                ):
                    matches.append(authority)
            if not isinstance(operation, str) or len(matches) != 1:
                raise AssertionError("V5 readiness Activity request has no unique independently admitted authority")
            self.truth.bind_effect_authority("readiness", operation, matches[0])

    def drop(self, generation: _Generation) -> None:
        self._dropped.append(weakref.ref(generation))
        generation.client.close()
        generation.host.abort()

    def close(self, generation: _Generation) -> None:
        generation.client.close()
        generation.host.close()

    def dropped_generations_alive(self) -> int:
        return sum(reference() is not None for reference in self._dropped)


class ReadinessChecker:
    """Compare independent expected facts with V5's durable grant and effects."""

    identity = CHECKER_IDENTITY
    request = ObservationRequest(name="readiness.state", payload={})

    def check(self, observation: Observation) -> CheckResult:
        state = cast(dict[str, JsonValue], observation.value)
        expected = cast(dict[str, JsonValue], state["expected"])
        actual = cast(dict[str, JsonValue], state["actual"])
        host = cast(dict[str, JsonValue], state["host"])
        provider = cast(dict[str, JsonValue], state["provider"])
        effects = cast(list[dict[str, JsonValue]], provider["effects"])
        operations = Counter(cast(str, item["operation"]) for item in effects)
        duplicate = sorted(operation for operation, count in operations.items() if count > 1)
        collisions = cast(list[str], provider["collisions"])
        custody_actions = cast(list[dict[str, JsonValue]], provider["custody_actions"])
        custody_mismatches = [
            {"expected": action["expected"], "observed": action["observed"]}
            for action in custody_actions
            if action["expected"] != action["observed"]
        ]
        terminal_operations = cast(list[str], state["terminal_operations"])
        duplicate_terminals = sorted(
            operation for operation, count in Counter(terminal_operations).items() if count > 1
        )
        motus = cast(dict[str, JsonValue], state["motus"])
        terminal_overrun = cast(int, motus["terminals"]) > cast(int, motus["requests"])
        violations = cast(list[JsonValue], expected["violations"])
        work = cast(dict[str, JsonValue], state["work"])
        facts = cast(dict[str, JsonValue], state["facts"])
        authority = cast(dict[str, JsonValue], facts["authority"])
        authority_lag = authority["admitted"] != authority["provider"]
        unloaded = host["snapshot"] is None and work["unloaded_application"] is True
        snapshot = host["snapshot"]
        admitted = authority["admitted"]
        snapshot_parity = unloaded or self._snapshot_matches(admitted, snapshot)
        provider_authority = authority["provider"]
        observed_readiness = self._current_readiness(effects, provider_authority, snapshot)
        actual_parity = actual["readiness_published"] == observed_readiness
        progress_disclosed = self._progress_disclosed(work, observation.instant)
        readiness_parity = observed_readiness == expected["ready"] or (
            expected["ready"] is True and not observed_readiness and progress_disclosed
        )
        timer_mismatches = self._timer_custody_mismatches(state)
        timer_custody_parity = not timer_mismatches or progress_disclosed
        git_mismatches = self._git_custody_mismatches(state, progress_disclosed)
        git_custody_parity = not git_mismatches
        neutral_host_verdict = host["ready"] is None
        ready_parity = readiness_parity and actual_parity and neutral_host_verdict
        parity = ready_parity and snapshot_parity and timer_custody_parity and git_custody_parity
        retained = bounded_json(state, PROFILE_LIMITS["observation_bytes"], "checker observation").decode()
        sensitive = [
            label
            for label, value in {
                "client_id": "readiness-world-client",
                "private_key": "readiness-world-private-key",
                "webhook_secret": WEBHOOK_SECRET,
            }.items()
            if value in retained
        ]
        passed = (
            parity
            and not custody_mismatches
            and not duplicate
            and not collisions
            and not duplicate_terminals
            and not terminal_overrun
            and not sensitive
            and not violations
        )
        return CheckResult(
            passed=passed,
            detail={
                "parity": parity,
                "ready_parity": ready_parity,
                "snapshot_parity": snapshot_parity,
                "timer_custody_parity": timer_custody_parity,
                "timer_custody_mismatches": timer_mismatches,
                "git_custody_parity": git_custody_parity,
                "git_custody_mismatches": git_mismatches,
                "authority_lag": authority_lag,
                "expected_ready": expected["ready"],
                "readiness_published": observed_readiness,
                "progress_disclosed": progress_disclosed,
                "actual_parity": actual_parity,
                "neutral_host_verdict": neutral_host_verdict,
                "custody_action_mismatches": custody_mismatches,
                "duplicate_acceptance": duplicate,
                "effect_identity_collisions": collisions,
                "duplicate_terminal_projection": duplicate_terminals,
                "terminal_overrun": terminal_overrun,
                "sensitive_values": sensitive,
                "violations": violations,
            },
        )

    @staticmethod
    def _git_custody_mismatches(state: dict[str, JsonValue], progress_disclosed: bool) -> list[dict[str, JsonValue]]:
        provider = cast(dict[str, JsonValue], state["provider"])
        publications = cast(list[dict[str, JsonValue]], provider["git_publications"])
        admitted_recoveries = cast(list[dict[str, JsonValue]], provider["admitted_recoveries"])
        custody = cast(dict[str, JsonValue], state["git_custody"])
        requests = cast(list[dict[str, JsonValue]], custody["requests"])
        terminals = cast(list[dict[str, JsonValue]], custody["terminals"])
        mismatches: list[dict[str, JsonValue]] = []
        operations = Counter(cast(str, publication["operation"]) for publication in publications)
        for operation, count in sorted(operations.items()):
            if count > 1:
                mismatches.append({"operation": operation, "field": "acceptances", "expected": 1, "observed": count})
        for publication in publications:
            operation = cast(str, publication["operation"])
            authority = cast(dict[str, JsonValue], publication["authority"])
            recovery_identities = [
                recovery["identity"] for recovery in admitted_recoveries if recovery["operation"] == operation
            ]
            if publication["recovered"] and publication["recovery_identity"] not in recovery_identities:
                mismatches.append(
                    {
                        "operation": operation,
                        "field": "recovery_authorization",
                        "expected": recovery_identities,
                        "observed": publication["recovery_identity"],
                    }
                )
            matching_requests = [request for request in requests if request["operation"] == operation]
            if not matching_requests:
                mismatches.append({"operation": operation, "field": "request", "expected": True, "observed": False})
            if publication["expected_head"] != authority["head"]:
                mismatches.append(
                    {
                        "operation": operation,
                        "field": "expected_head",
                        "expected": authority["head"],
                        "observed": publication["expected_head"],
                    }
                )
            for request in matching_requests:
                for authority_field in ("head", "base"):
                    expected = authority[authority_field]
                    if request[authority_field] != expected:
                        mismatches.append(
                            {
                                "operation": operation,
                                "field": f"request_{authority_field}",
                                "expected": expected,
                                "observed": request[authority_field],
                            }
                        )
            if progress_disclosed:
                continue
            matching = [terminal for terminal in terminals if terminal["operation"] == operation]
            expected_variants = (
                ["FaultM", "Pushed"]
                if publication["response_lost"] and publication["recovered"]
                else ["FaultM"]
                if publication["response_lost"]
                else ["Pushed"]
            )
            observed_variants = [terminal["variant"] for terminal in matching]
            if observed_variants != expected_variants:
                mismatches.append(
                    {
                        "operation": operation,
                        "field": "terminal",
                        "expected": cast(list[JsonValue], expected_variants),
                        "observed": observed_variants,
                    }
                )
            expected_requests = len(expected_variants)
            if len(matching_requests) != expected_requests:
                mismatches.append(
                    {
                        "operation": operation,
                        "field": "requests",
                        "expected": expected_requests,
                        "observed": len(matching_requests),
                    }
                )
            for terminal in matching:
                expected_head = publication["result_head"] if terminal["variant"] == "Pushed" else None
                if terminal["result_head"] != expected_head:
                    mismatches.append(
                        {
                            "operation": operation,
                            "field": "terminal_result_head",
                            "expected": expected_head,
                            "observed": terminal["result_head"],
                        }
                    )
        return mismatches

    @staticmethod
    def _timer_custody_mismatches(state: dict[str, JsonValue]) -> list[dict[str, JsonValue]]:
        expected = cast(list[dict[str, JsonValue]], state["timer_expectations"])
        custody = cast(dict[str, JsonValue], state["timer_custody"])
        actual = cast(list[dict[str, JsonValue]], custody["timers"])
        actual_by_identity = {cast(str, timer["identity"]): timer for timer in actual}
        mismatches: list[dict[str, JsonValue]] = []
        compatible_states = {
            "scheduled": {"armed"},
            "due": {"armed", "matured"},
            "acknowledged": {"matured"},
            "canceled": {"cancelled", "superseded", "retired"},
        }
        for timer in expected:
            identity = cast(str, timer["identity"])
            observed = actual_by_identity.get(identity)
            if observed is None:
                mismatches.append({"identity": identity, "field": "presence", "expected": True, "observed": False})
                continue
            for attribute in ("incarnation", "sequence", "head", "due_at", "matured_at"):
                if observed[attribute] != timer[attribute]:
                    mismatches.append(
                        {
                            "identity": identity,
                            "field": attribute,
                            "expected": timer[attribute],
                            "observed": observed[attribute],
                        }
                    )
            status = cast(str, timer["status"])
            if observed["state"] not in compatible_states[status]:
                mismatches.append(
                    {
                        "identity": identity,
                        "field": "status",
                        "expected": status,
                        "observed": observed["state"],
                    }
                )
            if status == "acknowledged" and observed["maturity_delivered"] is not True:
                mismatches.append(
                    {
                        "identity": identity,
                        "field": "maturity_delivered",
                        "expected": True,
                        "observed": observed["maturity_delivered"],
                    }
                )
        expected_identities = {cast(str, timer["identity"]) for timer in expected}
        for identity in sorted(set(actual_by_identity) - expected_identities):
            mismatches.append({"identity": identity, "field": "presence", "expected": False, "observed": True})

        operations = cast(list[dict[str, JsonValue]], custody["operations"])
        generations = [operation["generation"] for operation in operations]
        expected_generations = list(range(1, len(operations) + 1))
        if generations != expected_generations:
            mismatches.append(
                {
                    "identity": "timer-operations",
                    "field": "generations",
                    "expected": expected_generations,
                    "observed": generations,
                }
            )
        for operation in operations:
            if operation["acknowledged"] is not True:
                mismatches.append(
                    {
                        "identity": operation["identity"],
                        "field": "acknowledged",
                        "expected": True,
                        "observed": operation["acknowledged"],
                    }
                )
        return mismatches

    @staticmethod
    def _snapshot_matches(admitted: JsonValue, snapshot: JsonValue) -> bool:
        if admitted is None:
            return snapshot is None
        if type(admitted) is not dict or type(snapshot) is not dict:
            return False
        lifecycle = admitted["lifecycle"]
        if lifecycle in {"closed", "merged"}:
            return snapshot.get("phase") == "terminal"
        expected_phase = "quiescent" if lifecycle == "draft" else "running"
        return (
            snapshot.get("phase") == expected_phase
            and snapshot.get("head") == admitted["head"]
            and snapshot.get("base_head") == admitted["base"]
            and snapshot.get("policy_digest") == admitted["policy"]
        )

    @staticmethod
    def _current_readiness(
        effects: list[dict[str, JsonValue]],
        provider_authority: JsonValue,
        snapshot: JsonValue,
    ) -> bool:
        if type(provider_authority) is not dict or type(snapshot) is not dict or snapshot.get("phase") != "running":
            return False
        incarnation = snapshot.get("incarnation")
        if type(incarnation) is not int:
            return False
        operation = f"ready:{provider_authority['head']}:i{incarnation}"
        return any(
            effect["kind"] == "readiness"
            and effect["operation"] == operation
            and effect["authority"] == provider_authority
            and effect["provider_authority_at_acceptance"] == provider_authority
            for effect in effects
        )

    @staticmethod
    def _progress_disclosed(work: dict[str, JsonValue], instant: int) -> bool:
        due = work["runnable_due"]
        due_now = type(due) in {int, float} and math.ceil(cast(float, due)) <= instant
        return any(
            (
                work["pending_custody"] is True,
                work["unresolved_activity"] is True,
                work["unloaded_application"] is True,
                due_now,
            )
        )


class ReadinessTimeline:
    """Business-readable imperative facade over one revocable Petrus Timeline."""

    def __init__(self, owner: ReadinessWorld, timeline: Timeline) -> None:
        self._owner, self._timeline = owner, timeline

    def command(self, name: str, payload: object) -> ApplyResult:
        return self._timeline.command(name, payload)

    def pending(self) -> bool:
        self._require_current_generation()
        return bool(self._owner.world.pending())

    def step(self) -> ApplyResult:
        self._require_current_generation()
        return self._owner.world.step().result

    def _require_current_generation(self) -> None:
        if self._timeline.generation != self._owner.world.generation:
            raise StaleGeneration(f"readiness Timeline generation {self._timeline.generation} is stale")

    def set_pull_request(
        self,
        *,
        head: str,
        base: str,
        policy: str,
        lifecycle: str,
        strict_base: bool,
        base_current: bool,
        mergeable: bool,
    ) -> ApplyResult:
        authority = AuthorityClaim(
            44, 31, 7, head, base, policy, cast(Any, lifecycle), strict_base, base_current, mergeable
        )
        return self.command("readiness.github.pr.set", {"subject": SUBJECT, "authority": authority.dump()})

    def set_ci(self, *, head: str, required_checks: tuple[str, ...], checks: dict[str, str]) -> ApplyResult:
        values = [{"name": name, "run": 101, "attempt": 1, "status": status} for name, status in sorted(checks.items())]
        return self.command(
            "readiness.github.ci.set",
            {"subject": SUBJECT, "head": head, "required_checks": list(required_checks), "checks": values},
        )

    def set_review(self, *, head: str, status: str, findings: tuple[dict[str, object], ...] = ()) -> ApplyResult:
        return self.command(
            "readiness.github.review.set",
            {"subject": SUBJECT, "head": head, "status": status, "findings": list(findings)},
        )

    def set_human_comment(self, *, comment: int, fixture: str, author: str = "author") -> ApplyResult:
        return self.command(
            "readiness.github.human.comment",
            {
                "subject": SUBJECT,
                "comment": comment,
                "author": author,
                "fixture": fixture,
                "digest": strict_digest({"fixture": fixture}),
            },
        )

    def set_agent_terminal(self, *, operation: str, fixture: str, status: str, attempt: int = 1) -> ApplyResult:
        return self.command(
            "readiness.agent.terminal",
            {
                "subject": SUBJECT,
                "operation": operation,
                "attempt": attempt,
                "status": status,
                "fixture": fixture,
                "digest": strict_digest({"fixture": fixture, "status": status}),
            },
        )

    def emit_webhook(self, event: str, *, action: str) -> str:
        self._owner._delivery += 1
        delivery = str(uuid.UUID(int=self._owner._delivery))
        fixture = f"{event}:{action}"
        self.command(
            "readiness.github.webhook.emit",
            {
                "subject": SUBJECT,
                "delivery": delivery,
                "event": event,
                "fixture": fixture,
                "digest": strict_digest({"event": event, "fixture": fixture}),
            },
        )
        return delivery

    def deliver_webhook(self, delivery: str) -> ApplyResult:
        return self.command("readiness.github.webhook.deliver", {"delivery": delivery})

    def lose_effect_response(self, kind: str) -> None:
        self.fault_effect(kind, "after_acceptance_before_response")

    def fault_effect(self, kind: str, cut: str, *, occurrence: int = 1) -> None:
        self._timeline.activate_fault(
            "readiness.github.effect",
            f"effect:{kind}",
            occurrence=occurrence,
            disposition=FaultDisposition.RAISE,
            payload={"cut": cut},
        )

    def fault_git_publication(self, operation: str, cut: str, *, occurrence: int = 1) -> None:
        self._timeline.activate_fault(
            "readiness.git.publish",
            f"git:{operation}",
            occurrence=occurrence,
            disposition=FaultDisposition.RAISE,
            payload={"cut": cut},
        )

    def advance_time(self, seconds: int) -> ApplyResult:
        result = self.command("readiness.time.advance", {"seconds": seconds})
        target = cast(int, cast(dict[str, JsonValue], result.value)["target"])
        while self._owner.world.instant < target:
            self._owner.world.step()
        return result

    def reveal_effect(self, operation: str) -> ApplyResult:
        return self.command("readiness.github.effect.reveal", {"subject": SUBJECT, "operation": operation})

    def observe(self) -> Observation:
        return self._timeline.observe("readiness.state", {})

    def run_until(self, name: str, predicate) -> Observation:
        del name  # Petrus diagnostics retain the normalized observation and journal tail.
        return self._timeline.run_until(
            "readiness.state",
            lambda observation: predicate(cast(dict[str, JsonValue], observation.value)),
            payload={},
        )

    def crash(self, cut: str) -> None:
        self._timeline.crash(cut)

    def begin_fair(self) -> None:
        self._timeline.begin_fair()

    def converge(self) -> Observation:
        self.begin_fair()
        while self._owner.world.pending():
            self._owner.world.step()
        observation = self.observe()
        expected = cast(dict[str, JsonValue], cast(dict[str, JsonValue], observation.value)["expected"])
        disposition = expected["disposition"]
        ending = (
            Disposition.CONVERGED
            if disposition in {"ready", "terminal"}
            else Disposition.QUARANTINED
            if disposition == "quarantined"
            else Disposition.QUIESCENT
        )
        self._timeline.finish(ending)
        return observation


class ReadinessWorld:
    """Convenience owner for one deterministic non-sharded V5 host scenario."""

    def __init__(self, root: Path, budget: BudgetV4 = DEFAULT_BUDGET, *, seed: int | None = None) -> None:
        self.profile = ReadinessScenarioProfile(root)
        # Petrus stores generations opaquely as ``object``; its registry makes
        # the same safe erasure after checking the profile identity.
        self.world = World(cast(Any, self.profile), budget, checkers=(ReadinessChecker(),), seed=seed)
        self._delivery = 0

    def timeline(self) -> ReadinessTimeline:
        return ReadinessTimeline(self, self.world.timeline())

    def restart(self) -> ReadinessTimeline:
        self.world.restart()
        return self.timeline()

    def artifact(self, scenario_id: str) -> ScenarioArtifact:
        return cast(ScenarioArtifact, self.world.artifact(scenario_id))

    def close(self) -> None:
        self.world.close()

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *_errors: object) -> None:
        self.close()


def replay_readiness(artifact: ScenarioArtifact, root: Path) -> ReplayResult:
    registry = ScenarioRegistry()
    registry.register_profile(ReadinessScenarioProfile(root))
    registry.register_checker(ReadinessChecker())
    return cast(ReplayResult, replay(artifact, registry))


def _config(root: Path) -> HostConfig:
    return HostConfig(
        app_id=17,
        app_slug="hamsterdan-test",
        client_id="readiness-world-client",
        account_id=23,
        account_login="Owner",
        allowed_repositories=frozenset({(31, "owner/repo")}),
        state_path=root,
        private_key="readiness-world-private-key",
        webhook_secret=WEBHOOK_SECRET,
    )


def _history_records(root: Path) -> list[dict[str, JsonValue]]:
    path = root / "applications" / "44" / "31" / "7" / "history.jsonl"
    if not path.is_file():
        return []
    return [cast(dict[str, JsonValue], json.loads(line)) for line in path.read_text().splitlines() if line]


def _history(root: Path) -> tuple[dict[str, JsonValue], list[str]]:
    records = _history_records(root)
    requested: dict[int, str] = {}
    terminal: set[int] = set()
    summary: list[dict[str, JsonValue]] = []
    kinds: Counter[str] = Counter()
    for record in records:
        kind = str(record.get("record", ""))
        kinds[kind] += 1
        occurrence = record.get("occurrence")
        operation = None
        if kind == "ActivityRequested" and type(occurrence) is int:
            payload = record.get("input")
            work = payload.get("work", payload.get("command")) if isinstance(payload, dict) else None
            operation = work.get("operation") if isinstance(work, dict) else None
            if isinstance(operation, str):
                requested[occurrence] = operation
        if kind in {"ActivityCompleted", "ActivityFailed", "ActivityTerminalQuarantined"} and type(occurrence) is int:
            terminal.add(occurrence)
        summary.append(
            {
                "record": kind,
                "occurrence": occurrence if type(occurrence) is int else None,
                "operation": operation,
            }
        )
    return (
        {
            "records": len(records),
            "by_kind": dict(sorted(kinds.items())),
            "digest": strict_digest(records),
            "tail": cast(list[JsonValue], summary[-32:]),
        },
        sorted(requested[item] for item in terminal & requested.keys()),
    )


def _git_custody(root: Path) -> dict[str, JsonValue]:
    """Project V5 Git requests and terminals from canonical public History."""

    requests: list[dict[str, JsonValue]] = []
    terminals: list[dict[str, JsonValue]] = []
    requested: dict[int, str] = {}
    for record in _history_records(root):
        occurrence = record.get("occurrence")
        if record.get("record") == "ActivityRequested" and record.get("activity") == "git_gate":
            payload = record.get("input")
            work = payload.get("work") if isinstance(payload, dict) else None
            if type(occurrence) is not int or not isinstance(work, dict):
                raise RuntimeError("V5 Git History request is malformed")
            operation = work.get("op_key")
            if not isinstance(operation, str):
                raise RuntimeError("V5 Git History request has no strict operation key")
            requested[occurrence] = operation
            requests.append(
                {
                    "occurrence": occurrence,
                    "operation": operation,
                    "head": work.get("head"),
                    "base": work.get("base"),
                }
            )
            continue
        if record.get("record") not in {"ActivityCompleted", "ActivityFailed", "ActivityTerminalQuarantined"}:
            continue
        if type(occurrence) is not int or occurrence not in requested:
            continue
        result = record.get("result")
        variant = result.get("$variant") if isinstance(result, dict) else record.get("record")
        terminals.append(
            {
                "occurrence": occurrence,
                "operation": requested[occurrence],
                "variant": variant,
                "result_head": result.get("new_head") if isinstance(result, dict) else None,
            }
        )
    return {"requests": requests, "terminals": terminals}


def _timer_custody(root: Path) -> dict[str, JsonValue]:
    """Detach V5 timer custody without exposing a Net marking or live store."""

    operations: list[JsonValue] = []
    timers: list[JsonValue] = []
    for path in sorted((root / "applications").glob("*/*/*/timers.sqlite3")):
        with closing(sqlite3.connect(path)) as database:
            names = {str(row[0]) for row in database.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            if {"v5_timer_operations", "v5_timers"} - names:
                raise RuntimeError("readiness timer custody store is incomplete")
            for operation, generation, applied_at, acknowledged in database.execute(
                "SELECT operation,generation,applied_at_us,ack_delivered"
                " FROM v5_timer_operations ORDER BY generation,operation"
            ):
                operations.append(
                    {
                        "identity": str(operation),
                        "generation": int(generation),
                        "applied_at": _whole_seconds(applied_at, "timer operation instant"),
                        "acknowledged": acknowledged == 1,
                    }
                )
            for row in database.execute(
                "SELECT timer_id,incarnation,sequence,head,due_at_us,state,matured_at_us,maturity_delivered"
                " FROM v5_timers ORDER BY incarnation,sequence,timer_id"
            ):
                identity, incarnation, sequence, head, due_at, state, matured_at, delivered = row
                timers.append(
                    {
                        "identity": str(identity),
                        "incarnation": int(incarnation),
                        "sequence": int(sequence),
                        "head": str(head),
                        "due_at": _whole_seconds(due_at, "timer deadline"),
                        "state": str(state),
                        "matured_at": None
                        if matured_at is None
                        else _whole_seconds(matured_at, "timer maturity instant"),
                        "maturity_delivered": delivered == 1,
                    }
                )
    return {"operations": operations, "timers": timers}


def _whole_seconds(value: object, label: str) -> int:
    if type(value) is not int or value % 1_000_000:
        raise RuntimeError(f"{label} is not a deterministic whole second")
    return value // 1_000_000


def _sqlite_retained(root: Path) -> tuple[int, int, dict[str, int]]:
    """Count durable SQLite rows, scalar bytes, and named pending subsets."""
    count = 0
    encoded_bytes = 0
    counts: Counter[str] = Counter()
    for path in sorted(root.rglob("*.sqlite3")):
        if not path.is_file():
            continue
        with closing(sqlite3.connect(path)) as database:
            tables = [
                str(row[0])
                for row in database.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
                )
            ]
            for table in tables:
                quoted = table.replace('"', '""')
                columns = [str(row[1]) for row in database.execute(f'PRAGMA table_info("{quoted}")')]
                scalar_bytes = "+".join(
                    f'length(CAST(quote("{column.replace(chr(34), chr(34) * 2)}") AS BLOB))' for column in columns
                )
                row_count, data_bytes = database.execute(
                    f'SELECT COUNT(*),COALESCE(SUM({scalar_bytes}),0) FROM "{quoted}"'
                ).fetchone()
                rows = int(row_count)
                count += rows
                counts[table] += rows
                encoded_bytes += len(str(path.relative_to(root)).encode()) + len(table.encode()) + int(data_bytes)
                if table == "inbox":
                    counts["inbox.pending"] += _where_count(database, quoted, "status='pending'")
                elif table == "v5_timer_operations":
                    counts["v5_timer_operations.pending_ack"] += _where_count(
                        database,
                        quoted,
                        "ack_delivered=0",
                    )
                elif table == "v5_timers":
                    counts["v5_timers.pending_maturity"] += _where_count(
                        database,
                        quoted,
                        "state='matured' AND maturity_delivered=0",
                    )
                    counts["v5_timers.armed"] += _where_count(database, quoted, "state='armed'")
            if {
                "impetus_local_dispatch_tasks",
                "impetus_local_dispatch_terminals",
                "impetus_local_dispatch_cancellations",
            } <= set(tables):
                counts["impetus_local_dispatch.pending"] += int(
                    database.execute(
                        "SELECT COUNT(*) FROM impetus_local_dispatch_tasks AS task"
                        " LEFT JOIN impetus_local_dispatch_terminals AS terminal"
                        " USING(instance,occurrence)"
                        " LEFT JOIN impetus_local_dispatch_cancellations AS cancellation"
                        " USING(instance,occurrence)"
                        " WHERE terminal.occurrence IS NULL AND cancellation.occurrence IS NULL"
                    ).fetchone()[0]
                )
    return count, encoded_bytes, dict(counts)


def _where_count(database: sqlite3.Connection, quoted_table: str, where: str) -> int:
    return int(database.execute(f'SELECT COUNT(*) FROM "{quoted_table}" WHERE {where}').fetchone()[0])


def _motus(root: Path) -> dict[str, JsonValue]:
    path = root / "activity-dispatch.sqlite3"
    if not path.is_file():
        return {"requests": 0, "terminals": 0, "cancellations": 0}
    with closing(sqlite3.connect(path)) as database:
        names = {str(row[0]) for row in database.execute("SELECT name FROM sqlite_master WHERE type='table'")}

        def count(table: str) -> int:
            return 0 if table not in names else int(database.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])

        return {
            "requests": count("impetus_local_dispatch_tasks"),
            "terminals": count("impetus_local_dispatch_terminals"),
            "cancellations": count("impetus_local_dispatch_cancellations"),
        }


__all__ = [
    "BASE",
    "CHECKER_IDENTITY",
    "DEFAULT_BUDGET",
    "HEAD",
    "PROFILE_IDENTITY",
    "PROFILE_LIMITS",
    "PROFILE_RESOURCE_LIMITS",
    "READINESS_POLICY_DIGEST",
    "REMINDER_DELAY",
    "ReadinessChecker",
    "ReadinessScenarioProfile",
    "ReadinessTimeline",
    "ReadinessWorld",
    "replay_readiness",
]
