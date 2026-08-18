"""Deterministic external world around the real production HostService.

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
import time
import uuid
import weakref
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Self, cast

from fastapi.testclient import TestClient
from petrus.testing.dst import (
    ApplyResult,
    Budget,
    CheckResult,
    Command,
    Disposition,
    Fault,
    FaultDisposition,
    GenerationStart,
    Observation,
    ObservationRequest,
    ReplayResult,
    ScenarioArtifact,
    ScenarioContext,
    ScenarioRegistry,
    ScheduledCommand,
    Timeline,
    World,
    replay,
)
from pydantic import JsonValue

from hamsterdan.github_app.config import HostConfig
from hamsterdan.host.agenticus import AgentRouteStore, compose_agent
from hamsterdan.host.api import create_app
from hamsterdan.host.service import HostService
from hamsterdan.host.topology import PRODUCTION
from hamsterdan.testing.readiness import (
    AuthorityClaim,
    AuthorityFacts,
    CheckFacts,
    CiFacts,
    EffectObligation,
    HumanFacts,
    ReadinessFacts,
    ReadinessModel,
    ReviewFacts,
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
    PROFILE_IDENTITY,
    PROFILE_LIMITS,
    READINESS_POLICY_DIGEST,
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
    """Petrus profile over one opaque real production HostService generation."""

    identity = PROFILE_IDENTITY

    def __init__(self, root: Path) -> None:
        self.root = root
        self.truth = ReadinessProviderTruth()
        self._dropped: list[weakref.ReferenceType[_Generation]] = []
        self._started_at = time.monotonic()
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
            if payload["digest"] != strict_digest({"fixture": fixture}):
                raise ValueError("comment fixture digest does not match")
        elif command.name == "readiness.agent.terminal":
            bounded_text(payload["operation"], "agent operation", pattern=NAME)
            if type(payload["attempt"]) is not int or payload["attempt"] <= 0:
                raise ValueError("agent attempt must be positive")
            if payload["status"] not in {"clear", "blocking", "unable", "changed", "unchanged"}:
                raise ValueError("unsupported agent terminal status")
            fixture = bounded_text(payload["fixture"], "agent fixture", pattern=NAME)
            if fixture not in {"review", "conversation", "coding"}:
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
        composition = compose_agent()
        routes.activate(composition, self.root / "applications")
        context_holder: dict[str, ScenarioContext | None] = {"value": None}

        def transport_factory(_client: object) -> ProviderTransport:
            return ProviderTransport(self.truth, context_holder)

        host = HostService(
            _config(self.root),
            clients=cast(Any, ProviderClients()),
            runner=cast(Any, AgentRunner(self.truth)),
            agent_composition=composition,
            agent_routes=routes,
            readiness_composition=PRODUCTION,
            reminder_delay=86_400,
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
            self._assert_bounds(generation)
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
            self.truth.agent_terminal = {
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
            return {"comment": payload["comment"]}, "applied"
        if name == "readiness.agent.terminal":
            self.truth.agent_terminal = {
                "kind": cast(str, payload["fixture"]),
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
            emitted = _Emitted(delivery, event, action, self.truth.authority)
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
            if candidate is not None:
                self.truth.admitted.append(candidate)
            observed = generation.host.process_one()
            expected = None if candidate is None else {"delivery": candidate.delivery, "disposition": "completed"}
            observed_value = (
                None if observed is None else {"delivery": observed.delivery_id, "disposition": observed.disposition}
            )
            self.truth.custody_actions.append({"expected": expected, "observed": observed_value})
            return {"custody": observed_value}, "applied" if observed is not None else "refused_expected"
        if name == "readiness.host.activity_one":
            processed = generation.host.run_one_activity()
            return {"processed": processed}, "applied" if processed else "refused_expected"
        if name == "readiness.host.drive_one":
            processed = generation.host.run_due(limit=1)
            return {"processed": processed}, "applied" if processed else "refused_expected"
        if name == "readiness.host.reconcile_one":
            processed = generation.host.reconcile_one("dst")
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
            ("readiness.host.activity_one", context.now(), cast(bool, state["unresolved_activity"])),
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

    def observe(
        self,
        generation: _Generation,
        request: ObservationRequest,
        context: ScenarioContext,
    ) -> JsonValue:
        del context
        if request.name != "readiness.state" or request.payload not in (None, {}):
            raise ValueError("readiness profile exposes only readiness.state without parameters")
        return self._state(generation)

    def _state(self, generation: _Generation) -> dict[str, JsonValue]:
        custody = {delivery: generation.host.custody.status(delivery) for delivery in sorted(self.truth.emitted)}
        facts = self._facts()
        expected = ReadinessModel().evaluate(facts)
        host = generation.host.subject_state(44, 31, 7)
        history, terminal_operations = _history(self.root)
        state: dict[str, JsonValue] = {
            "subject": SUBJECT,
            "expected": expected.dump(),
            "facts": facts.dump(),
            "host": {"ready": False, "snapshot": None} if host is None else cast(dict[str, JsonValue], host),
            "provider": self.truth.observation(),
            "custody": cast(dict[str, JsonValue], custody),
            "history": history,
            "motus": _motus(self.root),
            "terminal_operations": terminal_operations,
            "work": cast(dict[str, JsonValue], generation.host.work_state()),
            "bounds": {
                "limits": cast(dict[str, JsonValue], PROFILE_LIMITS),
                "usage": self._usage(generation),
            },
        }
        self._assert_bounds(
            generation,
            observation_bytes=len(bounded_json(state, PROFILE_LIMITS["observation_bytes"], "readiness observation")),
        )
        return state

    def _usage(self, generation: _Generation) -> dict[str, JsonValue]:
        custody = generation.host.custody.counts()
        motus = _motus(self.root)
        history_bytes = sum(
            path.stat().st_size for path in (self.root / "applications").glob("*/*/*/history.jsonl") if path.is_file()
        )
        return {
            "authority_generations": len(self.truth.authorities),
            "provider_truth_changes": self.truth.provider_truth_changes,
            "webhook_emissions": len(self.truth.emitted),
            "delivery_attempts": sum(self.truth.delivery_attempts.values()),
            "checks": len(self.truth.checks),
            "reviews": len(self.truth.human_reviews),
            "findings": len(self.truth.findings),
            "comments": len(self.truth.comments),
            "threads": len(self.truth.review_threads),
            "agent_operations": len(self.truth.agent_calls),
            "provider_calls": len(self.truth.calls),
            "effects": len(self.truth.effects),
            "host_followups": self._host_followups,
            "pending_custody": int(custody.get("pending", 0)),
            "runnable": generation.host.runnable.count(),
            "dispatch_entries": sum(cast(int, value) for value in motus.values()),
            "history_bytes": history_bytes,
        }

    def _assert_bounds(self, generation: _Generation, *, observation_bytes: int = 0) -> None:
        usage = self._usage(generation)
        for name, value in usage.items():
            limit = PROFILE_LIMITS[name]
            if cast(int, value) > limit:
                raise RuntimeError(f"readiness profile bound {name} exhausted at {limit}")
        if observation_bytes > PROFILE_LIMITS["observation_bytes"]:
            raise RuntimeError(
                f"readiness profile bound observation_bytes exhausted at {PROFILE_LIMITS['observation_bytes']}"
            )
        if time.monotonic() - self._started_at > PROFILE_LIMITS["wall_watchdog_seconds"]:
            raise RuntimeError(
                f"readiness profile wall watchdog exhausted at {PROFILE_LIMITS['wall_watchdog_seconds']} seconds"
            )

    def _facts(self) -> ReadinessFacts:
        admitted_events = self.truth.admitted
        admitted = admitted_events[-1].authority if admitted_events else None
        generations = 0
        prior: AuthorityClaim | None = None
        for emitted in admitted_events:
            if prior is None or emitted.authority.head != prior.head:
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
        effects = tuple(
            EffectObligation(
                kind=cast(
                    Any,
                    "findings"
                    if effect.kind == "finding"
                    else effect.kind
                    if effect.kind in {"dashboard", "conversation", "readiness", "rerun"}
                    else "dashboard",
                ),
                operation=effect.operation,
                authority=effect.authority,
                content_digest=effect.content_digest,
                status="settled" if effect.recovered else "accepted",
                blocks_readiness=False,
            )
            for effect in self.truth.effects
        )
        record_identities = tuple(f"github-delivery:{event.delivery}" for event in admitted_events)
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
            effects=effects,
        )

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
    """Compare independent expected facts with the detached real-host verdict."""

    identity = CHECKER_IDENTITY
    request = ObservationRequest(name="readiness.state", payload={})

    def check(self, observation: Observation) -> CheckResult:
        state = cast(dict[str, JsonValue], observation.value)
        expected = cast(dict[str, JsonValue], state["expected"])
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
        parity = host["ready"] == expected["ready"] or (
            host["snapshot"] is None and work["unloaded_application"] is True
        )
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
                "expected_ready": expected["ready"],
                "host_ready": host["ready"],
                "custody_action_mismatches": custody_mismatches,
                "duplicate_acceptance": duplicate,
                "effect_identity_collisions": collisions,
                "duplicate_terminal_projection": duplicate_terminals,
                "terminal_overrun": terminal_overrun,
                "sensitive_values": sensitive,
                "violations": violations,
            },
        )


class ReadinessTimeline:
    """Business-readable imperative facade over one revocable Petrus Timeline."""

    def __init__(self, owner: ReadinessWorld, timeline: Timeline) -> None:
        self._owner, self._timeline = owner, timeline

    def command(self, name: str, payload: object) -> ApplyResult:
        return self._timeline.command(name, payload)

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
    """Convenience owner for one deterministic production-host scenario."""

    def __init__(self, root: Path, budget: Budget = DEFAULT_BUDGET) -> None:
        self.profile = ReadinessScenarioProfile(root)
        # Petrus stores generations opaquely as ``object``; its registry makes
        # the same safe erasure after checking the profile identity.
        self.world = World(cast(Any, self.profile), budget, checkers=(ReadinessChecker(),))
        self._delivery = 0

    def timeline(self) -> ReadinessTimeline:
        return ReadinessTimeline(self, self.world.timeline())

    def restart(self) -> ReadinessTimeline:
        self.world.restart()
        return self.timeline()

    def artifact(self, scenario_id: str) -> ScenarioArtifact:
        return self.world.artifact(scenario_id)

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
    return replay(artifact, registry)


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


def _history(root: Path) -> tuple[list[JsonValue], list[str]]:
    records = _history_records(root)
    requested: dict[int, str] = {}
    terminal: set[int] = set()
    summary: list[JsonValue] = []
    for record in records:
        kind = str(record.get("record", ""))
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
    return summary, sorted(requested[item] for item in terminal & requested.keys())


def _motus(root: Path) -> dict[str, JsonValue]:
    path = root / "activity-dispatch.sqlite3"
    if not path.is_file():
        return {"requests": 0, "terminals": 0, "cancellations": 0}
    with sqlite3.connect(path) as database:
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
    "READINESS_POLICY_DIGEST",
    "ReadinessChecker",
    "ReadinessScenarioProfile",
    "ReadinessTimeline",
    "ReadinessWorld",
    "replay_readiness",
]
