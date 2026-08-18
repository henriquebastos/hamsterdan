from __future__ import annotations

import json
from dataclasses import replace

import pytest
from petrus.testing.dst import API_COMPATIBILITY, ARTIFACT_FORMAT, CheckResult, Observation
from pydantic import ValidationError

from hamsterdan.testing.readiness import (
    AuthorityClaim,
    AuthorityFacts,
    ChangeAuthorization,
    CheckFacts,
    CiFacts,
    EffectObligation,
    FairEnvironment,
    Finding,
    HumanFacts,
    MutationFacts,
    ReadinessFacts,
    ReadinessModel,
    ReviewFacts,
    TimerObligation,
    evaluate_liveness,
)


def claim(
    *,
    installation: int = 44,
    repository: int = 31,
    pull_request: int = 7,
    head: str = "a" * 40,
    base: str = "b" * 40,
    policy: str = "policy-1",
    lifecycle: str = "active",
    strict_base: bool = True,
    base_current: bool = True,
    mergeable: bool = True,
) -> AuthorityClaim:
    return AuthorityClaim(
        installation=installation,
        repository=repository,
        pull_request=pull_request,
        head=head,
        base=base,
        policy=policy,
        lifecycle=lifecycle,
        strict_base=strict_base,
        base_current=base_current,
        mergeable=mergeable,
    )


def ready_facts() -> ReadinessFacts:
    current = claim()
    return ReadinessFacts(
        subject="github:44:31:pr:7",
        authority=AuthorityFacts(generation=1, admitted=current, provider=current),
        admitted_observations=("delivery:open",),
        ci=CiFacts(
            head=current.head,
            required_checks=("build",),
            checks=(CheckFacts(name="build", status="success"),),
        ),
        review=ReviewFacts(head=current.head, status="clear"),
        human=HumanFacts(approvals=1, required_approvals=1),
    )


def authorization(
    *,
    operation: str = "push:comment:1",
    authority: AuthorityClaim | None = None,
) -> ChangeAuthorization:
    return ChangeAuthorization(
        identity="delivery:comment:1",
        operation=operation,
        authority=authority or claim(),
        intent="repair",
        intent_digest="sha256:repair-request-1",
    )


def test_clean_green_is_ready_without_topology_state() -> None:
    expectation = ReadinessModel().evaluate(ready_facts())

    assert expectation.ready is True
    assert expectation.disposition == "ready"
    assert expectation.blockers == ()
    assert expectation.violations == ()


def test_a_new_provider_head_invalidates_old_readiness_until_fresh_evidence_arrives() -> None:
    model = ReadinessModel()
    head_a = ready_facts()
    assert model.evaluate(head_a).disposition == "ready"

    # GitHub has moved to B, but B's webhook has not yet reached host custody.
    admitted_a = head_a.authority.admitted
    assert admitted_a is not None
    provider_b = claim(head="c" * 40)
    awaiting_admission = replace(
        head_a,
        authority=AuthorityFacts(generation=1, admitted=admitted_a, provider=provider_b),
    )
    assert model.evaluate(awaiting_admission).blockers == ("current_authority_admission",)

    # Publishing under A after GitHub moved to B is a correctness failure.
    stale_publication = replace(
        awaiting_admission,
        effects=(
            EffectObligation(
                kind="readiness",
                operation="ready:head-a",
                authority=admitted_a,
                content_digest="head-a-ready",
                status="settled",
            ),
        ),
    )
    assert model.evaluate(stale_publication).violations == (
        "stale_effect_settled:ready:head-a",
        "readiness_published_with_closed_gates:ready:head-a",
    )

    # Once B is admitted, evidence from A is still insufficient.
    admitted_b = replace(
        head_a,
        authority=AuthorityFacts(generation=2, admitted=provider_b, provider=provider_b),
    )
    assert model.evaluate(admitted_b).blockers == ("current_ci_evidence", "current_review_evidence")

    # Fresh CI and review evidence for B restore the expected ready result.
    current_b = replace(
        admitted_b,
        ci=CiFacts(
            head=provider_b.head,
            required_checks=("build",),
            checks=(CheckFacts(name="build", status="success"),),
        ),
        review=ReviewFacts(head=provider_b.head, status="clear"),
    )
    assert model.evaluate(current_b).disposition == "ready"


