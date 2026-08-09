import os
import stat
import subprocess
from pathlib import Path

import pytest

from hamsterdan.agents import AgentCleanupCategory, AgentResultCategory
from hamsterdan.contracts.readiness import EffectResult
from hamsterdan.host.git_publish import GitPublishError, PublicationCategory
from hamsterdan.host.publication_qualification import (
    AtomicSetupPush,
    PublicationQualification,
    QualificationCategory,
    SetupCategory,
    observe_setup_boundary,
)


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


def test_atomic_setup_push_spends_before_one_exact_command(tmp_path) -> None:
    root = tmp_path / "private"
    root.mkdir(mode=0o700)
    commands: list[tuple[str, ...]] = []
    base, head = "a" * 40, "b" * 40

    outcome = AtomicSetupPush(root / "push-spent").push(
        "https://github.com/owner/target.git",
        base,
        head,
        lambda command: commands.append(command) or 0,
    )

    assert commands == [
        (
            "git",
            "push",
            "--atomic",
            "https://github.com/owner/target.git",
            f"{base}:refs/heads/main",
            f"{head}:refs/heads/hamsterdan/ds11-live-v4",
        )
    ]
    assert outcome.command_succeeded and outcome.attempted and outcome.category is None
    assert outcome.sanitized() == {"attempted": True, "command_succeeded": True, "category": ""}
    assert (root / "push-spent").stat().st_mode & 0o777 == 0o600


def test_atomic_setup_timeout_is_closed_sanitized_and_durably_spent(tmp_path) -> None:
    root = tmp_path / "private"
    root.mkdir(mode=0o700)
    coordinate = "owner/private-timeout-canary"
    diagnostic = "credential-and-coordinate-private-diagnostic"
    spent = root / "push-spent"

    def timeout(command: tuple[str, ...]) -> int:
        raise subprocess.TimeoutExpired(command, 1, output=diagnostic, stderr=coordinate)

    outcome = AtomicSetupPush(spent).push(
        f"https://github.com/{coordinate}.git",
        "a" * 40,
        "b" * 40,
        timeout,
    )
    retained = repr(outcome) + repr(outcome.sanitized())

    assert outcome.category is SetupCategory.BOUNDARY_UNAVAILABLE
    assert outcome.attempted and not outcome.command_succeeded
    assert coordinate not in retained and diagnostic not in retained

    calls: list[tuple[str, ...]] = []
    replay = AtomicSetupPush(spent).push(
        "https://github.com/owner/another-target.git",
        "c" * 40,
        "d" * 40,
        lambda command: calls.append(command) or 0,
    )
    assert calls == []
    assert replay.category is SetupCategory.ALREADY_SPENT
    assert not replay.attempted and not replay.command_succeeded


def test_atomic_setup_nonzero_or_throwing_runner_never_retains_private_diagnostics(tmp_path) -> None:
    for name, runner, category in (
        ("nonzero", lambda _command: 1, SetupCategory.PUSH_UNCONFIRMED),
        (
            "throwing",
            lambda _command: (_ for _ in ()).throw(RuntimeError("private runner diagnostic")),
            SetupCategory.BOUNDARY_UNAVAILABLE,
        ),
        ("malformed", lambda _command: True, SetupCategory.BOUNDARY_UNAVAILABLE),
    ):
        root = tmp_path / name
        root.mkdir(mode=0o700)
        outcome = AtomicSetupPush(root / "push-spent").push(
            "https://github.com/owner/private-target.git",
            "a" * 40,
            "b" * 40,
            runner,
        )
        assert outcome.category is category
        assert "private" not in repr(outcome) + repr(outcome.sanitized())


@pytest.mark.parametrize(
    ("remote", "base", "head"),
    [
        ("https://token@github.com/owner/target.git", "a" * 40, "b" * 40),
        ("https://github.com/owner/target.git?token=private", "a" * 40, "b" * 40),
        ("https://github.com/owner/target.git?", "a" * 40, "b" * 40),
        ("https://github.com/owner/target.git#", "a" * 40, "b" * 40),
        ("https://github.com:/owner/target.git", "a" * 40, "b" * 40),
        ("https://GITHUB.COM/owner/target.git", "a" * 40, "b" * 40),
        ("\nhttps://github.com/owner/target.git", "a" * 40, "b" * 40),
        ("https://git\thub.com/owner/target.git", "a" * 40, "b" * 40),
        ("https://example.invalid/owner/target.git", "a" * 40, "b" * 40),
        ("https://github.com/owner/target.git", "A" * 40, "b" * 40),
        ("https://github.com/owner/target.git", "a" * 40, "a" * 40),
    ],
)
def test_invalid_atomic_setup_command_is_refused_before_spending(
    tmp_path,
    remote: str,
    base: str,
    head: str,
) -> None:
    root = tmp_path / "private"
    root.mkdir(mode=0o700)
    calls: list[tuple[str, ...]] = []

    with pytest.raises(ValueError, match="atomic setup command is invalid"):
        AtomicSetupPush(root / "push-spent").push(remote, base, head, lambda command: calls.append(command) or 0)

    assert calls == [] and not (root / "push-spent").exists()


