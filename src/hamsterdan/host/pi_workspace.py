"""Private receiving-host proof from settled Pi workspaces to canonical Git patches."""

from __future__ import annotations

import io
import os
import shutil
import stat
import subprocess
import tarfile
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path, PurePosixPath

from petrus.agenticus.hands.contract import ToolMethod
from petrus.agenticus.runtime.pi_a2_host import PiA2RuntimePolicy
from petrus.motus.execution.archive import workspace_archive

from hamsterdan.agents.pi import PiWorkspaceCleanupError, PiWorkspaceError
from hamsterdan.agents.protocol import AgentRequest, ReviewRequest

from .git_publish import _safe_path

MAX_WORKSPACE_BYTES = 64 * 1024 * 1024
MAX_WORKSPACE_ENTRIES = 20_000
MAX_CHANGED_PATHS = 1_000
MAX_PATCH_BYTES = 4_000_000
_DENIED_ROOTS = frozenset({".git", ".gitmodules", ".impetus", ".petrus-hands-stage"})
_READ_POLICY = PiA2RuntimePolicy(frozenset({ToolMethod.WORKSPACE_READ, ToolMethod.WORKSPACE_SEARCH}))
_CODE_POLICY = PiA2RuntimePolicy(
    frozenset({ToolMethod.WORKSPACE_READ, ToolMethod.WORKSPACE_SEARCH, ToolMethod.WORKSPACE_WRITE}),
    max_tool_calls=32,
    writable_roots=frozenset({"."}),
)


@dataclass(frozen=True)
class _ArchiveEntry:
    path: str
    mode: int
    content: bytes
    directory: bool = False


@dataclass
class PreparedGitWorkspace:
    archive: bytes
    digest: str
    correlation: str
    policy: PiA2RuntimePolicy
    _checkout: Path
    _base: Path
    _result: Path
    _verify: Path
    _head: str

    def reconcile(self, archive: bytes) -> tuple[str, list[str]]:
        entries = _validated_entries(archive)
        _extract(entries, self._result)
        if workspace_archive(self._result) != archive:
            raise PiWorkspaceError("settled workspace archive is not canonical")
        _stage_tree(self._checkout, self._result)
        changed = _git_paths(self._checkout, "diff", "--cached", "--name-only", "-z", "HEAD", "--")
        if not changed or len(changed) > MAX_CHANGED_PATHS:
            if changed:
                raise PiWorkspaceError("settled workspace changes exceed the path limit")
            return "", []
        if changed != sorted(changed) or any(not _safe_workspace_path(path) for path in changed):
            raise PiWorkspaceError("settled workspace changed paths are unsafe")
        patch = _git(self._checkout, "diff", "--cached", "--binary", "HEAD", "--", capture=True)
        if not patch.strip() or len(patch.encode()) > MAX_PATCH_BYTES:
            raise PiWorkspaceError("canonical workspace patch is empty or exceeds its bound")
        result_tree = _git(self._checkout, "write-tree", capture=True).strip()

        _clone_exact(str(self._checkout), self._verify, self._head)
        patch_path = self._verify.parent / "canonical.patch"
        patch_path.write_text(patch, encoding="utf-8")
        _git(self._verify, "apply", "--binary", "--index", "--", str(patch_path))
        if _git(self._verify, "write-tree", capture=True).strip() != result_tree:
            raise PiWorkspaceError("canonical workspace patch could not reproduce the settled tree")
        return patch, changed


class GitPiWorkspaceProvider:
    """Build and receive one exact PR workspace entirely below an owned private root."""

    def __init__(self, root: Path) -> None:
        self.root = _private_root(root)

    @contextmanager
    def open(
        self,
        kind: str,
        repository_url: str,
        request: AgentRequest,
        operation_id: str,
    ) -> Iterator[PreparedGitWorkspace]:
        try:
            temporary = tempfile.mkdtemp(prefix="operation-", dir=self.root)
        except OSError:
            raise PiWorkspaceError("private Pi workspace preparation failed") from None
        operation_root = Path(temporary)
        preparation_failed = False
        try:
            try:
                checkout = operation_root / "source"
                base, result, verify = (operation_root / name for name in ("base", "result", "verify"))
                _clone_exact(repository_url, checkout, request.head)
                _export_tracked(checkout, base)
                if kind == "review" and isinstance(request, ReviewRequest):
                    _review_inputs(checkout, base, request)
                archive = workspace_archive(base)
                if len(archive) > MAX_WORKSPACE_BYTES:
                    raise PiWorkspaceError("input workspace archive exceeds its bound")
                digest = sha256(archive).hexdigest()
                correlation = (
                    "hamsterdan-pr-v1:"
                    + sha256(
                        f"{operation_id}\0{request.repository}\0{request.pull_request}\0{request.epoch}\0"
                        f"{request.head}\0{request.base}".encode()
                    ).hexdigest()
                )
                prepared = PreparedGitWorkspace(
                    archive,
                    digest,
                    correlation,
                    _CODE_POLICY if kind == "coding" else _READ_POLICY,
                    checkout,
                    base,
                    result,
                    verify,
                    request.head,
                )
            except PiWorkspaceError:
                preparation_failed = True
                raise
            except Exception:  # noqa: BLE001 - sanitize every private staging implementation failure
                preparation_failed = True
                raise PiWorkspaceError("private Pi workspace preparation failed") from None
            yield prepared
        finally:
            try:
                shutil.rmtree(operation_root)
            except OSError:
                raise PiWorkspaceCleanupError(preparation_failed=preparation_failed) from None


