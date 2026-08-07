import pytest

from hamsterdan.agents import AgentCleanupCategory, AgentResultCategory
from hamsterdan.contracts.readiness import EffectResult
from hamsterdan.host.git_publish import GitPublishError, PublicationCategory
from hamsterdan.host.publication_qualification import PublicationQualification, QualificationCategory


def result(
    *,
    ok: bool,
    category: str = "",
    agent_result: str = "",
    agent_cleanup: str = "",
) -> EffectResult:
    return EffectResult(
        "change",
        2,
        "a" * 40,
        ok,
        operation="change:diagnostic",
        publication_category=category,
        agent_result_category=agent_result,
        agent_cleanup_category=agent_cleanup,
    )


def test_original_failure_is_retained_and_zero_publication_suppresses_every_assertion() -> None:
    evidence = PublicationQualification()
    calls: list[str] = []
    evidence.record_original(result(ok=False, category=PublicationCategory.REF_CAS), 0)

    evidence.run_publication_assertions(
        schema=lambda: calls.append("schema") is None,
        tree=lambda: calls.append("tree") is None,
        replay=lambda: (_ for _ in ()).throw(
            GitPublishError(PublicationCategory.PATCH_ADMISSION, "private secondary diagnostic")
        ),
    )

    assert calls == []
    assert evidence.original_category is PublicationCategory.REF_CAS
    assert evidence.replay_category is None
    assert evidence.sanitized() == {
        "accepted": False,
        "original_publications": 0,
        "agent_result_category": "",
        "agent_cleanup_category": "",
        "original_category": "ref_cas",
        "publication_assertions_allowed": False,
        "schema_assertion": None,
        "tree_assertion": None,
        "replay_assertion": None,
        "replay_category": "",
        "cleanup_verified": None,
        "cleanup_category": "",
    }


def test_success_runs_assertions_and_one_replay_without_overwriting_original() -> None:
    evidence = PublicationQualification()
    calls: list[str] = []
    evidence.record_original(result(ok=True), 1)
    evidence.run_publication_assertions(
        schema=lambda: not calls.append("schema"),
        tree=lambda: not calls.append("tree"),
        replay=lambda: not calls.append("replay"),
    )
    evidence.record_cleanup(True)

    assert calls == ["schema", "tree", "replay"]
    assert evidence.accepted
    assert evidence.original_category is None and evidence.replay_category is None


@pytest.mark.parametrize("category", list(AgentResultCategory))
def test_agent_result_first_cause_suppresses_all_publication_assertions(category: AgentResultCategory) -> None:
    evidence = PublicationQualification()
    calls: list[str] = []

    evidence.record_original(result(ok=False, agent_result=category), 0)
    evidence.run_publication_assertions(
        schema=lambda: not calls.append("schema"),
        tree=lambda: not calls.append("tree"),
        replay=lambda: not calls.append("replay"),
    )

    assert calls == []
    assert evidence.agent_result_category is category
    assert evidence.original_category is None
    assert evidence.sanitized()["agent_result_category"] == category.value


def test_agent_result_first_cause_and_cleanup_uncertainty_remain_separate() -> None:
    evidence = PublicationQualification()
    evidence.record_original(
        result(
            ok=False,
            agent_result=AgentResultCategory.OUTPUT_SCHEMA,
            agent_cleanup=AgentCleanupCategory.UNVERIFIED,
        ),
        0,
    )
    evidence.record_cleanup(False)

    assert evidence.agent_result_category is AgentResultCategory.OUTPUT_SCHEMA
    assert evidence.agent_cleanup_category is AgentCleanupCategory.UNVERIFIED
    assert evidence.original_category is None
    assert evidence.cleanup_category is QualificationCategory.CLEANUP_UNVERIFIED


def test_replay_and_cleanup_failures_are_separate_and_do_not_replace_original() -> None:
    evidence = PublicationQualification()
    evidence.record_original(result(ok=True), 1)
    evidence.run_publication_assertions(
        schema=lambda: True,
        tree=lambda: True,
        replay=lambda: (_ for _ in ()).throw(GitPublishError(PublicationCategory.IDEMPOTENCY, "private")),
    )
    evidence.record_cleanup(False)

    assert evidence.original_category is None
    assert evidence.replay_category is PublicationCategory.IDEMPOTENCY
    assert evidence.cleanup_category is QualificationCategory.CLEANUP_UNVERIFIED
    assert not evidence.accepted


@pytest.mark.parametrize(
    "effect",
    [
        result(ok=False, category="owner/private-ref"),
        result(ok=False, category="https://example.invalid/private"),
        result(ok=False, category="raw provider diagnostic"),
        result(ok=False, agent_result="owner/private-ref"),
        result(ok=False, agent_result="raw model diagnostic"),
        result(ok=False, agent_cleanup="raw cleanup prose"),
    ],
)
def test_arbitrary_or_private_diagnostics_cannot_enter_retained_evidence(effect: EffectResult) -> None:
    with pytest.raises((TypeError, ValueError), match="closed vocabulary"):
        PublicationQualification().record_original(effect, 0)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("publication_category", None),
        ("agent_result_category", 0),
        ("agent_cleanup_category", False),
        ("agent_result_category", []),
    ],
)
def test_falsy_nonstring_categories_cannot_bypass_the_closed_vocabulary(field: str, value: object) -> None:
    effect = result(ok=False, category=PublicationCategory.REF_CAS)
    object.__setattr__(effect, field, value)

    with pytest.raises((TypeError, ValueError), match="closed vocabulary"):
        PublicationQualification().record_original(effect, 0)


def test_inconsistent_or_repeated_original_and_cleanup_evidence_is_rejected() -> None:
    evidence = PublicationQualification()
    with pytest.raises(ValueError, match="lacks a closed category"):
        evidence.record_original(result(ok=False), 0)
    with pytest.raises(ValueError, match="inconsistent"):
        PublicationQualification().record_original(result(ok=True), 0)

    evidence.record_original(result(ok=False, category=PublicationCategory.GIT_OPERATION), 0)
    with pytest.raises(ValueError, match="inconsistent"):
        evidence.record_original(result(ok=False, category=PublicationCategory.REF_CAS), 0)
    evidence.record_cleanup(True)
    with pytest.raises(ValueError, match="inconsistent"):
        evidence.record_cleanup(False)

    overlap = result(
        ok=False,
        category=PublicationCategory.REF_CAS,
        agent_result=AgentResultCategory.CORRELATION,
    )
    with pytest.raises(ValueError, match="cannot overlap"):
        PublicationQualification().record_original(overlap, 0)


def test_assertions_are_one_shot_and_non_boolean_evidence_is_rejected() -> None:
    evidence = PublicationQualification()
    evidence.record_original(result(ok=True), 1)
    with pytest.raises(ValueError, match="must be boolean"):
        evidence.run_publication_assertions(schema=lambda: "passed", tree=lambda: True, replay=lambda: True)  # type: ignore[return-value]
    with pytest.raises(ValueError, match="already started"):
        evidence.run_publication_assertions(schema=lambda: True, tree=lambda: True, replay=lambda: True)
    assert not evidence.accepted

    malformed = result(ok=True)
    object.__setattr__(malformed, "ok", "true")
    with pytest.raises(ValueError, match="inconsistent"):
        PublicationQualification().record_original(malformed, 1)
