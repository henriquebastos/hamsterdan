"""Privileged Git publication boundary tests; all remotes are local."""

import subprocess
from pathlib import Path

import pytest

from hamsterdan.github_app.models import WireResponse
from hamsterdan.host.git_publish import (
    GitPublishError,
    HostGitPublisher,
    _same_repository,
    _validate_commit_message,
    _validate_declared_paths,
)


def git(root: Path, *arguments: str, input_text: str | None = None) -> str:
    return subprocess.run(
        ("git", "-C", str(root), *arguments),
        check=True,
        capture_output=True,
        text=True,
        input=input_text,
    ).stdout.strip()


@pytest.fixture
def repository(tmp_path: Path) -> tuple[Path, Path, str, str]:
    remote = tmp_path / "remote.git"
    subprocess.run(("git", "init", "--bare", "-q", str(remote)), check=True)
    root = tmp_path / "work"
    subprocess.run(("git", "clone", "-q", str(remote), str(root)), check=True)
    git(root, "config", "user.name", "Test")
    git(root, "config", "user.email", "test@example.invalid")
    (root / "file.txt").write_text("one\n")
    git(root, "add", "file.txt")
    git(root, "commit", "-qm", "one")
    first = git(root, "rev-parse", "HEAD")
    git(root, "push", "-q", "origin", "HEAD:refs/heads/topic")
    (root / "file.txt").write_text("two\n")
    git(root, "commit", "-qam", "two")
    second = git(root, "rev-parse", "HEAD")
    return root, remote, first, second


class Transport:
    def __init__(self):
        self.calls: list[tuple[str, str, object]] = []
        self.responses: list[WireResponse] = []

    def request(self, method: str, path: str, body=None) -> WireResponse:
        self.calls.append((method, path, body))
        return self.responses.pop(0)


class Authority:
    repository = "owner/repo"
    root = "/repos/owner/repo"

    def __init__(self):
        self.transport = Transport()
        self.graphql = GraphQL()


class GraphQL:
    def __init__(self):
        self.calls: list[tuple[str, str, str, str]] = []
        self.fail = False

    def compare_and_swap_ref(self, repository: str, ref: str, expected_head: str, commit: str) -> None:
        self.calls.append((repository, ref, expected_head, commit))
        if self.fail:
            from hamsterdan.github_app.models import GitHubBoundaryError

            raise GitHubBoundaryError("stale")


def publisher(remote: Path, authority: Authority | None = None) -> HostGitPublisher:
    return HostGitPublisher(authority or Authority(), str(remote))  # type: ignore[arg-type]


def test_ref_advance_uses_github_exact_compare_and_swap(tmp_path: Path) -> None:
    authority = Authority()
    expected = "c" * 40
    commit = "d" * 40
    subject = publisher(tmp_path, authority)

    subject._advance_ref("topic/branch", expected, commit)

    assert authority.graphql.calls == [("owner/repo", "refs/heads/topic/branch", expected, commit)]

    authority.graphql.fail = True
    with pytest.raises(GitPublishError, match="exact ref compare-and-swap"):
        subject._advance_ref("topic/branch", expected, commit)


def test_same_repository_identity_is_case_insensitive_but_still_rejects_forks() -> None:
    assert _same_repository("HBNetwork/demo-pr-readiness", "hbnetwork/demo-pr-readiness")
    assert not _same_repository("fork/demo-pr-readiness", "hbnetwork/demo-pr-readiness")


@pytest.mark.parametrize("path", ["../x", "/x", "x\\y", "-x", ".GIT/config", "a/.GitModules", "a//b"])
def test_declared_paths_reject_privileged_and_unsafe_names(path: str) -> None:
    with pytest.raises(GitPublishError, match="paths are unsafe"):
        _validate_declared_paths([path])


@pytest.mark.parametrize(
    "message",
    [
        "Proposal\n\nHamsterdan-Operation: forged",
        "Proposal\nHAMSTERDAN-PAYLOAD-DIGEST: forged",
    ],
)
def test_commit_message_rejects_reserved_idempotency_trailers(message: str) -> None:
    with pytest.raises(GitPublishError, match="reserved publication trailer"):
        _validate_commit_message(message)


