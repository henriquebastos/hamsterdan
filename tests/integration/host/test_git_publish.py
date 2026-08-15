"""Privileged Git publication boundary tests; all remotes are local."""

import base64
import os
import subprocess
from pathlib import Path

import pytest
from petrus.motus.execution.archive import extract_workspace_archive, workspace_archive

from hamsterdan.agents import CodingRequest, CodingResult
from hamsterdan.contracts.readiness import ChangeResult
from hamsterdan.github_app.gateway import GitHubAuthority, GitHubObjectWriteError
from hamsterdan.github_app.models import PullRequestSnapshot, WireResponse
from hamsterdan.host.git_publish import (
    GitPublishError,
    GitReconciliation,
    HostGitPublisher,
    PublicationCategory,
    _publication_directory,
    _same_repository,
    _validate_commit_message,
    _validate_declared_paths,
)
from hamsterdan.host.pi_workspace import GitPiWorkspaceProvider
from hamsterdan.host.publication_qualification import PublicationQualification


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

    def create_tree(self, **kwargs):
        return GitHubAuthority.create_tree(self, **kwargs)

    def create_commit(self, **kwargs):
        return GitHubAuthority.create_commit(self, **kwargs)


class GraphQL:
    def __init__(self):
        self.calls: list[tuple[str, str, str, str]] = []
        self.fail = False

    def compare_and_swap_ref(self, repository: str, ref: str, expected_head: str, commit: str) -> None:
        self.calls.append((repository, ref, expected_head, commit))
        if self.fail:
            from hamsterdan.github_app.models import GitHubBoundaryError

            raise GitHubBoundaryError("stale")


class LocalObjectTransport:
    """GitHub object-write subset backed by one credential-free local repository."""

    def __init__(self, root: Path):
        self.root = root
        self.created: set[str] = set()

    def request(self, method: str, path: str, body=None) -> WireResponse:
        assert method == "POST" and isinstance(body, dict)
        if path.endswith("/git/blobs"):
            content = base64.b64decode(body["content"])
            completed = subprocess.run(
                ("git", "-C", str(self.root), "hash-object", "-w", "--stdin"),
                input=content,
                check=True,
                capture_output=True,
            )
            sha = completed.stdout.decode().strip()
        elif path.endswith("/git/trees"):
            index = self.root / ".git" / "publication-index"
            index.unlink(missing_ok=True)
            environment = os.environ | {"GIT_INDEX_FILE": str(index)}
            subprocess.run(
                ("git", "-C", str(self.root), "read-tree", body["base_tree"]),
                check=True,
                capture_output=True,
                env=environment,
            )
            for entry in body["tree"]:
                if entry["sha"] is None:
                    command = ("git", "-C", str(self.root), "update-index", "--force-remove", "--", entry["path"])
                else:
                    command = (
                        "git",
                        "-C",
                        str(self.root),
                        "update-index",
                        "--add",
                        "--cacheinfo",
                        f"{entry['mode']},{entry['sha']},{entry['path']}",
                    )
                subprocess.run(command, check=True, capture_output=True, env=environment)
            completed = subprocess.run(
                ("git", "-C", str(self.root), "write-tree"),
                check=True,
                capture_output=True,
                text=True,
                env=environment,
            )
            sha = completed.stdout.strip()
            index.unlink()
        elif path.endswith("/git/commits"):
            environment = os.environ | {
                "GIT_AUTHOR_NAME": body["author"]["name"],
                "GIT_AUTHOR_EMAIL": body["author"]["email"],
                "GIT_COMMITTER_NAME": body["committer"]["name"],
                "GIT_COMMITTER_EMAIL": body["committer"]["email"],
                "GIT_AUTHOR_DATE": "2001-01-01T00:00:00Z",
                "GIT_COMMITTER_DATE": "2001-01-01T00:00:00Z",
            }
            command = ["git", "-C", str(self.root), "commit-tree", body["tree"]]
            for parent in body["parents"]:
                command.extend(("-p", parent))
            completed = subprocess.run(
                command,
                input=body["message"],
                check=True,
                capture_output=True,
                text=True,
                env=environment,
            )
            sha = completed.stdout.strip()
        else:
            raise AssertionError("unexpected local authority request")
        self.created.add(sha)
        return WireResponse(201, {"sha": sha})


class LocalRefCAS:
    def __init__(self, authority: LocalPublicationAuthority, root: Path, remote: Path):
        self.authority, self.root, self.remote = authority, root, remote
        self.calls = 0

    def compare_and_swap_ref(self, repository: str, ref: str, expected_head: str, commit: str) -> None:
        assert repository == self.authority.repository
        assert ref == "refs/heads/topic"
        assert expected_head == self.authority.head
        assert commit in self.authority.transport.created
        subprocess.run(
            ("git", "-C", str(self.root), "push", "--quiet", str(self.remote), f"{commit}:{ref}"),
            check=True,
            capture_output=True,
        )
        self.authority.head = commit
        self.calls += 1


