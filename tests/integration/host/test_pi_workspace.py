from __future__ import annotations

import io
import subprocess
import tarfile
from hashlib import sha256
from pathlib import Path

import pytest
from petrus.agenticus.hands.contract import ToolMethod
from petrus.motus.execution.archive import extract_workspace_archive, workspace_archive

from hamsterdan.agents import CodingRequest, ReviewRequest
from hamsterdan.agents.pi import PiWorkspaceError
from hamsterdan.host import pi_workspace
from hamsterdan.host.pi_workspace import GitPiWorkspaceProvider, _validated_entries


def git(root: Path, *arguments: str) -> str:
    return subprocess.run(
        ("git", "-C", str(root), *arguments), check=True, capture_output=True, text=True
    ).stdout.strip()


@pytest.fixture
def repository(tmp_path: Path) -> tuple[Path, str]:
    root = tmp_path / "repository"
    root.mkdir()
    git(root, "init", "-q")
    git(root, "config", "user.name", "Test")
    git(root, "config", "user.email", "test@example.invalid")
    (root / "keep.txt").write_text("before\n")
    (root / "delete.txt").write_text("delete\n")
    (root / ".gitignore").write_text("ignored.log\n")
    tool = root / "tool"
    tool.write_text("#!/bin/sh\n")
    tool.chmod(0o755)
    git(root, "add", ".")
    git(root, "commit", "-qm", "base")
    return root, git(root, "rev-parse", "HEAD")


def request(head: str) -> CodingRequest:
    return CodingRequest("change", "owner/repo", 7, 2, head, head, "hamsterdan/change/test")


def test_unchanged_workspace_is_exact_and_private_stages_are_removed(
    tmp_path: Path, repository: tuple[Path, str]
) -> None:
    source, head = repository
    receiver = GitPiWorkspaceProvider(tmp_path / "receiver")

    with receiver.open("coding", str(source), request(head), "pi:unchanged") as prepared:
        assert prepared.digest == sha256(prepared.archive).hexdigest()
        assert prepared.correlation.startswith("hamsterdan-pr-v1:")
        assert prepared.policy.writable_roots == frozenset({"."})
        assert prepared.policy.max_tool_calls == 32
        assert ToolMethod.WORKSPACE_SHELL not in prepared.policy.capabilities
        assert prepared.reconcile(prepared.archive) == ("", [])

    assert list(receiver.root.iterdir()) == []


def test_non_coding_workspace_policy_has_no_mutation_authority(tmp_path: Path, repository: tuple[Path, str]) -> None:
    source, head = repository
    receiver = GitPiWorkspaceProvider(tmp_path / "receiver")

    with receiver.open("review", str(source), request(head), "pi:review") as prepared:
        assert prepared.policy.writable_paths == prepared.policy.writable_roots == frozenset()
        assert prepared.policy.capabilities == frozenset({ToolMethod.WORKSPACE_READ, ToolMethod.WORKSPACE_SEARCH})
        assert prepared.policy.max_tool_calls == 16

    assert list(receiver.root.iterdir()) == []


def test_review_workspace_supplies_the_requested_diff_and_exact_numbered_head(
    tmp_path: Path, repository: tuple[Path, str]
) -> None:
    source, base = repository
    (source / "keep.txt").write_text("first\n\nthird\n")
    git(source, "add", "keep.txt")
    git(source, "commit", "-qm", "change")
    head = git(source, "rev-parse", "HEAD")
    review = ReviewRequest("owner/repo", 7, 2, head, base, "diff.patch")
    receiver = GitPiWorkspaceProvider(tmp_path / "receiver")

    with receiver.open("review", str(source), review, "pi:review-input") as prepared:
        files = tmp_path / "files"
        extract_workspace_archive(prepared.archive, files)
        assert (files / "diff.patch").read_text().strip() == git(source, "diff", f"{base}...{head}")
        assert (files / "diff.patch.lines").read_text() == "keep.txt\n1: first\n2: \n3: third\n"
        assert ToolMethod.WORKSPACE_WRITE not in prepared.policy.capabilities

    assert list(receiver.root.iterdir()) == []


def test_changed_workspace_derives_reproducible_add_modify_delete_and_executable_patch(
    tmp_path: Path, repository: tuple[Path, str]
) -> None:
    source, head = repository
    receiver = GitPiWorkspaceProvider(tmp_path / "receiver")
    result = tmp_path / "settled"

    with receiver.open("coding", str(source), request(head), "pi:changed") as prepared:
        extract_workspace_archive(prepared.archive, result)
        (result / "keep.txt").write_text("after\n")
        (result / "delete.txt").unlink()
        added = result / "added.sh"
        added.write_text("#!/bin/sh\nexit 0\n")
        added.chmod(0o755)
        patch, changed = prepared.reconcile(workspace_archive(result))

    assert changed == ["added.sh", "delete.txt", "keep.txt"]
    assert "new file mode 100755" in patch
    assert "deleted file mode 100644" in patch
    assert "-before" in patch and "+after" in patch
    assert list(receiver.root.iterdir()) == []


@pytest.mark.parametrize("path", ["diff.patch", "diff.patch.lines"])
def test_review_inputs_never_overwrite_a_tracked_file(tmp_path: Path, repository: tuple[Path, str], path: str) -> None:
    source, base = repository
    (source / path).write_text("repository-owned\n")
    git(source, "add", path)
    git(source, "commit", "-qm", "tracked input name")
    head = git(source, "rev-parse", "HEAD")
    review = ReviewRequest("owner/repo", 7, 2, head, base, "diff.patch")
    receiver = GitPiWorkspaceProvider(tmp_path / "receiver")

    with (
        pytest.raises(PiWorkspaceError, match="collide"),
        receiver.open("review", str(source), review, "pi:collision"),
    ):
        raise AssertionError("colliding review input must not enter the agent")

    assert (source / path).read_text() == "repository-owned\n"
    assert list(receiver.root.iterdir()) == []