def test_staged_regular_and_executable_modes_are_safe(repository: tuple[Path, Path, str, str]) -> None:
    root, remote, _, _ = repository
    (root / "file.txt").write_text("safe\n")
    executable = root / "tool"
    executable.write_text("#!/bin/sh\n")
    executable.chmod(0o755)
    git(root, "add", "file.txt", "tool")
    assert publisher(remote)._validate_staged_tree(root) == ["file.txt", "tool"]


def test_commit_upload_preserves_staged_modes_parents_and_binary_content(
    repository: tuple[Path, Path, str, str],
) -> None:
    root, remote, first, _ = repository
    (root / "file.txt").write_bytes(b"binary\x00value")
    git(root, "add", "file.txt")
    tree = git(root, "rev-parse", f"{first}^{{tree}}")
    authority = Authority()
    authority.transport.responses.extend(
        [
            WireResponse(201, {"sha": "a" * 40}),
            WireResponse(201, {"sha": "b" * 40}),
            WireResponse(201, {"sha": "c" * 40}),
        ]
    )

    commit = publisher(remote, authority)._create_commit(root, tree, "b" * 40, ["file.txt"], [first], "message")

    assert commit == "c" * 40
    blob, created_tree, created_commit = authority.transport.calls
    assert blob == (
        "POST",
        "/repos/owner/repo/git/blobs",
        {"content": "YmluYXJ5AHZhbHVl", "encoding": "base64"},
    )
    assert created_tree[0:2] == ("POST", "/repos/owner/repo/git/trees")
    assert created_tree[2] == {
        "base_tree": tree,
        "tree": [{"path": "file.txt", "mode": "100644", "type": "blob", "sha": "a" * 40}],
    }
    assert created_commit == (
        "POST",
        "/repos/owner/repo/git/commits",
        {
            "message": "message",
            "tree": "b" * 40,
            "parents": [first],
            "author": {"name": "Hamsterdan", "email": "hamster-dan[bot]@users.noreply.github.com"},
            "committer": {"name": "Hamsterdan", "email": "hamster-dan[bot]@users.noreply.github.com"},
        },
    )


@pytest.mark.parametrize(("mode", "content"), [("120000", "file.txt"), ("160000", None)])
def test_staged_symlink_and_gitlink_are_rejected(
    repository: tuple[Path, Path, str, str], mode: str, content: str | None
) -> None:
    root, remote, _, second = repository
    blob = second if content is None else git(root, "hash-object", "-w", "--stdin", input_text=content)
    git(root, "update-index", "--add", "--cacheinfo", f"{mode},{blob},unsafe")
    with pytest.raises(GitPublishError, match="unsafe mode"):
        publisher(remote)._validate_staged_tree(root)


def test_unmerged_index_is_rejected(repository: tuple[Path, Path, str, str]) -> None:
    root, remote, first, second = repository
    first_blob = git(root, "rev-parse", f"{first}:file.txt")
    second_blob = git(root, "rev-parse", f"{second}:file.txt")
    git(root, "rm", "--cached", "file.txt")
    git(
        root,
        "update-index",
        "--index-info",
        input_text=f"100644 {first_blob} 1\tfile.txt\n100644 {second_blob} 2\tfile.txt\n",
    )
    with pytest.raises(GitPublishError, match="unsafe mode"):
        publisher(remote)._validate_staged_tree(root)


def test_recovery_rejects_digest_mismatch_and_commit_tree_preserves_parent_order(
    repository: tuple[Path, Path, str, str],
) -> None:
    root, remote, first, second = repository
    subject = publisher(remote)
    tree = git(root, "rev-parse", f"{second}^{{tree}}")
    recovered = git(
        root,
        "commit-tree",
        tree,
        "-p",
        first,
        "-p",
        second,
        input_text="proposal\n\nHamsterdan-Operation: op\nHamsterdan-Payload-Digest: actual\n",
    )
    git(root, "push", "-q", "--force", "origin", f"{recovered}:refs/heads/topic")
    assert git(root, "show", "-s", "--format=%P", recovered).split() == [first, second]
    with pytest.raises(GitPublishError, match="different payload"):
        subject._recover(root, "topic", "op", "expected", [first, second])