def test_transient_ci_failure_progresses_but_persistent_repair_waits_for_a_human() -> None:
    failed_check = CheckFacts(name="build", status="failure")
    failed = replace(
        ready_facts(),
        ci=CiFacts(head="a" * 40, required_checks=("build",), checks=(failed_check,), recovery="automatic"),
    )
    persistent = replace(
        ready_facts(),
        ci=CiFacts(
            head="a" * 40,
            required_checks=("build",),
            checks=(failed_check,),
            recovery="human_authorization",
        ),
    )

    assert ReadinessModel().evaluate(failed).disposition == "progressing"
    assert ReadinessModel().evaluate(failed).blockers == ("ci_failed:build",)
    assert ReadinessModel().evaluate(persistent).disposition == "human_wait"
    assert ReadinessModel().evaluate(persistent).blockers == ("ci_repair_authorization:build",)


def test_every_required_check_is_derived_from_provider_facts() -> None:
    missing = replace(
        ready_facts(),
        ci=CiFacts(
            head="a" * 40,
            required_checks=("build", "security"),
            checks=(CheckFacts(name="build", status="success"),),
        ),
    )
    failed = replace(
        ready_facts(),
        ci=CiFacts(
            head="a" * 40,
            required_checks=("build", "security"),
            checks=(
                CheckFacts(name="build", status="success"),
                CheckFacts(name="security", status="failure"),
            ),
            recovery="automatic",
        ),
    )

    assert ReadinessModel().evaluate(missing).blockers == ("required_ci_missing:security",)
    assert ReadinessModel().evaluate(failed).blockers == ("ci_failed:security",)


def test_open_finding_and_collaboration_require_human_resolution() -> None:
    facts = replace(
        ready_facts(),
        review=ReviewFacts(
            head="a" * 40,
            status="blocking",
            findings=(Finding(identity="finding-1", blocking=True, disposition="open"),),
        ),
        human=HumanFacts(
            approvals=1,
            required_approvals=1,
            changes_requested=True,
            unresolved_conversations=2,
        ),
    )

    expectation = ReadinessModel().evaluate(facts)

    assert expectation.disposition == "human_wait"
    assert expectation.blockers == (
        "blocking_findings",
        "changes_requested",
        "unresolved_conversations",
    )


def test_agent_inability_and_missing_approval_are_explicit_waits() -> None:
    unable = replace(ready_facts(), review=ReviewFacts(head="a" * 40, status="unable"))
    approval = replace(ready_facts(), human=HumanFacts(approvals=0, required_approvals=1))

    assert ReadinessModel().evaluate(unable).disposition == "external_wait"
    assert ReadinessModel().evaluate(unable).blockers == ("review_capability",)
    assert ReadinessModel().evaluate(approval).disposition == "human_wait"
    assert ReadinessModel().evaluate(approval).blockers == ("human_approval",)


def test_provider_movement_stales_admitted_authority_and_current_evidence() -> None:
    admitted = claim()
    provider = claim(head="c" * 40)
    facts = replace(
        ready_facts(),
        authority=AuthorityFacts(generation=1, admitted=admitted, provider=provider),
    )

    expectation = ReadinessModel().evaluate(facts)

    assert expectation.ready is False
    assert expectation.disposition == "progressing"
    assert expectation.blockers == ("current_authority_admission",)


def test_new_generation_requires_fresh_ci_and_review_evidence() -> None:
    current = claim(head="c" * 40)
    facts = replace(
        ready_facts(),
        authority=AuthorityFacts(generation=2, admitted=current, provider=current),
    )

    expectation = ReadinessModel().evaluate(facts)

    assert expectation.blockers == ("current_ci_evidence", "current_review_evidence")
    assert expectation.disposition == "progressing"