class LocalPublicationAuthority:
    repository = "owner/repo"
    root = "/repos/owner/repo"

    def __init__(self, work: Path, remote: Path, head: str):
        self.head = self.base = head
        self.transport = LocalObjectTransport(work)
        self.graphql = LocalRefCAS(self, work, remote)

    def pull_request(self) -> PullRequestSnapshot:
        return PullRequestSnapshot(
            self.repository,
            7,
            "open",
            False,
            self.head,
            self.base,
            "topic",
            "main",
            True,
            False,
            False,
            "qualifier",
            "clean",
            "https://example.invalid/pull/7",
            self.repository,
        )

    def create_tree(self, **kwargs):
        return GitHubAuthority.create_tree(self, **kwargs)

    def create_commit(self, **kwargs):
        return GitHubAuthority.create_commit(self, **kwargs)


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


def test_local_publication_io_failure_has_closed_sanitized_category(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "hamsterdan.host.git_publish.tempfile.TemporaryDirectory",
        lambda **kwargs: (_ for _ in ()).throw(OSError("private path")),
    )

    with pytest.raises(GitPublishError, match="Git operation failed") as caught, _publication_directory():
        raise AssertionError("unavailable directory must not yield")

    assert caught.value.category is PublicationCategory.GIT_OPERATION


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


@pytest.mark.parametrize("failure", ("blob", "tree", "commit"))
def test_provider_object_creation_requires_exact_proof_before_continuing(failure: str) -> None:
    authority = Authority()
    valid = {
        "blob": WireResponse(201, {"sha": "a" * 40}),
        "tree": WireResponse(201, {"sha": "b" * 40}),
        "commit": WireResponse(201, {"sha": "c" * 40}),
    }
    order = ("blob", "tree", "commit")
    authority.transport.responses.extend(
        WireResponse(200, {"sha": "f" * 40}) if kind == failure else valid[kind] for kind in order
    )

    with pytest.raises(GitHubObjectWriteError, match=f"{failure} creation"):
        tree = authority.create_tree(
            base_tree="d" * 40,
            entries=(("file.txt", "100644", b"content"),),
        )
        authority.create_commit(
            tree=tree,
            parents=("e" * 40,),
            message="message",
            name="Hamsterdan",
            email="hamster-dan[bot]@users.noreply.github.com",
        )

    assert len(authority.transport.calls) == order.index(failure) + 1


def test_host_refuses_unexpected_created_tree_before_commit_or_ref_update(
    repository: tuple[Path, Path, str, str],
) -> None:
    root, remote, first, _ = repository
    (root / "file.txt").write_text("changed\n")
    git(root, "add", "file.txt")
    base_tree = git(root, "rev-parse", f"{first}^{{tree}}")
    expected_tree = git(root, "write-tree")
    authority = Authority()
    authority.transport.responses.extend((WireResponse(201, {"sha": "a" * 40}), WireResponse(201, {"sha": "b" * 40})))

    with pytest.raises(GitPublishError) as caught:
        publisher(remote, authority)._create_commit(root, base_tree, expected_tree, ["file.txt"], [first], "message")

    assert caught.value.category is PublicationCategory.OBJECT_WRITE
    assert [path for _, path, _ in authority.transport.calls] == [
        "/repos/owner/repo/git/blobs",
        "/repos/owner/repo/git/trees",
    ]
    assert authority.graphql.calls == []


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


def test_reconciliation_finds_an_operation_beneath_a_later_fast_forward(
    repository: tuple[Path, Path, str, str],
) -> None:
    root, remote, first, _ = repository
    tree = git(root, "rev-parse", f"{first}^{{tree}}")
    operation = git(
        root,
        "commit-tree",
        tree,
        "-p",
        first,
        input_text="proposal\n\nHamsterdan-Operation: push:one\nHamsterdan-Payload-Digest: digest\n",
    )
    later = git(root, "commit-tree", tree, "-p", operation, input_text="later\n")
    git(root, "push", "-q", "--force", "origin", f"{later}:refs/heads/topic")
    authority = LocalPublicationAuthority(root, remote, first)
    authority.head = later

    result = HostGitPublisher(authority, str(remote)).reconcile(  # type: ignore[arg-type]
        operation="push:one",
        payload_digest="digest",
        expected_head=first,
        base_head=first,
    )

    assert result == GitReconciliation("existing", later, operation, (first,))