def _review_inputs(checkout: Path, destination: Path, request: ReviewRequest) -> None:
    paths = (request.diff_path, f"{request.diff_path}.lines")
    if any(not _safe_workspace_path(path) or (destination / path).exists() for path in paths):
        raise PiWorkspaceError("review input paths collide with repository content or are unsafe")
    revision = f"{request.base}...{request.head}"
    patch = _git(checkout, "diff", "--no-ext-diff", "--no-textconv", revision, "--", capture=True)
    numbered: list[str] = []
    for path in _git_paths(checkout, "diff", "--name-only", "--diff-filter=ACMRT", "-z", revision, "--"):
        if not _safe_workspace_path(path):
            raise PiWorkspaceError("review changed path is unsafe")
        source = destination / path
        if not source.is_file():
            continue
        numbered.append(f"{path}\n")
        try:
            lines = source.read_text(encoding="utf-8").splitlines()
        except UnicodeDecodeError:
            numbered.append("[binary file; no numbered text]\n")
            continue
        numbered.extend(f"{line}: {text}\n" for line, text in enumerate(lines, 1))
    for path, content in zip(paths, (patch, "".join(numbered)), strict=True):
        if len(content.encode()) > MAX_PATCH_BYTES:
            raise PiWorkspaceError("review input exceeds its bound")
        target = destination / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")


def _clone_exact(repository_url: str, destination: Path, head: str) -> None:
    _run_git(None, "clone", "--quiet", "--no-checkout", "--", repository_url, str(destination))
    _git(destination, "checkout", "--quiet", "--detach", head)
    if _git(destination, "rev-parse", "HEAD", capture=True).strip() != head:
        raise PiWorkspaceError("workspace checkout differs from the requested head")
    _git(destination, "fsck", "--strict", "--no-dangling")


def _export_tracked(checkout: Path, destination: Path) -> None:
    destination.mkdir(mode=0o700)
    raw = _git_bytes(checkout, "ls-files", "--stage", "-z")
    entries = [entry for entry in raw.split(b"\0") if entry]
    if len(entries) > MAX_WORKSPACE_ENTRIES:
        raise PiWorkspaceError("input workspace has too many entries")
    total = 0
    seen: set[str] = set()
    for entry in entries:
        metadata, separator, encoded_path = entry.partition(b"\t")
        fields = metadata.split()
        try:
            path = encoded_path.decode("utf-8")
        except UnicodeDecodeError:
            raise PiWorkspaceError("input workspace path is not UTF-8") from None
        if (
            not separator
            or len(fields) != 3
            or fields[0] not in {b"100644", b"100755"}
            or fields[2] != b"0"
            or path in seen
            or not _safe_workspace_path(path)
        ):
            raise PiWorkspaceError("input workspace contains an unsupported tracked entry")
        seen.add(path)
        source = checkout / path
        metadata = source.lstat()
        if not stat.S_ISREG(metadata.st_mode) or stat.S_IMODE(metadata.st_mode) not in {0o644, 0o755}:
            raise PiWorkspaceError("input workspace contains an unsupported file mode")
        remaining = MAX_WORKSPACE_BYTES - total
        if metadata.st_size > remaining:
            raise PiWorkspaceError("input workspace exceeds its expanded bound")
        with source.open("rb") as stream:
            content = stream.read(remaining + 1)
        if len(content) != metadata.st_size:
            raise PiWorkspaceError("input workspace file changed while being captured")
        total += len(content)
        _write(destination, path, content, stat.S_IMODE(metadata.st_mode))


def _validated_entries(data: bytes) -> list[_ArchiveEntry]:
    if type(data) is not bytes or not data or len(data) > MAX_WORKSPACE_BYTES:
        raise PiWorkspaceError("settled workspace archive is missing or oversized")
    entries: list[_ArchiveEntry] = []
    seen: set[str] = set()
    total = 0
    try:
        with tarfile.open(fileobj=io.BytesIO(data), mode="r:") as archive:
            members = archive.getmembers()
            if len(members) > MAX_WORKSPACE_ENTRIES:
                raise PiWorkspaceError("settled workspace has too many entries")
            for member in members:
                path = member.name
                if path in seen or not _safe_workspace_path(path):
                    raise PiWorkspaceError("settled workspace path is unsafe or duplicated")
                seen.add(path)
                mode = member.mode & 0o7777
                if member.isdir():
                    if mode != 0o755:
                        raise PiWorkspaceError("settled workspace directory mode is unsupported")
                    entries.append(_ArchiveEntry(path, mode, b"", True))
                    continue
                if not member.isfile() or mode not in {0o644, 0o755}:
                    raise PiWorkspaceError("settled workspace entry type or mode is unsupported")
                total += member.size
                if member.size < 0 or total > MAX_WORKSPACE_BYTES:
                    raise PiWorkspaceError("settled workspace exceeds its expanded bound")
                stream = archive.extractfile(member)
                if stream is None:
                    raise PiWorkspaceError("settled workspace file is unreadable")
                content = stream.read(MAX_WORKSPACE_BYTES + 1)
                if len(content) != member.size:
                    raise PiWorkspaceError("settled workspace file size is inconsistent")
                entries.append(_ArchiveEntry(path, mode, content))
    except PiWorkspaceError:
        raise
    except OSError, tarfile.TarError, EOFError:
        raise PiWorkspaceError("settled workspace archive is malformed") from None
    files = {entry.path for entry in entries if not entry.directory}
    directories = {entry.path for entry in entries if entry.directory}
    required = {str(PurePosixPath(path).parent) for path in files if str(PurePosixPath(path).parent) != "."}
    required |= {
        str(parent) for path in tuple(required) for parent in PurePosixPath(path).parents if str(parent) != "."
    }
    if directories != required:
        raise PiWorkspaceError("settled workspace contains missing or empty directories")
    return entries