def test_draft_resume_and_close_have_distinct_dispositions() -> None:
    drafted = claim(lifecycle="draft")
    draft = replace(
        ready_facts(),
        authority=AuthorityFacts(generation=1, admitted=drafted, provider=drafted),
    )
    resumed = claim(head="c" * 40)
    resume = replace(
        ready_facts(),
        authority=AuthorityFacts(generation=2, admitted=resumed, provider=resumed),
    )
    closed = claim(lifecycle="closed")
    close = replace(
        ready_facts(),
        authority=AuthorityFacts(generation=1, admitted=closed, provider=closed),
    )

    assert ReadinessModel().evaluate(draft).disposition == "human_wait"
    assert ReadinessModel().evaluate(draft).blockers == ("pull_request_draft",)
    assert ReadinessModel().evaluate(resume).blockers == ("current_ci_evidence", "current_review_evidence")
    assert ReadinessModel().evaluate(close).disposition == "terminal"


def test_mutation_effect_and_timer_obligations_are_visible() -> None:
    facts = replace(
        ready_facts(),
        admitted_observations=("delivery:open", "delivery:comment:1"),
        mutation=MutationFacts(
            status="in_flight",
            operation="push:comment:1",
            head="a" * 40,
            authorization=authorization(),
        ),
        effects=(
            EffectObligation(
                kind="git_mutation",
                operation="push:comment:1",
                authority=claim(),
                content_digest="change-1",
                status="ambiguous",
                authorization="delivery:comment:1",
            ),
        ),
        timers=(TimerObligation(identity="reminder:1", status="due", blocks_readiness=True),),
    )

    expectation = ReadinessModel().evaluate(facts)

    assert expectation.disposition == "progressing"
    assert expectation.blockers == (
        "mutation_in_flight",
        "effect_ambiguous:push:comment:1",
        "timer_due:reminder:1",
    )
    assert expectation.violations == ()


@pytest.mark.parametrize("kind", ["coding", "git_mutation"])
def test_coding_and_git_mutation_require_explicit_human_authorization(kind: str) -> None:
    facts = replace(
        ready_facts(),
        mutation=MutationFacts(status="in_flight", operation="push:comment:1", head="a" * 40),
        effects=(
            EffectObligation(
                kind=kind,
                operation="push:comment:1",
                authority=claim(),
                content_digest="change-1",
                status="accepted",
            ),
        ),
    )

    expectation = ReadinessModel().evaluate(facts)

    assert expectation.disposition == "quarantined"
    assert expectation.violations == ("unauthorized_change:push:comment:1",)


def test_change_authorization_is_bound_to_one_exact_operation() -> None:
    facts = replace(
        ready_facts(),
        admitted_observations=("delivery:open", "delivery:comment:1"),
        mutation=MutationFacts(
            status="in_flight",
            operation="push:comment:2",
            head="a" * 40,
            authorization=authorization(operation="push:comment:1"),
        ),
        effects=(
            EffectObligation(
                kind="coding",
                operation="push:comment:2",
                authority=claim(),
                content_digest="change-2",
                status="accepted",
                authorization="delivery:comment:1",
            ),
        ),
    )

    assert ReadinessModel().evaluate(facts).violations == ("unauthorized_change:push:comment:2",)


def test_change_effect_must_reference_the_exact_authorization_identity() -> None:
    facts = replace(
        ready_facts(),
        admitted_observations=("delivery:open", "delivery:comment:1"),
        mutation=MutationFacts(
            status="in_flight",
            operation="push:comment:1",
            head="a" * 40,
            authorization=authorization(),
        ),
        effects=(
            EffectObligation(
                kind="coding",
                operation="push:comment:1",
                authority=claim(),
                content_digest="change-1",
                status="accepted",
                authorization="delivery:someone-elses-comment",
            ),
        ),
    )

    assert ReadinessModel().evaluate(facts).violations == ("unauthorized_change:push:comment:1",)


