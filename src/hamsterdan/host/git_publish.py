"""Secret-safe host ownership of commits proposed by disposable agents."""

from __future__ import annotations

import base64
import hashlib
import re
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from hamsterdan.agents import CodingResult
from hamsterdan.github_app.gateway import GitHubAuthority
from hamsterdan.github_app.models import GitHubBoundaryError

_SAFE_REF = re.compile(r"[A-Za-z0-9][A-Za-z0-9._/-]{0,254}\Z")


class GitPublishError(RuntimeError):
    """A deliberately credential-free publishing failure."""


@dataclass(frozen=True)
class GitPublishResult:
    head: str
    recovered: bool = False


class HostGitPublisher:
    """Apply a host-captured binary patch and advance one same-repository PR ref."""

    def __init__(
        self,
        authority: GitHubAuthority,
        clone_url: str,
        *,
        commit_name: str = "Hamsterdan",
        commit_email: str = "hamster-dan[bot]@users.noreply.github.com",
    ):
        if not clone_url or ("://" in clone_url and "@" in clone_url.partition("://")[2]):
            raise ValueError("a credential-free clone URL is required")
        if not commit_name.strip() or not commit_email.strip() or "\n" in commit_name + commit_email:
            raise ValueError("explicit commit metadata is invalid")
        self.authority, self.clone_url = authority, clone_url
        self.commit_name, self.commit_email = commit_name, commit_email

    def publish(
        self,
        result: CodingResult,
        *,
        operation: str,
        payload_digest: str,
        expected_head: str,
        base_head: str,
        merge_base: bool = False,
    ) -> GitPublishResult:
        _validate_declared_paths(result.changed_files)
        pull = self.authority.pull_request()
        if result.head != expected_head or result.base != base_head:
            raise GitPublishError("stale or incorrectly correlated Git publication")
        if (
            pull.repository != self.authority.repository
            or pull.head_repository != self.authority.repository
            or not _safe_branch(pull.head_ref)
        ):
            raise GitPublishError("fork or unsafe pull-request ref is not publishable")
        if result.status != "changed" or not result.diff.strip() or _has_conflict_markers(result.diff):
            raise GitPublishError("empty, unchanged, or conflicted agent patch is not publishable")
        with tempfile.TemporaryDirectory(prefix="hamsterdan-git-") as temporary:
            root = Path(temporary) / "repository"
            self._git("clone", "--quiet", "--no-checkout", "--", self.clone_url, str(root))
            self._git("-C", str(root), "checkout", "--quiet", "--detach", expected_head)
            parents = [expected_head, *([base_head] if merge_base else [])]
            recovered = self._recover(root, pull.head_ref, operation, payload_digest, parents)
            if recovered:
                # The snapshot used to select the ref may already be stale.  Re-read
                # GitHub after the remote lookup before treating replay as success.
                verified = self.authority.pull_request()
                if not _same_pull(verified, pull) or verified.head != recovered:
                    raise GitPublishError("recovered operation is not the verified PR head")
                return GitPublishResult(recovered, True)
            if pull.head != expected_head or pull.base != base_head:
                raise GitPublishError("stale or incorrectly correlated Git publication")
            if merge_base:
                self._git("-C", str(root), "cat-file", "-e", f"{base_head}^{{commit}}")
            patch = Path(temporary) / "change.patch"
            patch.write_text(result.diff, encoding="utf-8")
            self._git("-C", str(root), "apply", "--binary", "--index", "--", str(patch))
            changed = self._validate_staged_tree(root)
            if changed != result.changed_files or not changed:
                raise GitPublishError("agent patch files differ from its declared result")
            tree = self._git("-C", str(root), "write-tree", capture=True).strip()
            base_tree = self._git("-C", str(root), "rev-parse", f"{expected_head}^{{tree}}", capture=True).strip()
            message = (
                f"{result.proposed_commit_message}\n\n"
                f"Hamsterdan-Operation: {operation}\nHamsterdan-Payload-Digest: {payload_digest}\n"
            )
            commit = self._create_commit(root, base_tree, tree, changed, parents, message)
            # The earlier snapshot authorized all preparation only.  This fresh
            # provider read and the exact server-side lease jointly authorize the
            # irreversible ref update.
            current = self.authority.pull_request()
            if not _same_pull(current, pull) or current.head != expected_head or current.base != base_head:
                raise GitPublishError("pull request changed before Git publication")
            self._advance_ref(pull.head_ref, expected_head, commit)
            verified = self.authority.pull_request()
            if (
                not _same_pull(verified, pull)
                or verified.head not in {expected_head, commit}
                or verified.base != base_head
            ):
                raise GitPublishError("ref advance succeeded without a coherent PR projection")
            return GitPublishResult(commit)

    def _validate_staged_tree(self, root: Path) -> list[str]:
        changed = self._git("-C", str(root), "diff", "--cached", "--name-only", "-z", capture=True)
        changed_paths = [path for path in changed.split("\0") if path]
        _validate_declared_paths(changed_paths)
        raw = self._git("-C", str(root), "ls-files", "--stage", "-z", capture=True)
        entries: dict[str, list[tuple[str, str]]] = {}
        for entry in raw.split("\0"):
            if not entry:
                continue
            metadata, separator, path = entry.partition("\t")
            fields = metadata.split()
            if not separator or len(fields) != 3:
                raise GitPublishError("staged tree contains an unsafe mode or unmerged entry")
            entries.setdefault(path, []).append((fields[0], fields[2]))
        for path in changed_paths:
            # A deletion has no index entry.  Every present changed entry must be
            # one ordinary stage-zero blob, never a symlink, gitlink, or conflict.
            values = entries.get(path, [])
            if values and (len(values) != 1 or values[0][0] not in {"100644", "100755"} or values[0][1] != "0"):
                raise GitPublishError("staged tree contains an unsafe mode or unmerged entry")
        return changed_paths

    def _recover(self, root: Path, ref: str, operation: str, digest: str, expected_parents: list[str]) -> str:
        remote = self._git("-C", str(root), "ls-remote", "--heads", "origin", f"refs/heads/{ref}", capture=True)
        if not remote:
            return ""
        head = remote.split()[0]
        self._git("-C", str(root), "fetch", "--quiet", "origin", head)
        body = self._git("-C", str(root), "show", "-s", "--format=%B", head, capture=True)
        trailers = body.splitlines()
        operation_line = f"Hamsterdan-Operation: {operation}"
        if operation_line not in trailers:
            return ""
        if trailers.count(operation_line) != 1 or trailers.count(f"Hamsterdan-Payload-Digest: {digest}") != 1:
            raise GitPublishError("stable operation was reused with a different payload")
        parents = self._git("-C", str(root), "show", "-s", "--format=%P", head, capture=True).split()
        if parents != expected_parents:
            raise GitPublishError("recovered operation has unexpected commit parents")
        return head

    def _create_commit(
        self,
        root: Path,
        base_tree: str,
        expected_tree: str,
        changed: list[str],
        parents: list[str],
        message: str,
    ) -> str:
        entries: list[dict[str, object]] = []
        for path in changed:
            index = self._git("-C", str(root), "ls-files", "--stage", "-z", "--", path, capture=True)
            if not index:
                entries.append({"path": path, "mode": "100644", "type": "blob", "sha": None})
                continue
            metadata, separator, observed = index.removesuffix("\0").partition("\t")
            fields = metadata.split()
            if not separator or observed != path or len(fields) != 3 or fields[2] != "0":
                raise GitPublishError("staged tree contains an unsafe mode or unmerged entry")
            mode = fields[0]
            response = self.authority.transport.request(
                "POST",
                f"{self.authority.root}/git/blobs",
                {"content": base64.b64encode((root / path).read_bytes()).decode(), "encoding": "base64"},
            )
            entries.append({"path": path, "mode": mode, "type": "blob", "sha": _created_sha(response, "blob")})
        tree_response = self.authority.transport.request(
            "POST",
            f"{self.authority.root}/git/trees",
            {"base_tree": base_tree, "tree": entries},
        )
        created_tree = _created_sha(tree_response, "tree")
        if created_tree != expected_tree:
            raise GitPublishError("GitHub-created tree differs from the host-validated tree")
        commit_response = self.authority.transport.request(
            "POST",
            f"{self.authority.root}/git/commits",
            {
                "message": message,
                "tree": created_tree,
                "parents": parents,
                "author": {"name": self.commit_name, "email": self.commit_email},
                "committer": {"name": self.commit_name, "email": self.commit_email},
            },
        )
        return _created_sha(commit_response, "commit")

    def _advance_ref(self, ref: str, expected_head: str, commit: str) -> None:
        destination = f"refs/heads/{ref}"
        if self.authority.graphql is None:
            raise GitPublishError("GitHub exact ref compare-and-swap is unavailable")
        try:
            self.authority.graphql.compare_and_swap_ref(self.authority.repository, destination, expected_head, commit)
        except GitHubBoundaryError:
            raise GitPublishError("GitHub rejected or did not prove the exact ref compare-and-swap") from None

    @staticmethod
    def _git(
        *arguments: str, capture: bool = False, input_text: str | None = None, env: dict[str, str] | None = None
    ) -> str:
        try:
            completed = subprocess.run(
                ("git", *arguments), input=input_text, text=True, capture_output=True, env=env, check=True, timeout=60
            )
        except subprocess.CalledProcessError:
            raise GitPublishError("Git operation failed") from None
        return completed.stdout if capture else ""