def test_merge_base_reconciliation_requires_the_exact_ordered_parents(
    repository: tuple[Path, Path, str, str],
) -> None:
    root, remote, first, second = repository
    tree = git(root, "rev-parse", f"{second}^{{tree}}")
    operation = git(
        root,
        "commit-tree",
        tree,
        "-p",
        first,
        "-p",
        second,
        input_text="proposal\n\nHamsterdan-Operation: push:merge\nHamsterdan-Payload-Digest: digest\n",
    )
    git(root, "push", "-q", "--force", "origin", f"{operation}:refs/heads/topic")
    authority = LocalPublicationAuthority(root, remote, first)
    authority.head = operation

    result = HostGitPublisher(authority, str(remote)).reconcile(  # type: ignore[arg-type]
        operation="push:merge",
        payload_digest="digest",
        expected_head=first,
        base_head=second,
        merge_base=True,
    )

    assert result == GitReconciliation("existing", operation, operation, (first, second))


def test_reconciliation_proves_coherent_absence(
    repository: tuple[Path, Path, str, str],
) -> None:
    root, remote, first, _ = repository
    authority = LocalPublicationAuthority(root, remote, first)

    result = HostGitPublisher(authority, str(remote)).reconcile(  # type: ignore[arg-type]
        operation="push:absent",
        payload_digest="digest",
        expected_head=first,
        base_head=first,
    )

    assert result == GitReconciliation("absent", first)


@pytest.mark.parametrize("collision", ["digest", "parents", "duplicate"])
def test_reconciliation_rejects_operation_identity_collisions(
    repository: tuple[Path, Path, str, str], collision: str
) -> None:
    root, remote, first, second = repository
    tree = git(root, "rev-parse", f"{first}^{{tree}}")
    digest = "different" if collision == "digest" else "digest"
    parents = (first, second) if collision == "parents" else (first,)
    arguments = ["commit-tree", tree]
    for parent in parents:
        arguments.extend(("-p", parent))
    operation = git(
        root,
        *arguments,
        input_text=f"proposal\n\nHamsterdan-Operation: push:one\nHamsterdan-Payload-Digest: {digest}\n",
    )
    head = operation
    if collision == "duplicate":
        head = git(
            root,
            "commit-tree",
            tree,
            "-p",
            operation,
            input_text="again\n\nHamsterdan-Operation: push:one\nHamsterdan-Payload-Digest: digest\n",
        )
    git(root, "push", "-q", "--force", "origin", f"{head}:refs/heads/topic")
    authority = LocalPublicationAuthority(root, remote, first)
    authority.head = head

    with pytest.raises(GitPublishError) as caught:
        HostGitPublisher(authority, str(remote)).reconcile(  # type: ignore[arg-type]
            operation="push:one",
            payload_digest="digest",
            expected_head=first,
            base_head=first,
        )

    assert caught.value.category is PublicationCategory.IDEMPOTENCY


def test_host_derived_patch_publishes_and_replays_through_complete_local_authority(
    tmp_path: Path, repository: tuple[Path, Path, str, str]
) -> None:
    work, remote, head, _ = repository
    receiver = GitPiWorkspaceProvider(tmp_path / "receiver")
    request = CodingRequest("change", "owner/repo", 7, 2, head, head, "hamsterdan/change/diagnostic")
    result_root = tmp_path / "settled"

    with receiver.open("coding", str(remote), request, "change:diagnostic:1") as prepared:
        extract_workspace_archive(prepared.archive, result_root)
        (result_root / "bounded.txt").write_text("qualified\n")
        diff, changed = prepared.reconcile(workspace_archive(result_root))

    result = CodingResult(
        "change",
        request.repository,
        request.pull_request,
        request.epoch,
        request.head,
        request.base,
        request.ref,
        "changed",
        "not_attempted",
        diff,
        changed,
        [{"command": "credential-free", "status": "passed"}],
        "Apply bounded diagnostic change",
    )
    authority = LocalPublicationAuthority(work, remote, head)
    subject = HostGitPublisher(authority, str(remote))  # type: ignore[arg-type]

    published = subject.publish(
        result,
        operation="change:diagnostic",
        payload_digest="d" * 64,
        expected_head=head,
        base_head=head,
    )
    evidence = PublicationQualification()
    evidence.record_original(ChangeResult(2, head, True, published.head), 1)
    recovered = None

    def replay() -> bool:
        nonlocal recovered
        recovered = subject.publish(
            result,
            operation="change:diagnostic",
            payload_digest="d" * 64,
            expected_head=head,
            base_head=head,
        )
        return recovered.recovered

    evidence.run_publication_assertions(
        schema=lambda: True,
        tree=lambda: git(work, "show", f"{published.head}:bounded.txt") == "qualified",
        replay=replay,
    )
    evidence.record_cleanup(not list(receiver.root.iterdir()))

    assert published.head == authority.head
    assert recovered is not None and recovered.head == published.head
    assert authority.graphql.calls == 1
    assert evidence.accepted