def test_change_authorization_requires_its_human_delivery_to_be_admitted() -> None:
    facts = replace(
        ready_facts(),
        mutation=MutationFacts(
            status="in_flight",
            operation="push:comment:1",
            head="a" * 40,
            authorization=authorization(),
        ),
        effects=(
            EffectObligation(
                kind="coding",
                operation="push:comment:1",
                authority=claim(),
                content_digest="change-1",
                status="accepted",
                authorization="delivery:comment:1",
            ),
        ),
    )

    assert ReadinessModel().evaluate(facts).violations == ("unauthorized_change:push:comment:1",)


def test_change_authorization_is_bound_to_the_current_full_authority() -> None:
    authority_a = claim()
    authority_b = claim(head="c" * 40)
    facts = replace(
        ready_facts(),
        admitted_observations=("delivery:open", "delivery:comment:1"),
        authority=AuthorityFacts(generation=2, admitted=authority_b, provider=authority_b),
        ci=CiFacts(
            head=authority_b.head,
            required_checks=("build",),
            checks=(CheckFacts(name="build", status="success"),),
        ),
        review=ReviewFacts(head=authority_b.head, status="clear"),
        mutation=MutationFacts(
            status="in_flight",
            operation="push:comment:1",
            head=authority_b.head,
            authorization=authorization(authority=authority_a),
        ),
        effects=(
            EffectObligation(
                kind="git_mutation",
                operation="push:comment:1",
                authority=authority_b,
                content_digest="change-1",
                status="accepted",
                authorization="delivery:comment:1",
            ),
        ),
    )

    assert ReadinessModel().evaluate(facts).violations == ("unauthorized_change:push:comment:1",)


def test_duplicate_admission_and_effect_identity_collision_are_safety_violations() -> None:
    facts = replace(
        ready_facts(),
        admitted_observations=("delivery:open", "delivery:open"),
        effects=(
            EffectObligation(
                kind="dashboard",
                operation="dashboard:1",
                authority=claim(),
                content_digest="one",
                status="settled",
            ),
            EffectObligation(
                kind="dashboard",
                operation="dashboard:1",
                authority=claim(),
                content_digest="two",
                status="settled",
            ),
        ),
    )

    expectation = ReadinessModel().evaluate(facts)

    assert expectation.disposition == "quarantined"
    assert expectation.violations == ("duplicate_admission:delivery:open", "effect_identity_collision:dashboard:1")


def test_stale_effect_and_premature_readiness_publication_are_safety_violations() -> None:
    facts = replace(
        ready_facts(),
        ci=CiFacts(
            head="a" * 40,
            required_checks=("build",),
            checks=(CheckFacts(name="build", status="failure"),),
            recovery="automatic",
        ),
        effects=(
            EffectObligation(
                kind="readiness",
                operation="ready:old",
                authority=claim(head="0" * 40),
                content_digest="ready",
                status="settled",
            ),
        ),
    )

    expectation = ReadinessModel().evaluate(facts)

    assert expectation.disposition == "quarantined"
    assert expectation.violations == (
        "stale_effect_settled:ready:old",
        "readiness_published_with_closed_gates:ready:old",
    )


@pytest.mark.parametrize("lifecycle", ["draft", "merged", "closed"])
def test_readiness_cannot_be_published_outside_an_active_lifecycle(lifecycle: str) -> None:
    authority = claim(lifecycle=lifecycle)
    facts = replace(
        ready_facts(),
        authority=AuthorityFacts(generation=1, admitted=authority, provider=authority),
        effects=(
            EffectObligation(
                kind="readiness",
                operation=f"ready:{lifecycle}",
                authority=authority,
                content_digest="ready",
                status="settled",
            ),
        ),
    )

    assert f"readiness_published_outside_active_lifecycle:ready:{lifecycle}" in (
        ReadinessModel().evaluate(facts).violations
    )


