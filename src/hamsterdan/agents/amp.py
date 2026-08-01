"""Disposable, credential-free Amp execution in a guarded Git worktree."""

# The subprocess calls deliberately inspect nonzero statuses themselves.
# ruff: noqa: PLW1510, C408

from __future__ import annotations

import hashlib
import json
import os
import signal
import stat
import subprocess
import tempfile
import threading
import time
from collections.abc import Callable
from dataclasses import asdict
from pathlib import Path
from typing import cast
from urllib.parse import urlsplit, urlunsplit

from .protocol import (
    _MAX_FILE,
    _SECRET_WORDS,
    CURRENT,
    AgentProtocolError,
    CodingRequest,
    CodingResult,
    ConversationRequest,
    ConversationResult,
    JSONDict,
    ReviewRequest,
    ReviewResult,
    _fail,
    _safe_path,
    _text,
    _validate_request,
    _validate_result,
)


class AmpExecuteRunner:
    def __init__(
        self,
        argv: tuple[str, ...] = ("amp", "--no-ide", "--no-color", "-m", "medium", "-x"),
        *,
        timeout: float = 600,
        max_output: int = 1_000_000,
        max_result: int = 1_000_000,
        poll_interval: float = 0.05,
        popen: Callable[..., subprocess.Popen] = subprocess.Popen,
    ):
        self.argv, self.timeout, self.max_output, self.max_result = argv, timeout, max_output, max_result
        self.poll_interval, self._popen = poll_interval, popen

    def review(self, repository_url: str, request: ReviewRequest, *, is_current: CURRENT | None = None) -> ReviewResult:
        return cast(ReviewResult, self._run("review", repository_url, request, is_current))

    def converse(
        self, repository_url: str, request: ConversationRequest, *, is_current: CURRENT | None = None
    ) -> ConversationResult:
        return cast(ConversationResult, self._run("conversation", repository_url, request, is_current))

    def code(self, repository_url: str, request: CodingRequest, *, is_current: CURRENT | None = None) -> CodingResult:
        return cast(CodingResult, self._run("coding", repository_url, request, is_current))

    change = repair = code

    def _run(
        self,
        kind: str,
        url: str,
        request: ReviewRequest | ConversationRequest | CodingRequest,
        current: CURRENT | None,
    ) -> ReviewResult | ConversationResult | CodingResult:
        _validate_request(request)
        clone_url = self._public_url(url)
        with tempfile.TemporaryDirectory(prefix="impetus-agent-") as tmp:
            root = Path(tmp) / "repo"
            self._git("clone", "--quiet", "--no-checkout", "--", clone_url, str(root))
            self._git("-C", str(root), "checkout", "--quiet", "--detach", request.head)
            expected_head = self._git("-C", str(root), "rev-parse", "HEAD", capture=True).strip()
            if expected_head != request.head:
                _fail("checked out HEAD does not exactly match request")
            self._git("-C", str(root), "remote", "set-url", "origin", "disabled://public-repository")
            if kind == "coding":
                if not isinstance(request, CodingRequest):
                    _fail("request kind differs from operation")
                self._git("-C", str(root), "switch", "--quiet", "-c", f"impetus-{request.kind}")
                if request.merge_base:
                    self._merge_without_commit(root, request.base)
            expected_origin = "disabled://public-repository"
            git_snapshot = self._tree_digest(root / ".git", ignored=frozenset({"index", "objects"}))
            control = root / ".impetus"
            control.mkdir(mode=0o700)
            diff_path: Path | None = None
            diff_digest: bytes | None = None
            if kind == "review":
                if not isinstance(request, ReviewRequest):
                    _fail("request kind differs from operation")
                self._git("-C", str(root), "cat-file", "-e", f"{request.base}^{{commit}}")
                diff_path = root / request.diff_path
                diff_path.parent.mkdir(parents=True, exist_ok=True)
                diff_path.write_text(
                    self._git(
                        "-C",
                        str(root),
                        "diff",
                        "--binary",
                        f"{request.base}...{expected_head}",
                        "--",
                        capture=True,
                    ),
                    encoding="utf-8",
                )
                diff_digest = hashlib.sha256(diff_path.read_bytes()).digest()
            (control / "request.json").write_text(json.dumps(asdict(request), separators=(",", ":")), encoding="utf-8")
            instructions = self._instructions(kind, request)
            (control / "instructions.txt").write_text(instructions, encoding="utf-8")
            request_digest = hashlib.sha256((control / "request.json").read_bytes()).digest()
            instructions_digest = hashlib.sha256((control / "instructions.txt").read_bytes()).digest()
            output = self._execute(root, instructions, current)
            control_failures = []
            if hashlib.sha256((control / "request.json").read_bytes()).digest() != request_digest:
                control_failures.append("request")
            if hashlib.sha256((control / "instructions.txt").read_bytes()).digest() != instructions_digest:
                control_failures.append("instructions")
            if diff_path is not None and (
                not diff_path.is_file() or hashlib.sha256(diff_path.read_bytes()).digest() != diff_digest
            ):
                control_failures.append("diff")
            names = {item.name for item in control.iterdir()}
            expected_names = {"request.json", "instructions.txt"}
            if (control / "result.json").exists():
                expected_names.add("result.json")
            if names != expected_names:
                control_failures.append("entries:" + ",".join(sorted(names)))
            if control_failures:
                _fail("agent modified host control files (" + ";".join(control_failures) + ")")
            if self._tree_digest(root / ".git", ignored=frozenset({"index", "objects"})) != git_snapshot:
                _fail("agent modified Git metadata or committed")
            if self._git("-C", str(root), "rev-parse", "HEAD", capture=True).strip() != expected_head:
                _fail("agent changed HEAD")
            if self._git("-C", str(root), "remote", "get-url", "origin", capture=True).strip() != expected_origin:
                _fail("agent changed origin")
            self._git("-C", str(root), "fsck", "--strict", "--no-dangling")
            self._git("-C", str(root), "cat-file", "-e", f"{expected_head}^{{commit}}")
            result_path = control / "result.json"
            if not result_path.exists() and len(output.encode()) > self.max_result:
                _fail("result exceeded limit")
            data = self._read_result(result_path) if result_path.exists() else self._parse_result(output)
            changed: list[str] = []
            if kind == "coding":
                diff, changed = self._capture(root)
                data["diff"], data["changed_files"] = diff, changed
            return _validate_result(kind, data, request, changed)

    @staticmethod
    def _public_url(url: str) -> str:
        _text(url, "repository URL", limit=4096)
        parsed = urlsplit(url)
        if parsed.scheme in {"http", "https"}:
            if parsed.username or parsed.password or parsed.query or parsed.fragment:
                _fail("repository URL contains credentials or noncanonical data")
            return urlunsplit((parsed.scheme, parsed.netloc, parsed.path, "", ""))
        if parsed.scheme or ":" in url.split("/")[0]:
            _fail("unsupported repository URL")
        return url  # local paths are retained solely for host tests/local proposals

    @staticmethod
    def _git(*args: str, capture: bool = False) -> str:
        env = AmpExecuteRunner._clean_env()
        done = subprocess.run(("git", *args), text=True, capture_output=True, timeout=60, env=env)
        if done.returncode:
            _fail("git workspace operation failed")
        return done.stdout if capture else ""

    @staticmethod
    def _clean_env() -> dict[str, str]:
        env = dict(os.environ)
        for name in list(env):
            upper = name.upper()
            if (
                upper.startswith(("GITHUB_", "GH_"))
                or upper == "IMPETUS_GITHUB_BOOTSTRAP_TOKEN"
                or "GITHUB" in upper
                or not upper.startswith("AMP_")
                and any(word in upper for word in _SECRET_WORDS)
            ):
                env.pop(name)
        env.update({"GIT_TERMINAL_PROMPT": "0", "GCM_INTERACTIVE": "never", "GIT_ASKPASS": ""})
        return env

    @staticmethod
    def _merge_without_commit(root: Path, base: str) -> None:
        done = subprocess.run(
            ("git", "-C", str(root), "merge", "--no-commit", "--no-ff", base),
            text=True,
            capture_output=True,
            timeout=60,
            env=AmpExecuteRunner._clean_env(),
        )
        if done.returncode not in {0, 1}:
            _fail("could not prepare the requested base merge")

    def _execute(self, root: Path, prompt: str, current: CURRENT | None) -> str:
        kwargs = dict(cwd=root, env=self._clean_env(), shell=False, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        if os.name == "posix":
            kwargs["start_new_session"] = True
        process = self._popen((*self.argv, prompt), **kwargs)
        output = bytearray()
        overflow = threading.Event()

        def drain() -> None:
            stream = process.stdout
            if stream is None:
                return
            while chunk := stream.read(65536):
                remaining = self.max_output + 1 - len(output)
                if remaining > 0:
                    output.extend(chunk[:remaining])
                if len(output) > self.max_output:
                    overflow.set()

        reader = threading.Thread(target=drain, daemon=True)
        reader.start()
        started = time.monotonic()
        try:
            while process.poll() is None:
                if current is not None and not current():
                    self._stop(process)
                    raise AgentProtocolError("agent attempt superseded", canceled=True)
                if time.monotonic() - started > self.timeout:
                    self._stop(process)
                    raise AgentProtocolError("agent execution timed out", timed_out=True)
                if overflow.is_set():
                    self._stop(process)
                    _fail("agent output exceeded limit")
                time.sleep(self.poll_interval)
            reader.join(timeout=2)
            if overflow.is_set():
                _fail("agent output exceeded limit")
            if process.returncode:
                _fail("agent execution failed")
            try:
                return bytes(output).decode("utf-8")
            except UnicodeDecodeError as error:
                raise AgentProtocolError("agent output is not UTF-8") from error
        finally:
            if process.poll() is None:
                self._stop(process)

    @staticmethod
    def _stop(process: subprocess.Popen) -> None:
        try:
            if os.name == "posix":
                os.killpg(process.pid, signal.SIGTERM)
            else:
                process.terminate()
            process.wait(timeout=1)
        except ProcessLookupError, subprocess.TimeoutExpired:
            try:
                if os.name == "posix":
                    os.killpg(process.pid, signal.SIGKILL)
                else:
                    process.kill()
            except ProcessLookupError:
                pass
            process.wait()

    def _read_result(self, path: Path) -> JSONDict:
        if path.parent.is_symlink() or not path.exists() or path.is_symlink() or not stat.S_ISREG(path.stat().st_mode):
            _fail("result missing or not a regular file")
        if path.stat().st_size > self.max_result:
            _fail("result exceeded limit")
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeError as error:
            raise AgentProtocolError("result is malformed JSON") from error
        return self._parse_result(text)

    @staticmethod
    def _parse_result(text: str) -> JSONDict:
        try:
            value = json.loads(text.strip())
        except json.JSONDecodeError as error:
            raise AgentProtocolError("result is malformed JSON") from error
        if not isinstance(value, dict):
            _fail("result must be a JSON object")
        return value

    @staticmethod
    def _tree_digest(path: Path, *, ignored: frozenset[str] = frozenset()) -> str:
        digest = hashlib.sha256()
        for item in sorted(path.rglob("*")):
            relative = item.relative_to(path).as_posix()
            if any(relative == name or relative.startswith(f"{name}/") for name in ignored):
                continue
            digest.update(relative.encode())
            if item.is_symlink():
                digest.update(b"L" + os.readlink(item).encode())
            elif item.is_file():
                digest.update(b"F" + item.read_bytes())
            elif item.is_dir():
                digest.update(b"D")
            else:
                digest.update(b"X")
        return digest.hexdigest()

    def _capture(self, root: Path) -> tuple[str, list[str]]:
        names = self._git(
            "-C", str(root), "status", "--porcelain=v1", "-z", "--untracked-files=all", capture=True
        ).split("\0")
        changed: set[str] = set()
        for record in filter(None, names):
            name = record[3:]
            if " -> " in name:
                name = name.split(" -> ", 1)[1]
            if name.startswith(".impetus/"):
                continue
            if not _safe_path(name):
                _fail("unsafe changed path")
            changed.add(name)
        diff = self._git("-C", str(root), "diff", "--binary", "HEAD", "--", capture=True)
        for name in sorted(changed):
            path = root / name
            if path.is_symlink():
                target = os.readlink(path)
                if not (path.parent / target).resolve().is_relative_to(root.resolve()):
                    _fail("symlink escapes checkout")
            if path.exists() and path.is_dir():
                _fail("submodule or directory worktree change is not accepted")
            if path.exists() and path.is_file() and path.stat().st_size > _MAX_FILE:
                _fail("changed file exceeded limit")
            if name not in self._git("-C", str(root), "ls-files", capture=True).splitlines():
                done = subprocess.run(
                    ("git", "-C", str(root), "diff", "--no-index", "--binary", "--", "/dev/null", name),
                    text=True,
                    capture_output=True,
                    env=self._clean_env(),
                    timeout=60,
                )
                if done.returncode not in {0, 1}:
                    _fail("could not capture untracked diff")
                diff += done.stdout
        if len(diff.encode()) > 4_000_000:
            _fail("captured diff exceeded limit")
        return diff, sorted(changed)

    @staticmethod
    def _instructions(kind: str, request: object) -> str:
        common = '"repository":string,"pull_request":integer,"epoch":integer,"head":SHA,"base":SHA'
        schemas = {
            "review": "{"
            + common
            + ',"status":"clear|blocking|unable","findings":[{"id":string,"path":repo_path,"line":positive_integer,"title":string,"body":string,"severity":"low|medium|high|critical","confidence":0..1,"evidence":string,"blocking":boolean,"suggestion":string}],"lineage":[{"finding_id":string,"state":"new|still_open|resolved|superseded|withdrawn","supersedes":string|null}]}',
            "conversation": "{"
            + common
            + ',"intents":[{"type":string,"arguments":object,"mutation":boolean,"explicit":boolean,"confidence":0..1,"confirmation":boolean}]}',
            "coding": "{"
            + common
            + ',"kind":"change|repair","ref":string,"status":"changed|unchanged|unable","reproduction_status":"unknown|confirmed|not_reproduced|not_attempted","diff":string,"changed_files":[repo_path],"validation_evidence":[object],"proposed_commit_message":string}',
        }
        semantics = {
            "review": "Act as one coordinating reviewer. Inspect the exact diff at request.diff_path and the checkout, apply every lens in request.review_lenses (using internal subagents only if useful), deduplicate and judge all candidate findings, and report only evidenced actionable defects. High/critical findings are blocking; low/medium are not. IDs are unique. Clear means no findings. Lineage must consistently relate current/prior findings and prior comments.",
            "conversation": "Answer natural readiness questions from the current durable dashboard, findings, gates, and exact PR generation supplied in the request; do not invent workflow state. Treat request.allowed_intents as internal response capabilities, never as user-visible commands or a tool API. Choose only declared types and exact argument names. For an ordinary readiness question emit exactly one reply for a direct explanation or one status when the host should render its deterministic summary. Put the concrete edit and its scope in a mutation's request argument and copy declared mutation metadata. For an explicit mutation request, emit only the mutation intent with confirmation=false so the host can stage it and publish exact confirmation guidance. Set confirmation=true only when confirmation_available is declared, the comment explicitly confirms the pending kind, arguments, and digest, and your emitted intent exactly reproduces that pending kind and arguments. Never treat an unconfirmed request as authorized execution.",
            "coding": "Make conservative local changes only; never commit, change HEAD/config/remotes/hooks, alter .impetus, add submodules, or push. You may update only the Git index to mark merge conflicts resolved; the host owns commits and publication. Run validation and report evidence. A changed repair requires confirmed reproduction. Host replaces diff and changed_files.",
        }
        return f"Read .impetus/request.json. {semantics[kind]} Produce one JSON object matching this exact canonical schema: {schemas[kind]} Write it to .impetus/result.json when tool access permits, and always emit the exact same object as your final response with no Markdown fence or prose. No other result is accepted. Never expose or seek credentials."