def test_ignored_result_file_is_part_of_the_canonical_patch(tmp_path: Path, repository: tuple[Path, str]) -> None:
    source, head = repository
    receiver = GitPiWorkspaceProvider(tmp_path / "receiver")
    result = tmp_path / "settled"

    with receiver.open("coding", str(source), request(head), "pi:ignored") as prepared:
        extract_workspace_archive(prepared.archive, result)
        (result / "ignored.log").write_text("must not disappear\n")
        patch, changed = prepared.reconcile(workspace_archive(result))

    assert changed == ["ignored.log"]
    assert "must not disappear" in patch
    assert list(receiver.root.iterdir()) == []


@pytest.mark.parametrize(
    ("name", "kind", "mode", "link"),
    [
        ("../escape", tarfile.REGTYPE, 0o644, ""),
        ("/absolute", tarfile.REGTYPE, 0o644, ""),
        (".git/config", tarfile.REGTYPE, 0o644, ""),
        (".petrus-hands-stage/value", tarfile.REGTYPE, 0o644, ""),
        ("link", tarfile.SYMTYPE, 0o777, "keep.txt"),
        ("hard", tarfile.LNKTYPE, 0o644, "keep.txt"),
        ("device", tarfile.FIFOTYPE, 0o644, ""),
        ("mode", tarfile.REGTYPE, 0o600, ""),
    ],
)
def test_archive_rejects_unsafe_paths_links_special_files_and_modes(
    name: str, kind: bytes, mode: int, link: str
) -> None:
    info = tarfile.TarInfo(name)
    info.type, info.mode, info.linkname = kind, mode, link
    content = b"value" if kind == tarfile.REGTYPE else b""
    info.size = len(content)

    with pytest.raises(PiWorkspaceError):
        _validated_entries(_tar((info, content)))


def test_archive_rejects_duplicate_malformed_missing_and_oversized(monkeypatch: pytest.MonkeyPatch) -> None:
    first = tarfile.TarInfo("duplicate")
    first.mode, first.size = 0o644, 1
    second = tarfile.TarInfo("duplicate")
    second.mode, second.size = 0o644, 1
    with pytest.raises(PiWorkspaceError, match="duplicated"):
        _validated_entries(_tar((first, b"a"), (second, b"b")))
    for malformed in (b"", b"not-a-tar"):
        with pytest.raises(PiWorkspaceError):
            _validated_entries(malformed)
    monkeypatch.setattr(pi_workspace, "MAX_WORKSPACE_BYTES", 10)
    with pytest.raises(PiWorkspaceError, match="oversized"):
        _validated_entries(b"x" * 11)


def test_stale_head_fails_before_runtime_and_cleans_stage(tmp_path: Path, repository: tuple[Path, str]) -> None:
    source, _ = repository
    receiver = GitPiWorkspaceProvider(tmp_path / "receiver")

    with pytest.raises(PiWorkspaceError), receiver.open("coding", str(source), request("f" * 40), "pi:stale"):
        raise AssertionError("stale workspace must not be admitted")

    assert list(receiver.root.iterdir()) == []


def test_input_size_is_rejected_before_reading_beyond_bound(
    tmp_path: Path, repository: tuple[Path, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    source, _ = repository
    large = source / "large.bin"
    large.write_bytes(b"x" * 32)
    git(source, "add", "large.bin")
    git(source, "commit", "-qm", "large")
    head = git(source, "rev-parse", "HEAD")
    receiver = GitPiWorkspaceProvider(tmp_path / "receiver")
    monkeypatch.setattr(pi_workspace, "MAX_WORKSPACE_BYTES", 50)

    with (
        pytest.raises(PiWorkspaceError, match="expanded bound"),
        receiver.open("coding", str(source), request(head), "pi:oversized-input"),
    ):
        raise AssertionError("oversized input must not be admitted")
    assert list(receiver.root.iterdir()) == []


def test_body_failure_propagates_without_reclassification_and_cleans_stage(
    tmp_path: Path, repository: tuple[Path, str]
) -> None:
    source, head = repository
    receiver = GitPiWorkspaceProvider(tmp_path / "receiver")
    expected = RuntimeError("body failure")

    with (
        pytest.raises(RuntimeError, match="body failure") as caught,
        receiver.open("coding", str(source), request(head), "pi:body-failure"),
    ):
        raise expected

    assert caught.value is expected
    assert list(receiver.root.iterdir()) == []


def test_cleanup_uncertainty_is_fail_closed(
    tmp_path: Path, repository: tuple[Path, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    source, head = repository
    receiver = GitPiWorkspaceProvider(tmp_path / "receiver")
    monkeypatch.setattr(pi_workspace.shutil, "rmtree", lambda path: (_ for _ in ()).throw(OSError("synthetic")))

    with (
        pytest.raises(PiWorkspaceError, match="cleanup is unverified"),
        receiver.open("coding", str(source), request(head), "pi:cleanup"),
    ):
        pass


def _tar(*entries: tuple[tarfile.TarInfo, bytes]) -> bytes:
    output = io.BytesIO()
    with tarfile.open(fileobj=output, mode="w", format=tarfile.PAX_FORMAT) as archive:
        for info, content in entries:
            info.uid = info.gid = 0
            info.uname = info.gname = ""
            info.mtime = 0
            archive.addfile(info, io.BytesIO(content) if info.isfile() else None)
    return output.getvalue()