def test_settled_effect_is_stale_when_provider_authority_moves_before_admission() -> None:
    admitted = claim()
    provider = claim(head="c" * 40)
    facts = replace(
        ready_facts(),
        admitted_observations=("delivery:open", "delivery:comment:1"),
        authority=AuthorityFacts(generation=1, admitted=admitted, provider=provider),
        mutation=MutationFacts(
            status="in_flight",
            operation="push:stale",
            head=admitted.head,
            authorization=authorization(operation="push:stale", authority=admitted),
        ),
        effects=(
            EffectObligation(
                kind="git_mutation",
                operation="push:stale",
                authority=admitted,
                content_digest="change",
                status="settled",
                authorization="delivery:comment:1",
            ),
        ),
    )

    assert ReadinessModel().evaluate(facts).violations == (
        "unauthorized_change:push:stale",
        "stale_effect_settled:push:stale",
    )


def test_strict_snapshot_round_trips_as_json_and_rejects_unmodeled_payloads() -> None:
    facts = ready_facts()
    encoded = json.dumps(facts.dump(), sort_keys=True)

    assert ReadinessFacts.load(encoded) == facts
    payload = facts.dump() | {"credential": "must-not-enter-the-model"}
    with pytest.raises(ValidationError):
        ReadinessFacts.load(json.dumps(payload))

    with pytest.raises(ValueError, match="subject must match"):
        replace(facts, subject="github:44:31:pr:8")


def test_model_values_fit_the_supported_petrus_detached_contract() -> None:
    facts = ready_facts()
    expectation = ReadinessModel().evaluate(facts)

    observation = Observation(
        name="readiness.expected_facts",
        value=facts.dump(),
        instant=0,
        generation=1,
        sequence=0,
    )
    result = CheckResult(passed=expectation.ready, detail=expectation.dump())

    assert API_COMPATIBILITY == "petrus.testing.dst/v1"
    assert ARTIFACT_FORMAT == "petrus-dst-world"
    assert observation.value == facts.dump()
    assert result.passed is True


def test_liveness_only_blames_runtime_after_a_fair_environment_exhausts_its_budget() -> None:
    progressing = ReadinessModel().evaluate(
        replace(
            ready_facts(),
            admitted_observations=("delivery:open", "delivery:comment:1"),
            mutation=MutationFacts(
                status="ambiguous",
                operation="push:1",
                head="a" * 40,
                authorization=authorization(operation="push:1"),
            ),
        )
    )
    fair = FairEnvironment(
        generated_faults_stopped=True,
        authority_stable=True,
        workers_available=True,
        logical_time_advances=True,
        durable_stores_readable=True,
    )

    assert evaluate_liveness(progressing, fair, budget_exhausted=False) == "in_progress"
    assert evaluate_liveness(progressing, fair, budget_exhausted=True) == "livelock"


def test_liveness_does_not_call_provider_or_human_wait_livelock() -> None:
    provider_wait = ReadinessModel().evaluate(
        replace(
            ready_facts(),
            ci=CiFacts(
                head="a" * 40,
                required_checks=("build",),
                checks=(CheckFacts(name="build", status="unavailable"),),
            ),
        )
    )
    human_wait = ReadinessModel().evaluate(replace(ready_facts(), human=HumanFacts(approvals=0, required_approvals=1)))
    fair = FairEnvironment(
        generated_faults_stopped=True,
        authority_stable=True,
        workers_available=True,
        logical_time_advances=True,
        durable_stores_readable=True,
    )

    assert evaluate_liveness(provider_wait, fair, budget_exhausted=True) == "not_applicable"
    assert evaluate_liveness(human_wait, fair, budget_exhausted=True) == "not_applicable"


def test_liveness_requires_every_fair_environment_condition() -> None:
    progressing = ReadinessModel().evaluate(
        replace(
            ready_facts(),
            admitted_observations=("delivery:open", "delivery:comment:1"),
            mutation=MutationFacts(
                status="ambiguous",
                operation="push:1",
                head="a" * 40,
                authorization=authorization(operation="push:1"),
            ),
        )
    )
    unfair = FairEnvironment(
        generated_faults_stopped=False,
        authority_stable=True,
        workers_available=True,
        logical_time_advances=True,
        durable_stores_readable=True,
    )

    assert evaluate_liveness(progressing, unfair, budget_exhausted=True) == "not_applicable"
