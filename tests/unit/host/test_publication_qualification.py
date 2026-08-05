import pytest

from hamsterdan.contracts.readiness import EffectResult
from hamsterdan.host.git_publish import GitPublishError, PublicationCategory
from hamsterdan.host.publication_qualification import PublicationQualification, QualificationCategory


def result(*, ok: bool, category: str = "") -> EffectResult:
    return EffectResult("change", 2, "a" * 40, ok, operation="change:diagnostic", publication_category=category)


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
    ],
)
def test_arbitrary_or_private_diagnostics_cannot_enter_retained_evidence(effect: EffectResult) -> None:
    with pytest.raises(ValueError, match="closed vocabulary"):
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