def test_atomic_setup_rejects_string_subclasses_before_formatting_or_spending(tmp_path) -> None:
    class ForcedRef(str):
        def __format__(self, _format_spec: str) -> str:
            return "+" + str(self)

    root = tmp_path / "private"
    root.mkdir(mode=0o700)
    calls: list[tuple[str, ...]] = []

    with pytest.raises(ValueError, match="atomic setup command is invalid"):
        AtomicSetupPush(root / "push-spent").push(
            "https://github.com/owner/target.git",
            ForcedRef("a" * 40),
            "b" * 40,
            lambda command: calls.append(command) or 0,
        )

    assert calls == [] and not (root / "push-spent").exists()


def test_atomic_setup_fence_failure_is_closed_without_running(tmp_path) -> None:
    unsafe = tmp_path / "unsafe"
    unsafe.mkdir(mode=0o755)
    calls: list[tuple[str, ...]] = []

    outcome = AtomicSetupPush(unsafe / "push-spent").push(
        "https://github.com/owner/target.git",
        "a" * 40,
        "b" * 40,
        lambda command: calls.append(command) or 0,
    )

    assert calls == []
    assert outcome.category is SetupCategory.FENCE_UNAVAILABLE
    assert not outcome.attempted and not outcome.command_succeeded


def test_atomic_setup_syncs_file_then_directory_before_running(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = tmp_path / "private"
    root.mkdir(mode=0o700)
    real_fsync = os.fsync
    synced: list[str] = []

    def fsync(descriptor: int) -> None:
        mode = os.fstat(descriptor).st_mode
        synced.append("directory" if stat.S_ISDIR(mode) else "file")
        real_fsync(descriptor)

    monkeypatch.setattr(os, "fsync", fsync)

    outcome = AtomicSetupPush(root / "push-spent").push(
        "https://github.com/owner/target.git",
        "a" * 40,
        "b" * 40,
        lambda _command: 0 if synced == ["file", "directory"] else 1,
    )

    assert outcome.command_succeeded and synced == ["file", "directory"]


@pytest.mark.parametrize("failed_kind", ["file", "directory"])
def test_atomic_setup_sync_failure_never_runs(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
    failed_kind: str,
) -> None:
    root = tmp_path / "private"
    root.mkdir(mode=0o700)
    real_fsync = os.fsync
    calls: list[tuple[str, ...]] = []

    def fsync(descriptor: int) -> None:
        kind = "directory" if stat.S_ISDIR(os.fstat(descriptor).st_mode) else "file"
        if kind == failed_kind:
            raise OSError("private sync diagnostic")
        real_fsync(descriptor)

    monkeypatch.setattr(os, "fsync", fsync)
    outcome = AtomicSetupPush(root / "push-spent").push(
        "https://github.com/owner/target.git",
        "a" * 40,
        "b" * 40,
        lambda command: calls.append(command) or 0,
    )

    assert calls == []
    assert outcome.category is SetupCategory.FENCE_UNAVAILABLE
    assert not outcome.attempted


def test_atomic_setup_close_failure_is_sanitized_without_running(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = tmp_path / "private"
    root.mkdir(mode=0o700)
    real_close = os.close
    calls: list[tuple[str, ...]] = []

    def close(descriptor: int) -> None:
        directory = stat.S_ISDIR(os.fstat(descriptor).st_mode)
        real_close(descriptor)
        if directory:
            raise OSError("private close diagnostic")

    monkeypatch.setattr(os, "close", close)
    outcome = AtomicSetupPush(root / "push-spent").push(
        "https://github.com/owner/private-target.git",
        "a" * 40,
        "b" * 40,
        lambda command: calls.append(command) or 0,
    )

    assert calls == []
    assert outcome.category is SetupCategory.FENCE_UNAVAILABLE
    assert not outcome.attempted
    assert "private" not in repr(outcome) + repr(outcome.sanitized())


def test_atomic_setup_forces_exact_marker_mode_under_restrictive_umask(tmp_path) -> None:
    root = tmp_path / "private"
    root.mkdir(mode=0o700)
    previous = os.umask(0o777)
    try:
        outcome = AtomicSetupPush(root / "push-spent").push(
            "https://github.com/owner/target.git",
            "a" * 40,
            "b" * 40,
            lambda _command: 0,
        )
    finally:
        os.umask(previous)

    assert outcome.command_succeeded
    assert stat.S_IMODE((root / "push-spent").stat().st_mode) == 0o600


def test_atomic_setup_parent_substitution_never_runs(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = tmp_path / "private"
    displaced = tmp_path / "displaced"
    root.mkdir(mode=0o700)
    spent = root / "push-spent"
    real_open = os.open
    substituted = False
    calls: list[tuple[str, ...]] = []

    def open_file(
        path: str | bytes | Path,
        flags: int,
        mode: int = 0o777,
        *,
        dir_fd: int | None = None,
    ) -> int:
        nonlocal substituted
        if not substituted and (Path(path) == spent or path == spent.name):
            root.rename(displaced)
            root.mkdir(mode=0o700)
            substituted = True
        return real_open(path, flags, mode, dir_fd=dir_fd)

    monkeypatch.setattr(os, "open", open_file)
    outcome = AtomicSetupPush(spent).push(
        "https://github.com/owner/target.git",
        "a" * 40,
        "b" * 40,
        lambda command: calls.append(command) or 0,
    )

    assert substituted and calls == []
    assert outcome.category is SetupCategory.FENCE_UNAVAILABLE
    assert not outcome.attempted


def test_atomic_setup_short_marker_write_remains_closed(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = tmp_path / "private"
    root.mkdir(mode=0o700)
    calls: list[tuple[str, ...]] = []
    monkeypatch.setattr(os, "write", lambda _descriptor, value: len(value) - 1)

    outcome = AtomicSetupPush(root / "push-spent").push(
        "https://github.com/owner/target.git",
        "a" * 40,
        "b" * 40,
        lambda command: calls.append(command) or 0,
    )

    assert calls == []
    assert outcome.category is SetupCategory.FENCE_UNAVAILABLE
    assert not outcome.attempted

    replay = AtomicSetupPush(root / "push-spent").push(
        "https://github.com/owner/target.git",
        "a" * 40,
        "b" * 40,
        lambda command: calls.append(command) or 0,
    )
    assert calls == [] and replay.category is SetupCategory.FENCE_UNAVAILABLE


def test_atomic_setup_existing_symlink_marker_never_runs(tmp_path) -> None:
    root = tmp_path / "private"
    root.mkdir(mode=0o700)
    outside = tmp_path / "outside"
    outside.write_text("atomic-two-ref-v1\n")
    (root / "push-spent").symlink_to(outside)
    calls: list[tuple[str, ...]] = []

    outcome = AtomicSetupPush(root / "push-spent").push(
        "https://github.com/owner/target.git",
        "a" * 40,
        "b" * 40,
        lambda command: calls.append(command) or 0,
    )

    assert calls == []
    assert outcome.category is SetupCategory.FENCE_UNAVAILABLE
    assert not outcome.attempted


def test_setup_observation_timeout_never_renders_private_command_or_diagnostics() -> None:
    coordinate = "owner/private-observation-canary"
    diagnostic = "private-provider-diagnostic"

    def observe() -> bool:
        raise subprocess.TimeoutExpired(("gh", "api", f"repos/{coordinate}/branches"), 30, stderr=diagnostic)

    outcome = observe_setup_boundary(observe)
    retained = repr(outcome) + repr(outcome.sanitized())

    assert not outcome.confirmed
    assert outcome.category is SetupCategory.BOUNDARY_UNAVAILABLE
    assert coordinate not in retained and diagnostic not in retained


@pytest.mark.parametrize(
    ("observer", "category"),
    [
        (lambda: False, SetupCategory.OBSERVATION_UNCONFIRMED),
        (lambda: "yes", SetupCategory.BOUNDARY_UNAVAILABLE),
        (
            lambda: (_ for _ in ()).throw(RuntimeError("private observation diagnostic")),
            SetupCategory.BOUNDARY_UNAVAILABLE,
        ),
    ],
)
def test_setup_observation_requires_strict_confirmation_without_retaining_diagnostics(observer, category) -> None:
    outcome = observe_setup_boundary(observer)

    assert not outcome.confirmed and outcome.category is category
    assert "private" not in repr(outcome) + repr(outcome.sanitized())