def _safe_branch(value: str) -> bool:
    return bool(_SAFE_REF.fullmatch(value)) and ".." not in value and "@{" not in value and not value.startswith("-")


def _safe_path(value: str) -> bool:
    if not value or "\x00" in value or "\\" in value or value.startswith("-"):
        return False
    path = PurePosixPath(value)
    parts = path.parts
    raw_parts = value.split("/")
    return (
        not path.is_absolute()
        and all(part not in {"", "."} for part in raw_parts)
        and parts == tuple(raw_parts)
        and ".." not in parts
        and all(part.casefold() != ".git" for part in parts)
        and all(part.casefold() != ".gitmodules" for part in parts)
    )


def _validate_declared_paths(paths: list[str]) -> None:
    if (
        not paths
        or len(paths) != len(set(paths))
        or any(not isinstance(path, str) or not _safe_path(path) for path in paths)
    ):
        raise GitPublishError("declared or staged paths are unsafe")


def _same_pull(current: object, original: object) -> bool:
    names = (
        "repository",
        "number",
        "head_repository",
        "head_ref",
        "base",
        "base_ref",
        "state",
        "draft",
        "merged",
        "closed",
    )
    return all(getattr(current, name) == getattr(original, name) for name in names)


def _has_conflict_markers(diff: str) -> bool:
    return any(line.startswith(("+<<<<<<<", "+=======", "+>>>>>>>")) for line in diff.splitlines())


def _created_sha(response: object, kind: str) -> str:
    status, body = getattr(response, "status", None), getattr(response, "body", None)
    sha = body.get("sha") if isinstance(body, dict) else None
    if status != 201 or not isinstance(sha, str) or not re.fullmatch(r"[0-9a-f]{40}", sha):
        raise GitPublishError(f"GitHub did not prove {kind} creation")
    return sha


def payload_digest(value: object) -> str:
    import json

    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
