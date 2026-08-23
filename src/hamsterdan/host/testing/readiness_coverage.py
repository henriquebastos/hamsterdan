"""Deterministic semantic coverage accounting for V5 readiness DST artifacts.

Coverage is evidence accounting, not a score. A dimension is covered only when
one scenario contains its executable adapter, a passed relevant checker, and
the detached semantic outcome. Unsupported DS1 dimensions remain explicit
blocked entries until their application-owned adapters and checkers exist.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from itertools import pairwise
from typing import Literal, Self, cast

from petrus.testing.dst import (
    CheckerIdentity,
    CheckResult,
    CrashOperation,
    ExecuteOperation,
    FairOperation,
    FaultOperation,
    FinishOperation,
    Observation,
    ProfileIdentity,
    ReplayResult,
    RestartOperation,
    ScenarioArtifact,
)
from pydantic import BaseModel, ConfigDict, Field, JsonValue, model_validator

from ._readiness_contract import CHECKER_IDENTITY, PROFILE_IDENTITY

type DimensionName = Literal[
    "authority_movement",
    "lifecycle_movement",
    "duplicate_delivery",
    "timer_lifecycle",
    "provider_response_loss",
    "crash_reconstruction",
    "conversation_effect",
    "coding_effect",
    "git_mutation",
    "git_ambiguity_recovery",
    "fair_convergence",
    "checker_activation",
    "exact_replay",
    "ci_rerun_repair",
    "agent_terminal_fault_cuts",
    "stale_rate_limited_reads",
    "history_dispatch_fault_cuts",
]
type CoverageStatus = Literal["covered", "uncovered", "blocked"]
type AdapterEvidence = Literal[
    "agent.coding_terminal",
    "agent.conversation_terminal",
    "authority.set",
    "fair.begin",
    "generation.crash",
    "generation.restart",
    "git.provider_request",
    "git.recovery_grant",
    "git.response_loss",
    "provider.response_loss",
    "petrus.replay",
    "time.advance",
    "webhook.redelivery",
    "world.accepted_operation",
]
type CheckerEvidence = Literal[
    "petrus.exact_replay",
    "readiness.authority",
    "readiness.fair_boundary",
    "readiness.git_custody",
    "readiness.generation_load",
    "readiness.independent_model",
    "readiness.no_duplicate_effect",
    "readiness.timer_custody",
]
type OutcomeEvidence = Literal[
    "agent.coding_called",
    "agent.conversation_called",
    "authority.generation_moved",
    "checker.passed",
    "crash.cut.authority_lifecycle",
    "crash.cut.git_after_acceptance",
    "crash.cut.git_after_head",
    "crash.cut.git_before_delivery",
    "crash.cut.timer_after_acceptance",
    "crash.cut.timer_after_due",
    "crash.cut.timer_before_due",
    "fair.converged",
    "generation.reloaded",
    "git.accepted",
    "git.faultm_then_pushed",
    "git.recovery_authorized",
    "lifecycle.changed",
    "lifecycle.closed",
    "lifecycle.draft",
    "lifecycle.resumed",
    "provider.response_lost",
    "replay.exact",
    "timer.acknowledged",
    "timer.armed",
    "timer.matured",
    "webhook.duplicate",
]

_DIMENSIONS: tuple[DimensionName, ...] = (
    "authority_movement",
    "lifecycle_movement",
    "duplicate_delivery",
    "timer_lifecycle",
    "provider_response_loss",
    "crash_reconstruction",
    "conversation_effect",
    "coding_effect",
    "git_mutation",
    "git_ambiguity_recovery",
    "fair_convergence",
    "checker_activation",
    "exact_replay",
    "ci_rerun_repair",
    "agent_terminal_fault_cuts",
    "stale_rate_limited_reads",
    "history_dispatch_fault_cuts",
)
_REQUIREMENTS: dict[
    DimensionName,
    tuple[frozenset[AdapterEvidence], frozenset[CheckerEvidence], frozenset[OutcomeEvidence]],
] = {
    "authority_movement": (
        frozenset({"authority.set"}),
        frozenset({"readiness.authority"}),
        frozenset({"authority.generation_moved"}),
    ),
    "lifecycle_movement": (
        frozenset({"authority.set"}),
        frozenset({"readiness.authority"}),
        frozenset({"lifecycle.changed"}),
    ),
    "duplicate_delivery": (
        frozenset({"webhook.redelivery"}),
        frozenset({"readiness.no_duplicate_effect"}),
        frozenset({"webhook.duplicate"}),
    ),
    "timer_lifecycle": (
        frozenset({"time.advance"}),
        frozenset({"readiness.timer_custody"}),
        frozenset({"timer.armed", "timer.matured", "timer.acknowledged"}),
    ),
    "provider_response_loss": (
        frozenset({"provider.response_loss"}),
        frozenset({"readiness.independent_model"}),
        frozenset({"provider.response_lost"}),
    ),
    "crash_reconstruction": (
        frozenset({"generation.crash", "generation.restart"}),
        frozenset({"readiness.generation_load"}),
        frozenset({"generation.reloaded"}),
    ),
    "conversation_effect": (
        frozenset({"agent.conversation_terminal"}),
        frozenset({"readiness.independent_model"}),
        frozenset({"agent.conversation_called"}),
    ),
    "coding_effect": (
        frozenset({"agent.coding_terminal"}),
        frozenset({"readiness.independent_model"}),
        frozenset({"agent.coding_called"}),
    ),
    "git_mutation": (
        frozenset({"git.provider_request"}),
        frozenset({"readiness.git_custody"}),
        frozenset({"git.accepted"}),
    ),
    "git_ambiguity_recovery": (
        frozenset({"git.response_loss", "git.recovery_grant"}),
        frozenset({"readiness.git_custody"}),
        frozenset({"git.faultm_then_pushed", "git.recovery_authorized"}),
    ),
    "fair_convergence": (
        frozenset({"fair.begin"}),
        frozenset({"readiness.fair_boundary"}),
        frozenset({"fair.converged"}),
    ),
    "checker_activation": (
        frozenset({"world.accepted_operation"}),
        frozenset({"readiness.independent_model"}),
        frozenset({"checker.passed"}),
    ),
    "exact_replay": (
        frozenset({"petrus.replay"}),
        frozenset({"petrus.exact_replay"}),
        frozenset({"replay.exact"}),
    ),
}
_BLOCKED: dict[DimensionName, tuple[str, str]] = {
    "ci_rerun_repair": (
        "V5 CI truth is observable, but the DST profile has no rerun request/terminal adapter or independent recovery checker.",
        "Revisit when DS3 adds the modeled CI rerun boundary and drives the real V5 repair loop.",
    ),
    "agent_terminal_fault_cuts": (
        "Agent terminals are modeled, but no deterministic pre/post-terminal fault cut is executable.",
        "Revisit when DS3 adds named agent terminal cuts with custody and retry outcomes.",
    ),
    "stale_rate_limited_reads": (
        "The modeled provider has no stale-read or rate-limit/unavailability schedule adapter.",
        "Revisit when provider read outcomes are first-class normalized commands or faults.",
    ),
    "history_dispatch_fault_cuts": (
        "Remaining canonical History and Motus Dispatch cut names have no application profile adapters.",
        "Revisit when each public-boundary cut has a checker-visible durable disposition.",
    ),
}
_CRASH_OUTCOMES: dict[str, OutcomeEvidence] = {
    "generated_authority_lifecycle_cut": "crash.cut.authority_lifecycle",
    "generated_timer_before_due": "crash.cut.timer_before_due",
    "generated_timer_after_due": "crash.cut.timer_after_due",
    "generated_timer_after_acceptance": "crash.cut.timer_after_acceptance",
    "generated_git_before_delivery": "crash.cut.git_before_delivery",
    "generated_git_after_acceptance": "crash.cut.git_after_acceptance",
    "generated_git_after_head": "crash.cut.git_after_head",
}
_SCENARIO = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}")
_DIGEST = re.compile(r"sha256:[0-9a-f]{64}")
_MAX_RUNS = 16
_MAX_OPERATIONS = 8_192
_MAX_CHECKS = 8_192
_MAX_ARTIFACT_BYTES = 4_194_304
_MAX_TOTAL_ARTIFACT_BYTES = 16_777_216
_MAX_REPORT_BYTES = 262_144


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


class ScenarioReference(_StrictModel):
    scenario_id: str = Field(min_length=1, max_length=128, pattern=_SCENARIO.pattern)
    journal_digest: str = Field(pattern=_DIGEST.pattern)
    replayed: bool


class ScenarioDimensionEvidence(_StrictModel):
    scenario_id: str = Field(min_length=1, max_length=128, pattern=_SCENARIO.pattern)
    journal_digest: str = Field(pattern=_DIGEST.pattern)
    checkpoint: int = Field(ge=0, le=_MAX_OPERATIONS)
    adapters: tuple[AdapterEvidence, ...] = Field(max_length=16)
    checkers: tuple[CheckerEvidence, ...] = Field(max_length=16)
    outcomes: tuple[OutcomeEvidence, ...] = Field(max_length=24)

    @model_validator(mode="after")
    def ordered_unique(self) -> Self:
        for name, values in (
            ("adapters", self.adapters),
            ("checkers", self.checkers),
            ("outcomes", self.outcomes),
        ):
            if tuple(sorted(set(values))) != values:
                raise ValueError(f"coverage {name} must be sorted and unique")
        if not (self.adapters or self.checkers or self.outcomes):
            raise ValueError("scenario coverage evidence cannot be empty")
        return self


class CoverageDimension(_StrictModel):
    name: DimensionName
    status: CoverageStatus
    evidence: tuple[ScenarioDimensionEvidence, ...] = Field(max_length=_MAX_RUNS)
    blocked_reason: str | None = Field(default=None, max_length=512)
    revisit_trigger: str | None = Field(default=None, max_length=512)

    @model_validator(mode="after")
    def coherent(self) -> Self:
        ordered = tuple(sorted(self.evidence, key=lambda item: item.scenario_id))
        if ordered != self.evidence or len({item.scenario_id for item in self.evidence}) != len(self.evidence):
            raise ValueError("dimension evidence must have unique ordered scenarios")
        if self.name in _BLOCKED:
            expected_reason, expected_trigger = _BLOCKED[self.name]
            if (
                self.status != "blocked"
                or self.evidence
                or self.blocked_reason != expected_reason
                or self.revisit_trigger != expected_trigger
            ):
                raise ValueError("blocked dimension must retain its exact reason and revisit trigger")
            return self
        if self.blocked_reason is not None or self.revisit_trigger is not None:
            raise ValueError("executable dimension cannot carry a blocked reason")
        requirements = _REQUIREMENTS[self.name]
        complete = any(
            requirements[0] <= set(item.adapters)
            and requirements[1] <= set(item.checkers)
            and requirements[2] <= set(item.outcomes)
            for item in self.evidence
        )
        if self.status == "covered" and not complete:
            raise ValueError("covered dimension requires complete scenario evidence")
        if self.status == "uncovered" and complete:
            raise ValueError("uncovered dimension contradicts complete scenario evidence")
        if self.status == "blocked":
            raise ValueError("executable dimension cannot be blocked")
        return self


class ReadinessCoverageReport(_StrictModel):
    format: Literal["hamsterdan-readiness-semantic-coverage"]
    version: Literal[1]
    artifact_api: Literal["petrus.testing.dst/v4"]
    profile: ProfileIdentity
    checker: CheckerIdentity
    scenarios: tuple[ScenarioReference, ...] = Field(min_length=1, max_length=_MAX_RUNS)
    dimensions: tuple[CoverageDimension, ...]

    @model_validator(mode="after")
    def complete_catalog(self) -> Self:
        if self.profile != PROFILE_IDENTITY or self.checker != CHECKER_IDENTITY:
            raise ValueError("coverage report dependency identities do not match its contract")
        if tuple(item.name for item in self.dimensions) != _DIMENSIONS:
            raise ValueError("coverage report must contain the ordered complete dimension catalog")
        ordered = tuple(sorted(self.scenarios, key=lambda item: item.scenario_id))
        if ordered != self.scenarios or len({item.scenario_id for item in self.scenarios}) != len(self.scenarios):
            raise ValueError("coverage scenarios must be unique and ordered")
        references = {item.scenario_id: item.journal_digest for item in self.scenarios}
        for dimension in self.dimensions:
            for evidence in dimension.evidence:
                if references.get(evidence.scenario_id) != evidence.journal_digest:
                    raise ValueError("coverage evidence has no matching scenario reference")
        return self

    @property
    def covered(self) -> frozenset[DimensionName]:
        return frozenset(item.name for item in self.dimensions if item.status == "covered")

    @property
    def blocked(self) -> frozenset[DimensionName]:
        return frozenset(item.name for item in self.dimensions if item.status == "blocked")


@dataclass(frozen=True)
class CoverageRun:
    artifact: ScenarioArtifact
    replay: ReplayResult | None = None


@dataclass
class _Signals:
    adapters: set[AdapterEvidence]
    checkers: set[CheckerEvidence]
    outcomes: set[OutcomeEvidence]


@dataclass(frozen=True)
class _Checkpoint:
    position: int
    signals: _Signals


def collect_readiness_coverage(runs: tuple[CoverageRun, ...]) -> ReadinessCoverageReport:
    """Collect bounded evidence without reading production folds or markings."""

    if not runs or len(runs) > _MAX_RUNS:
        raise ValueError(f"readiness coverage requires 1 to at most {_MAX_RUNS} scenario runs")
    by_id: dict[str, str] = {}
    total_operations = total_checks = total_bytes = 0
    normalized: list[tuple[CoverageRun, tuple[_Checkpoint, ...]]] = []
    for run in runs:
        artifact = run.artifact
        if _SCENARIO.fullmatch(artifact.scenario_id) is None:
            raise ValueError("coverage scenario identity is not bounded")
        digest = artifact.expected.journal_digest
        previous = by_id.get(artifact.scenario_id)
        if previous is not None:
            if previous != digest:
                raise ValueError("coverage scenario identity is contradictory")
            raise ValueError("coverage scenario identity is duplicated")
        by_id[artifact.scenario_id] = digest
        _require_compatible_artifact(artifact)
        total_operations += len(artifact.operations)
        total_checks += len(artifact.expected.checks)
        encoded_bytes = len(artifact.model_dump_json().encode())
        if encoded_bytes > _MAX_ARTIFACT_BYTES:
            raise ValueError("coverage artifact exceeds the per-scenario byte bound")
        total_bytes += encoded_bytes
        if total_operations > _MAX_OPERATIONS or total_checks > _MAX_CHECKS:
            raise ValueError("coverage evidence exceeds operation or checker bounds")
        if total_bytes > _MAX_TOTAL_ARTIFACT_BYTES:
            raise ValueError("coverage evidence exceeds the aggregate byte bound")
        replayed = _require_exact_replay(artifact, run.replay) if run.replay is not None else False
        normalized.append((run, _extract_checkpoints(artifact, replayed=replayed)))

    normalized.sort(key=lambda item: item[0].artifact.scenario_id)
    references = tuple(
        ScenarioReference(
            scenario_id=run.artifact.scenario_id,
            journal_digest=run.artifact.expected.journal_digest,
            replayed=run.replay is not None,
        )
        for run, _signals in normalized
    )
    dimensions = tuple(_dimension(name, normalized) for name in _DIMENSIONS)
    report = ReadinessCoverageReport(
        format="hamsterdan-readiness-semantic-coverage",
        version=1,
        artifact_api="petrus.testing.dst/v4",
        profile=PROFILE_IDENTITY,
        checker=CHECKER_IDENTITY,
        scenarios=references,
        dimensions=dimensions,
    )
    if len(encode_readiness_coverage(report)) > _MAX_REPORT_BYTES:
        raise ValueError("readiness coverage report exceeds its byte bound")
    return report


def encode_readiness_coverage(report: ReadinessCoverageReport) -> bytes:
    return json.dumps(report.model_dump(mode="json"), sort_keys=True, separators=(",", ":")).encode()


def load_readiness_coverage(data: bytes) -> ReadinessCoverageReport:
    if len(data) > _MAX_REPORT_BYTES:
        raise ValueError("readiness coverage report exceeds its byte bound")
    return ReadinessCoverageReport.model_validate_json(data, strict=True)


def _require_compatible_artifact(artifact: ScenarioArtifact) -> None:
    if artifact.version != 4 or artifact.api != "petrus.testing.dst/v4":
        raise ValueError("readiness coverage requires a Petrus DST v4 artifact")
    if artifact.profile != PROFILE_IDENTITY:
        raise ValueError("readiness coverage artifact has a foreign profile")
    if artifact.checkers != [CHECKER_IDENTITY]:
        raise ValueError("readiness coverage artifact has a foreign checker catalog")
    if _DIGEST.fullmatch(artifact.expected.journal_digest) is None:
        raise ValueError("readiness coverage artifact has an invalid journal digest")


def _require_exact_replay(artifact: ScenarioArtifact, replayed: ReplayResult) -> bool:
    if replayed.scenario_id != artifact.scenario_id:
        raise ValueError("replay scenario does not match coverage artifact")
    if replayed.outcome != "pass":
        raise ValueError("replay did not pass")
    if replayed.disposition != artifact.expected.disposition:
        raise ValueError("replay disposition does not match coverage artifact")
    if replayed.failure != artifact.expected.failure:
        raise ValueError("replay failure does not match coverage artifact")
    if replayed.operations != len(artifact.operations):
        raise ValueError("replay operation count does not match coverage artifact")
    if replayed.journal_digest != artifact.expected.journal_digest:
        raise ValueError("replay journal digest does not match coverage artifact")
    return True


def _dimension(
    name: DimensionName,
    runs: list[tuple[CoverageRun, tuple[_Checkpoint, ...]]],
) -> CoverageDimension:
    if name in _BLOCKED:
        reason, trigger = _BLOCKED[name]
        return CoverageDimension(
            name=name,
            status="blocked",
            evidence=(),
            blocked_reason=reason,
            revisit_trigger=trigger,
        )
    evidence = tuple(
        item
        for run, checkpoints in runs
        if (
            item := _scenario_dimension_evidence(
                name,
                run.artifact.scenario_id,
                run.artifact.expected.journal_digest,
                checkpoints,
            )
        )
        is not None
    )
    requirements = _REQUIREMENTS[name]
    covered = any(
        requirements[0] <= set(item.adapters)
        and requirements[1] <= set(item.checkers)
        and requirements[2] <= set(item.outcomes)
        for item in evidence
    )
    return CoverageDimension(
        name=name,
        status="covered" if covered else "uncovered",
        evidence=evidence,
        blocked_reason=None,
        revisit_trigger=None,
    )


def _scenario_dimension_evidence(
    name: DimensionName,
    scenario_id: str,
    journal_digest: str,
    checkpoints: tuple[_Checkpoint, ...],
) -> ScenarioDimensionEvidence | None:
    requirements = _REQUIREMENTS[name]
    candidates: list[ScenarioDimensionEvidence] = []
    relevant_adapters = _relevant_adapters(name, requirements[0])
    relevant_outcomes = _relevant_outcomes(name, requirements[2])
    for checkpoint in checkpoints:
        signals = checkpoint.signals
        adapters = tuple(sorted(signals.adapters & relevant_adapters))
        checkers = tuple(sorted(signals.checkers & requirements[1]))
        outcomes = tuple(sorted(signals.outcomes & relevant_outcomes))
        if not (adapters or checkers or outcomes):
            continue
        candidates.append(
            ScenarioDimensionEvidence(
                scenario_id=scenario_id,
                journal_digest=journal_digest,
                checkpoint=checkpoint.position,
                adapters=adapters,
                checkers=checkers,
                outcomes=outcomes,
            )
        )
    if not candidates:
        return None
    return max(
        candidates,
        key=lambda item: (
            requirements[0] <= set(item.adapters)
            and requirements[1] <= set(item.checkers)
            and requirements[2] <= set(item.outcomes),
            len(requirements[0] & set(item.adapters))
            + len(requirements[1] & set(item.checkers))
            + len(requirements[2] & set(item.outcomes)),
            item.checkpoint,
        ),
    )


def _relevant_adapters(
    name: DimensionName,
    required: frozenset[AdapterEvidence],
) -> set[AdapterEvidence]:
    relevant = set(required)
    if name == "provider_response_loss":
        relevant.add("git.response_loss")
    return relevant


def _relevant_outcomes(
    name: DimensionName,
    required: frozenset[OutcomeEvidence],
) -> set[OutcomeEvidence]:
    relevant = set(required)
    if name == "lifecycle_movement":
        relevant.update({"lifecycle.draft", "lifecycle.resumed", "lifecycle.closed"})
    elif name == "crash_reconstruction":
        relevant.update(_CRASH_OUTCOMES.values())
    return relevant


def _extract_checkpoints(artifact: ScenarioArtifact, *, replayed: bool) -> tuple[_Checkpoint, ...]:
    """Build witnesses certified by one passed checker boundary each."""

    checkpoints: list[_Checkpoint] = []
    certified_observations: list[Observation] = []
    all_checks_passed = True
    fair_checked = False
    operations_by_position = {operation.position: operation for operation in artifact.operations}
    for entry in artifact.expected.checks:
        if entry.kind != "check" or entry.name != CHECKER_IDENTITY.name:
            raise ValueError("readiness coverage artifact contains an unexpected checker entry")
        value = _exact_object(entry.value, {"checker", "trigger", "observation", "result"}, "checker entry")
        if value["checker"] != CHECKER_IDENTITY.model_dump(mode="json"):
            raise ValueError("readiness coverage checker identity is contradictory")
        trigger = value["trigger"]
        if type(trigger) is not str:
            raise ValueError("readiness coverage checker trigger is malformed")
        observation = Observation.model_validate(value["observation"], strict=True)
        result = CheckResult.model_validate(value["result"], strict=True)
        _readiness_state(observation)
        if not result.passed:
            all_checks_passed = False
            continue
        certified_observations.append(observation)
        position = observation.sequence
        current = operations_by_position.get(position)
        prefix_position = -1 if trigger == "create" else position
        if isinstance(current, CrashOperation):
            # Petrus checks the last reconstructable state before revocation;
            # only the subsequent successful load may certify the crash.
            prefix_position -= 1
        signals = _operation_signals(artifact, prefix_position, certified_observations)
        signals.checkers.update(_checker_signals(trigger, result))
        signals.outcomes.add("checker.passed")
        checkpoints.append(_Checkpoint(position, signals))
        fair_checked = fair_checked or trigger == "begin_fair"

    finishes = [operation for operation in artifact.operations if isinstance(operation, FinishOperation)]
    if len(finishes) > 1:
        raise ValueError("readiness coverage artifact has multiple finish operations")
    if (
        finishes
        and finishes[0].disposition == "converged"
        and fair_checked
        and all_checks_passed
        and artifact.expected.failure is None
    ):
        finish = finishes[0]
        signals = _operation_signals(artifact, finish.position, certified_observations)
        signals.checkers.add("readiness.fair_boundary")
        signals.outcomes.add("fair.converged")
        checkpoints.append(_Checkpoint(finish.position, signals))
    if replayed:
        position = max((operation.position for operation in artifact.operations), default=0)
        checkpoints.append(
            _Checkpoint(
                position,
                _Signals(
                    adapters={"petrus.replay"},
                    checkers={"petrus.exact_replay"},
                    outcomes={"replay.exact"},
                ),
            )
        )
    return tuple(checkpoints)


def _operation_signals(
    artifact: ScenarioArtifact,
    prefix_position: int,
    observations: list[Observation],
) -> _Signals:
    adapters: set[AdapterEvidence] = set()
    checkers: set[CheckerEvidence] = set()
    outcomes: set[OutcomeEvidence] = set()
    authorities: list[dict[str, JsonValue]] = []
    lifecycles: list[str] = []
    deliveries: dict[str, int] = {}

    for operation in artifact.operations:
        if operation.position > prefix_position:
            continue
        if isinstance(operation, ExecuteOperation):
            adapters.add("world.accepted_operation")
            name = operation.command.name
            payload = _object(operation.command.payload, f"{name} payload")
            if name == "readiness.github.pr.set":
                adapters.add("authority.set")
                authority = _object(payload.get("authority"), "authority command")
                lifecycle = authority.get("lifecycle")
                if type(lifecycle) is not str:
                    raise ValueError("authority lifecycle is malformed")
                authorities.append(authority)
                lifecycles.append(lifecycle)
            elif name == "readiness.github.webhook.deliver":
                delivery = payload.get("delivery")
                if type(delivery) is not str:
                    raise ValueError("webhook delivery evidence is malformed")
                deliveries[delivery] = deliveries.get(delivery, 0) + 1
                result = _object(operation.result.value, "webhook delivery result")
                if result.get("disposition") == "duplicate":
                    outcomes.add("webhook.duplicate")
            elif name == "readiness.time.advance":
                adapters.add("time.advance")
            elif name == "readiness.agent.terminal":
                fixture = payload.get("fixture")
                if fixture in {"conversation_change", "conversation_recover"}:
                    adapters.add("agent.conversation_terminal")
                elif fixture == "coding":
                    adapters.add("agent.coding_terminal")
            elif name == "readiness.github.human.comment":
                fixture = payload.get("fixture")
                if type(fixture) is str and fixture.startswith("recover:"):
                    adapters.add("git.recovery_grant")
        elif isinstance(operation, FaultOperation):
            payload = _object(operation.fault.payload, "fault payload")
            cut = payload.get("cut")
            if operation.fault.name == "readiness.github.effect" and cut == "after_acceptance_before_response":
                adapters.add("provider.response_loss")
            elif operation.fault.name == "readiness.git.publish" and cut == "ref_cas":
                adapters.update({"provider.response_loss", "git.response_loss"})
        elif isinstance(operation, CrashOperation):
            adapters.add("generation.crash")
            selected = _CRASH_OUTCOMES.get(operation.cut)
            if selected is not None:
                outcomes.add(selected)
        elif isinstance(operation, RestartOperation):
            adapters.add("generation.restart")
        elif isinstance(operation, FairOperation):
            adapters.add("fair.begin")
        elif isinstance(operation, FinishOperation):
            if operation.disposition == "converged":
                outcomes.add("fair.converged")

    if any(count > 1 for count in deliveries.values()):
        adapters.add("webhook.redelivery")
    states = [_readiness_state(observation) for observation in observations]
    model_generations, observed_lifecycles = _state_outcomes(states, outcomes, adapters)
    distinct_authorities = {json.dumps(authority, sort_keys=True, separators=(",", ":")) for authority in authorities}
    if len(distinct_authorities) > 1 and max(model_generations, default=0) > 1:
        outcomes.add("authority.generation_moved")
    if len(set(lifecycles)) > 1 and set(lifecycles) <= observed_lifecycles:
        outcomes.add("lifecycle.changed")
        if "draft" in lifecycles:
            outcomes.add("lifecycle.draft")
        if "closed" in lifecycles:
            outcomes.add("lifecycle.closed")
        if any(previous == "draft" and current == "active" for previous, current in pairwise(lifecycles)):
            outcomes.add("lifecycle.resumed")
    if max((observation.generation for observation in observations), default=0) > 1:
        outcomes.add("generation.reloaded")
    return _Signals(adapters, checkers, outcomes)


def _checker_signals(trigger: str, result: CheckResult) -> set[CheckerEvidence]:
    checkers: set[CheckerEvidence] = {"readiness.independent_model"}
    detail = _object(result.detail, "checker detail")
    if (
        detail.get("parity") is True
        and detail.get("snapshot_parity") is True
        and detail.get("authority_lag") is False
        and detail.get("violations") == []
    ):
        checkers.add("readiness.authority")
    if (
        detail.get("duplicate_acceptance") == []
        and detail.get("duplicate_terminal_projection") == []
        and detail.get("effect_identity_collisions") == []
    ):
        checkers.add("readiness.no_duplicate_effect")
    if detail.get("timer_custody_parity") is True and detail.get("timer_custody_mismatches") == []:
        checkers.add("readiness.timer_custody")
    if detail.get("git_custody_parity") is True and detail.get("git_custody_mismatches") == []:
        checkers.add("readiness.git_custody")
    if trigger == "load":
        checkers.add("readiness.generation_load")
    if trigger == "begin_fair":
        checkers.add("readiness.fair_boundary")
    return checkers


def _state_outcomes(
    states: list[dict[str, JsonValue]],
    outcomes: set[OutcomeEvidence],
    adapters: set[AdapterEvidence],
) -> tuple[list[int], set[str]]:
    generations: list[int] = []
    lifecycles: set[str] = set()
    for state in states:
        expected = _object(state.get("expected"), "expected readiness state")
        generation = expected.get("generation")
        if type(generation) is int:
            generations.append(generation)
        facts = _object(state.get("facts"), "readiness facts")
        authority = _object(facts.get("authority"), "readiness authority facts")
        for claim in (authority.get("admitted"), authority.get("provider")):
            if claim is None:
                continue
            lifecycle = _object(claim, "observed readiness authority").get("lifecycle")
            if type(lifecycle) is not str:
                raise ValueError("observed readiness lifecycle is malformed")
            lifecycles.add(lifecycle)
        timers = facts.get("timers")
        if type(timers) is not list:
            raise ValueError("readiness timer facts are malformed")
        if any(type(item) is dict and item.get("status") == "acknowledged" for item in timers):
            outcomes.add("timer.acknowledged")
        custody = _object(state.get("timer_custody"), "timer custody")
        durable_timers = custody.get("timers")
        if type(durable_timers) is not list:
            raise ValueError("durable timer custody is malformed")
        if any(type(item) is dict and item.get("state") == "armed" for item in durable_timers):
            outcomes.add("timer.armed")
        if any(type(item) is dict and item.get("matured_at") is not None for item in durable_timers):
            outcomes.add("timer.matured")

        provider = _object(state.get("provider"), "provider observation")
        response_losses = provider.get("response_losses")
        publications = provider.get("git_publications")
        calls = provider.get("agent_call_log")
        recoveries = provider.get("admitted_recoveries")
        if type(response_losses) is not list or type(publications) is not list or type(calls) is not list:
            raise ValueError("provider coverage observation is malformed")
        if response_losses or any(type(item) is dict and item.get("response_lost") is True for item in publications):
            outcomes.add("provider.response_lost")
        if any(type(item) is dict and item.get("kind") == "conversation" for item in calls):
            outcomes.add("agent.conversation_called")
        if any(type(item) is dict and item.get("kind") == "coding" for item in calls):
            outcomes.add("agent.coding_called")
        if publications:
            outcomes.add("git.accepted")
        if type(recoveries) is not list:
            raise ValueError("provider recovery observation is malformed")
        if recoveries:
            outcomes.add("git.recovery_authorized")

        git_custody = _object(state.get("git_custody"), "Git custody")
        requests = git_custody.get("requests")
        terminals = git_custody.get("terminals")
        if type(requests) is not list or type(terminals) is not list:
            raise ValueError("Git custody observation is malformed")
        if requests:
            adapters.add("git.provider_request")
        variants = [item.get("variant") for item in terminals if type(item) is dict]
        if "FaultM" in variants and "Pushed" in variants and variants.index("FaultM") < variants.index("Pushed"):
            outcomes.add("git.faultm_then_pushed")
    return generations, lifecycles


def _readiness_state(observation: Observation) -> dict[str, JsonValue]:
    if observation.name != "readiness.state":
        raise ValueError("readiness coverage encountered a foreign observation")
    return _object(observation.value, "readiness observation")


def _object(value: object, label: str) -> dict[str, JsonValue]:
    if type(value) is not dict:
        raise ValueError(f"{label} must be a strict object")
    return cast(dict[str, JsonValue], value)


def _exact_object(value: object, keys: set[str], label: str) -> dict[str, JsonValue]:
    result = _object(value, label)
    if set(result) != keys:
        raise ValueError(f"{label} must contain exact fields {sorted(keys)}")
    return result


__all__ = [
    "CoverageDimension",
    "CoverageRun",
    "ReadinessCoverageReport",
    "ScenarioDimensionEvidence",
    "ScenarioReference",
    "collect_readiness_coverage",
    "encode_readiness_coverage",
    "load_readiness_coverage",
]