def _extract(entries: list[_ArchiveEntry], destination: Path) -> None:
    destination.mkdir(mode=0o700)
    for entry in entries:
        if entry.directory:
            path = destination / entry.path
            path.mkdir(mode=0o755, parents=True, exist_ok=True)
            if path.is_symlink() or not path.is_dir():
                raise PiWorkspaceError("settled workspace staging path is unsafe")
            path.chmod(0o755)
        else:
            _write(destination, entry.path, entry.content, entry.mode)


def _write(root: Path, path: str, content: bytes, mode: int) -> None:
    target = root / path
    target.parent.mkdir(mode=0o755, parents=True, exist_ok=True)
    for parent in (target.parent, *target.parent.parents):
        if parent == root.parent:
            break
        metadata = parent.lstat()
        if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISDIR(metadata.st_mode):
            raise PiWorkspaceError("workspace staging parent is unsafe")
        if parent == root:
            break
    descriptor = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0), mode)
    try:
        with os.fdopen(descriptor, "wb", closefd=False) as stream:
            stream.write(content)
            stream.flush()
        os.fchmod(descriptor, mode)
    finally:
        os.close(descriptor)


def _stage_tree(checkout: Path, result: Path) -> None:
    env = _git_environment()
    env["GIT_WORK_TREE"] = str(result)
    _run_git(checkout, "add", "--all", "--force", "--", ".", env=env)


def _safe_workspace_path(value: str) -> bool:
    if not _safe_path(value) or PurePosixPath(value).as_posix() != value:
        return False
    return value.split("/", 1)[0].casefold() not in _DENIED_ROOTS


def _private_root(path: Path) -> Path:
    selected = Path(path)
    if selected.is_symlink():
        raise ValueError("Pi workspace receiver root must not be a symlink")
    selected.mkdir(mode=0o700, parents=True, exist_ok=True)
    selected.chmod(0o700)
    metadata = selected.lstat()
    if not stat.S_ISDIR(metadata.st_mode) or stat.S_IMODE(metadata.st_mode) != 0o700 or metadata.st_uid != os.geteuid():
        raise ValueError("Pi workspace receiver root must be owned and private")
    return selected.resolve()


def _git(root: Path, *arguments: str, capture: bool = False) -> str:
    completed = _run_git(root, *arguments)
    return completed.stdout if capture else ""


def _git_bytes(root: Path, *arguments: str) -> bytes:
    command = ("git", "-C", str(root), *arguments)
    try:
        return subprocess.run(command, check=True, capture_output=True, timeout=60, env=_git_environment()).stdout
    except OSError, subprocess.SubprocessError:
        raise PiWorkspaceError("private Git workspace operation failed") from None


def _git_paths(root: Path, *arguments: str) -> list[str]:
    raw = _git_bytes(root, *arguments)
    try:
        return [value.decode("utf-8") for value in raw.split(b"\0") if value]
    except UnicodeDecodeError:
        raise PiWorkspaceError("canonical changed path is not UTF-8") from None


def _run_git(
    root: Path | None,
    *arguments: str,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    command = ("git", *(("-C", str(root)) if root is not None else ()), *arguments)
    try:
        return subprocess.run(
            command,
            check=True,
            text=True,
            capture_output=True,
            timeout=60,
            env=env or _git_environment(),
        )
    except OSError, subprocess.SubprocessError:
        raise PiWorkspaceError("private Git workspace operation failed") from None


def _git_environment() -> dict[str, str]:
    return {
        "PATH": os.environ.get("PATH", ""),
        "LANG": "C.UTF-8",
        "LC_ALL": "C.UTF-8",
        "HOME": os.devnull,
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_TERMINAL_PROMPT": "0",
        "GIT_CONFIG_COUNT": "2",
        "GIT_CONFIG_KEY_0": "credential.helper",
        "GIT_CONFIG_VALUE_0": "",
        "GIT_CONFIG_KEY_1": "core.hooksPath",
        "GIT_CONFIG_VALUE_1": os.devnull,
    }
