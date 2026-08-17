"""Bounded human-operator tooling for Hamsterdan qualification.

Existing demo commands use the operator's configured ``gh``/Git identity. The
DS11 setup command instead consumes one private credential file into a bounded
child environment; neither route accepts credential values as CLI arguments.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shlex
import shutil
import stat
import subprocess
import tempfile
import time
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any, cast
from urllib.parse import quote

from hamsterdan.host.publication_qualification import (
    AtomicSetupPush,
    SetupCategory,
    SetupObservationResult,
    SetupPhase,
    SetupQualificationResult,
    qualify_setup,
)

REPOSITORY = "HBNetwork/demo-pr-readiness"
ORG_ID = 108842540
REPOSITORY_ID = 1316665126
DEFAULT_BRANCH = "main"
WORKFLOWS = frozenset({"ci", "rerun-broker"})
APP_SLUG = "hamster-dan"
APP_BOT_LOGIN = f"{APP_SLUG}[bot]"
SCENARIO_PATH = Path(".pr-lab/scenario.json")
CREATABLE_SCENARIOS = ("clean-green", "first-attempt-flake", "hero-review")
HERO_REVIEWER = "crisbastos"
BROKER_PATH = Path(".github/workflows/rerun-broker.yml")
BROKER_VALIDATOR_PATH = Path("tools/rerun_broker.py")
# Normalized source pair accepted at HBNetwork/demo-pr-readiness@a83e9223f7ffc6b0af919b0b8261fa2578261b41.
DELEGATED_BROKER_DIGEST = "373195c1935ef1a339526a577a6e3e6c30b9b618a135cfec8bd6fd2ad9c15ef9"
DELEGATED_VALIDATOR_DIGEST = "2869cce84573f4d3d21202a023f14b6138144667ae1a058cffab7442b7ab767a"
OLD_MARKER = "impetus-rerun"
NEW_MARKER = "hamsterdan-rerun"
LEGACY_BROKER_AUTHORIZATION = (
    'contains(fromJSON(\'["OWNER","MEMBER","COLLABORATOR"]\'), github.event.comment.author_association) &&'
)
APP_BROKER_AUTHORIZATION = (
    f"github.event.comment.user.type == 'Bot' &&\n      github.event.comment.user.login == '{APP_BOT_LOGIN}' &&"
)
MARKER_RE = re.compile(
    r"<!-- (?P<identity>hamsterdan-rerun|impetus-rerun) run=(?P<run>[1-9][0-9]*) "
    r"head=(?P<head>[0-9a-f]{40}) operation=(?P<operation>[A-Za-z0-9][A-Za-z0-9._:-]{0,127}) -->\Z"
)
DASHBOARD_RE = re.compile(r"<!-- hamsterdan:dashboard -->\Z")
IMMUTABLE_RE = re.compile(
    r"<!-- hamsterdan:(?P<kind>finding|reminder|readiness) "
    r"operation=(?P<operation>[A-Za-z0-9][A-Za-z0-9._:-]{0,127}) head=(?P<head>[0-9a-f]{40}) -->\Z"
)
BATCH_FINDING_RE = re.compile(
    r"^### `[A-Za-z0-9][A-Za-z0-9._-]{0,47}` — [^\n]+\n"
    r"(?:\*\*blocking\*\*|advisory) · severity: \*\*[^*\n]+\*\*$",
    re.MULTILINE,
)
PRIMARY_LOCATION_RE = re.compile(r"^Primary location: `(?P<path>[^`\n]+):(?P<line>[1-9][0-9]*)`$", re.MULTILINE)
FINDINGS_DIGEST_RE = re.compile(r"^<!-- hamsterdan:findings-digest [0-9a-f]{64} -->$", re.MULTILINE)
HERO_SUGGESTION_LOCATION = ("scenario-fixtures/hero_review/gate.py", 10)
HERO_CONCEPTUAL_LOCATION = ("scenario-fixtures/hero_review/gate.py", 16)
HERO_RELATED_LOCATION = ("scenario-fixtures/hero_review/cache.py", 11)
HERO_FINDING_LOCATIONS = frozenset({HERO_SUGGESTION_LOCATION, HERO_CONCEPTUAL_LOCATION, HERO_RELATED_LOCATION})
AUTHORITY_EXPECTATIONS = (
    "non-draft",
    "strict-stale",
    "conflict",
    "review-requested",
    "changes-requested",
    "required-approval",
    "unresolved-thread",
    "collaboration-clear",
)
AUTHORITY_REVIEW_FACTS = """
query($owner:String!,$repository:String!,$number:Int!) {
  repository(owner:$owner,name:$repository) {
    pullRequest(number:$number) {
      reviewDecision
      reviewThreads(first:100) {
        nodes { id isResolved }
        pageInfo { hasNextPage endCursor }
      }
    }
  }
}
"""
Runner = Callable[[Sequence[str], Path | None], subprocess.CompletedProcess[str]]
SetupRunner = Callable[[tuple[str, ...], Path, dict[str, str], bytes | None], subprocess.CompletedProcess[bytes]]
_PRIVATE_INPUT_LIMIT = 4096
_SETUP_REF = re.compile(r"refs/[A-Za-z0-9][A-Za-z0-9._/-]{0,255}\Z", re.ASCII)


class OperatorError(RuntimeError):
    """A bounded operator failure safe to display."""


def _consume_private_file(path: Path) -> bytearray:
    """Read and remove one owned 0600 regular file without following links."""
    descriptor: int | None = None
    try:
        descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
        metadata = os.fstat(descriptor)
        entry = path.lstat()
        if (
            not stat.S_ISREG(metadata.st_mode)
            or stat.S_IMODE(metadata.st_mode) != 0o600
            or metadata.st_uid != os.geteuid()
            or metadata.st_nlink != 1
            or (metadata.st_dev, metadata.st_ino) != (entry.st_dev, entry.st_ino)
            or metadata.st_size < 1
            or metadata.st_size > _PRIVATE_INPUT_LIMIT
        ):
            raise OperatorError("private input file is unavailable")
        value = bytearray(os.read(descriptor, _PRIVATE_INPUT_LIMIT + 1))
        if len(value) != metadata.st_size:
            raise OperatorError("private input file is unavailable")
        path.unlink()
        if path.exists():
            raise OperatorError("private input file is unavailable")
        return value
    except OSError:
        raise OperatorError("private input file is unavailable") from None
    finally:
        if descriptor is not None:
            os.close(descriptor)
        # The entry-level cleanup owner independently retries and verifies removal.


def _setup_subprocess(
    command: tuple[str, ...], cwd: Path, environment: dict[str, str], input_bytes: bytes | None
) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(
        command,
        cwd=cwd,
        env=environment,
        input=input_bytes,
        capture_output=True,
        timeout=30,
        check=False,
    )


def _parse_setup_refs(raw: bytes) -> dict[str, str]:
    """Parse an exact smart-HTTP ref projection without ignoring malformed data."""
    try:
        text = raw.decode("ascii")
    except UnicodeDecodeError:
        raise OperatorError("Git ref observation is malformed") from None
    if any(separator in text for separator in ("\r", "\v", "\f")):
        raise OperatorError("Git ref observation is malformed")
    lines = text.split("\n")
    if lines and lines[-1] == "":
        lines.pop()
    if any(not line for line in lines):
        raise OperatorError("Git ref observation is malformed")
    found: dict[str, str] = {}
    for line in lines:
        fields = line.split("\t")
        reference = fields[1] if len(fields) == 2 else ""
        components = reference.split("/")
        if (
            len(fields) != 2
            or re.fullmatch(r"[0-9a-f]{40}", fields[0]) is None
            or _SETUP_REF.fullmatch(reference) is None
            or ".." in reference
            or "@{" in reference
            or reference.endswith(("/", "."))
            or any(
                not component or component.startswith(".") or component.endswith(".lock") for component in components
            )
            or reference in found
        ):
            raise OperatorError("Git ref observation is malformed")
        found[reference] = fields[0]
    return found


def qualification_setup(
    credential_file: Path,
    target_file: Path,
    spent_path: Path,
    *,
    runner: SetupRunner = _setup_subprocess,
) -> dict[str, object]:
    """Run the one-mutation setup route with isolated, managed authority."""
    credential = bytearray()
    target_input = bytearray()
    root: Path | None = None
    inputs: tuple[Path, Path] = (Path(credential_file), Path(target_file))
    cleanup_confirmed = False
    cleanup_attempted = False
    environment: dict[str, str] | None = None

    def cleanup() -> bool:
        nonlocal cleanup_attempted, cleanup_confirmed
        cleanup_attempted = True
        for value in (credential, target_input):
            value[:] = b"\0" * len(value)
            value.clear()
        if environment is not None:
            environment.pop("GH_TOKEN", None)

        def remove_file(path: Path) -> bool:
            for _ in range(2):
                try:
                    path.unlink()
                except FileNotFoundError:
                    break
                except OSError:
                    continue
            try:
                path.lstat()
            except FileNotFoundError:
                return True
            except OSError:
                return False
            return False

        absent = True
        for path in inputs:
            absent = remove_file(path) and absent
        if root is not None:
            for _ in range(2):
                try:
                    shutil.rmtree(root)
                except FileNotFoundError:
                    break
                except OSError:
                    continue
            try:
                root.lstat()
            except FileNotFoundError:
                pass
            except OSError:
                absent = False
            else:
                absent = False
        cleanup_confirmed = absent
        return absent

    def preparation_failure() -> dict[str, object]:
        cleanup()
        cleanup_result = SetupObservationResult(
            cleanup_confirmed,
            None if cleanup_confirmed else SetupCategory.OBSERVATION_UNCONFIRMED,
        )
        result = SetupQualificationResult(
            None,
            None,
            None,
            None,
            None,
            None,
            None,
            None,
            cleanup_result,
            SetupPhase.PREPARATION,
            SetupCategory.INPUT_UNAVAILABLE,
        )
        return {"command": "qualification-setup", "ok": False, "evidence": result.sanitized()}

    try:
        raw_paths = (Path(credential_file), Path(target_file), Path(spent_path))
        if any(not path.is_absolute() for path in raw_paths):
            return preparation_failure()
        normalized = tuple(Path(os.path.abspath(path)) for path in raw_paths)
        if len(set(normalized)) != 3:
            return preparation_failure()
        inputs = (normalized[0], normalized[1])
        marker = normalized[2]
        git_executable = shutil.which("git")
        gh_executable = shutil.which("gh")
        if git_executable is None or gh_executable is None:
            return preparation_failure()
        git_executable = str(Path(git_executable).resolve(strict=True))
        gh_executable = str(Path(gh_executable).resolve(strict=True))
        parent = marker.parent.stat(follow_symlinks=False)
        if (
            marker.parent.resolve(strict=True) != marker.parent
            or not stat.S_ISDIR(parent.st_mode)
            or stat.S_IMODE(parent.st_mode) != 0o700
            or parent.st_uid != os.geteuid()
        ):
            return preparation_failure()
        credential = _consume_private_file(inputs[0])
        target_input = _consume_private_file(inputs[1])
        try:
            token = credential.decode("ascii")
        except UnicodeDecodeError:
            return preparation_failure()
        if not token or token.strip() != token or any(character.isspace() for character in token):
            return preparation_failure()
        try:
            envelope = json.loads(target_input)
        except UnicodeError, json.JSONDecodeError:
            return preparation_failure()
        if not isinstance(envelope, dict) or set(envelope) != {"repository", "account_id", "repository_id"}:
            return preparation_failure()
        target = envelope["repository"]
        account_id = envelope["account_id"]
        repository_id = envelope["repository_id"]
        if not isinstance(target, str) or type(account_id) is not int or type(repository_id) is not int:
            return preparation_failure()
        if re.fullmatch(r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,38})/[A-Za-z0-9._-]{1,100}", target) is None:
            return preparation_failure()
        owner, repository = target.split("/", 1)
        if ".." in repository or repository.startswith(".") or repository.endswith("."):
            return preparation_failure()

        root = Path(tempfile.mkdtemp(prefix="hamsterdan-qualification-"))
        os.chmod(root, 0o700)
        home, gh_config, fixture = root / "home", root / "gh", root / "fixture"
        for directory in (home, gh_config, fixture):
            directory.mkdir(mode=0o700)
        environment = {
            "PATH": os.defpath,
            "HOME": str(home),
            "GH_CONFIG_DIR": str(gh_config),
            "GH_PROMPT_DISABLED": "1",
            "GH_TOKEN": token,
            "GIT_TERMINAL_PROMPT": "0",
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_CONFIG_GLOBAL": os.devnull,
        }
        credential[:] = b"\0" * len(credential)
        credential.clear()

        def raw_run(
            command: tuple[str, ...],
            cwd: Path = fixture,
            input_bytes: bytes | None = None,
            env: dict[str, str] = environment,
        ) -> subprocess.CompletedProcess[bytes]:
            return runner(command, cwd, env, input_bytes)

        git_options = (
            "-c",
            "credential.helper=",
            "-c",
            f"credential.helper=!{shlex.quote(gh_executable)} auth git-credential",
            "-c",
            "core.hooksPath=/dev/null",
            "-c",
            "http.followRedirects=false",
            "-c",
            "protocol.file.allow=never",
        )

        def git(
            *arguments: str, cwd: Path = fixture, env: dict[str, str] = environment
        ) -> subprocess.CompletedProcess[bytes]:
            return raw_run((git_executable, *git_options, *arguments), cwd, env=env)

        fixture_commands = (
            ("init", "--quiet", "--initial-branch=main"),
            ("config", "user.name", "Hamsterdan Qualification"),
            ("config", "user.email", "qualification@invalid"),
        )
        if any(git(*command).returncode != 0 for command in fixture_commands):
            return preparation_failure()
        (fixture / "qualification.txt").write_text("hamsterdan qualification fixture v1\n")
        commit_environment = dict(environment)
        commit_environment.update(
            {"GIT_AUTHOR_DATE": "2000-01-01T00:00:00Z", "GIT_COMMITTER_DATE": "2000-01-01T00:00:00Z"}
        )

        def fixture_run(command: tuple[str, ...]) -> subprocess.CompletedProcess[bytes]:
            return git(*command, env=commit_environment)

        for command in (("add", "qualification.txt"), ("commit", "--quiet", "-m", "base")):
            if fixture_run(command).returncode != 0:
                return preparation_failure()
        base_result = fixture_run(("rev-parse", "HEAD"))
        base = base_result.stdout.decode().strip()
        (fixture / "requested-change.txt").write_text("requested change\n")
        for command in (("add", "requested-change.txt"), ("commit", "--quiet", "-m", "change")):
            if fixture_run(command).returncode != 0:
                return preparation_failure()
        head_result = fixture_run(("rev-parse", "HEAD"))
        head = head_result.stdout.decode().strip()
        if (
            base_result.returncode != 0
            or head_result.returncode != 0
            or not re.fullmatch(r"[0-9a-f]{40}", base)
            or not re.fullmatch(r"[0-9a-f]{40}", head)
        ):
            return preparation_failure()
        remote = f"https://github.com/{owner}/{repository}.git"

        def refs(*names: str) -> dict[str, str] | None:
            result = git("ls-remote", "--refs", remote, *names)
            if result.returncode != 0:
                return None
            return _parse_setup_refs(result.stdout)

        expected = {"refs/heads/main": base, "refs/heads/hamsterdan/ds11-live-v4": head}

        def empty() -> bool:
            return refs() == {}

        def exact() -> bool:
            return refs() == expected

        def pull_request_ready() -> bool:
            # GitHub exposes PR heads as read-only smart-HTTP refs. The target
            # is ready only when no existing PR advertises this exact head.
            advertised = refs("refs/pull/*/head")
            return advertised is not None and head not in advertised.values()

        def stale_cas_observed() -> bool:
            current = refs("refs/heads/hamsterdan/ds11-live-v4")
            return current == {"refs/heads/hamsterdan/ds11-live-v4": head} and current != {
                "refs/heads/hamsterdan/ds11-live-v4": base
            }

        def gh_json(endpoint: str) -> object:
            result = raw_run((gh_executable, "api", endpoint), root)
            if result.returncode != 0:
                raise RuntimeError
            return json.loads(result.stdout)

        def identity() -> bool:
            value = gh_json("/user")
            return isinstance(value, dict) and value.get("id") == account_id

        def target_ready() -> bool:
            value = gh_json(f"/repos/{owner}/{repository}")
            permissions = value.get("permissions") if isinstance(value, dict) else None
            return bool(
                isinstance(value, dict)
                and value.get("full_name") == target
                and value.get("id") == repository_id
                and value.get("private") is False
                and value.get("archived") is False
                and value.get("disabled") is False
                and value.get("size") == 0
                and value.get("default_branch") == "main"
                and isinstance(permissions, dict)
                and permissions.get("push") is True
            )

        result = qualify_setup(
            identity=identity,
            target=target_ready,
            pre_push=lambda: target_ready() and empty(),
            push=AtomicSetupPush(marker),
            remote=remote,
            base=base,
            head=head,
            runner=lambda command: raw_run((git_executable, *git_options, *command[1:])).returncode,
            readback=exact,
            # These are deliberately observations. No PR or ref mutation is
            # performed by qualification setup.
            pull_request=pull_request_ready,
            current_cas=exact,
            stale_cas=stale_cas_observed,
            cleanup=cleanup,
        )
        return {"command": "qualification-setup", "ok": result.accepted, "evidence": result.sanitized()}
    except Exception:  # noqa: BLE001 - fixed evidence must not retain private diagnostics
        return preparation_failure()
    finally:
        if not cleanup_attempted:
            cleanup()


def command_runner(command: Sequence[str], cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, cwd=cwd, text=True, capture_output=True, check=False)


def _run(runner: Runner, command: Sequence[str], cwd: Path | None = None) -> str:
    result = runner(tuple(command), cwd)
    if result.returncode:
        # Never reproduce provider/command output: it can contain credential-bearing URLs or headers.
        raise OperatorError(f"command failed: {command[0]} {command[1] if len(command) > 1 else ''}".strip())
    return result.stdout.strip()


def _json(runner: Runner, command: Sequence[str], cwd: Path | None = None) -> Any:
    try:
        return json.loads(_run(runner, command, cwd) or "null")
    except json.JSONDecodeError:
        raise OperatorError(f"malformed JSON from {command[0]}") from None


def _api(runner: Runner, path: str) -> Any:
    return _json(runner, ("gh", "api", path))


def broker_status(text: str, validator: str | None = None) -> str:
    old_prefix = "startsWith(github.event.comment.body, '<!-- impetus-rerun ')" in text
    old_regex = r"<!-- impetus-rerun run=" in text
    new_prefix = "startsWith(github.event.comment.body, '<!-- hamsterdan-rerun ')" in text
    new_regex = r"<!-- hamsterdan-rerun run=" in text
    legacy_auth = text.count(LEGACY_BROKER_AUTHORIZATION) == 1
    app_auth = text.count(APP_BROKER_AUTHORIZATION) == 1
    if old_prefix and old_regex and legacy_auth and not new_prefix and not new_regex and not app_auth:
        return "legacy"
    if new_prefix and new_regex and app_auth and not old_prefix and not old_regex and not legacy_auth:
        return "hamsterdan"
    if _delegated_broker(text, validator):
        return "hamsterdan"
    return "malformed"


def _delegated_broker(workflow: str, validator: str | None) -> bool:
    if validator is None:
        return False
    return (
        _broker_digest(workflow) == DELEGATED_BROKER_DIGEST and _broker_digest(validator) == DELEGATED_VALIDATOR_DIGEST
    )


def _broker_digest(source: str) -> str:
    return hashlib.sha256(source.replace("\r\n", "\n").strip().encode()).hexdigest()


def _check(name: str, passed: bool, observed: object) -> dict[str, object]:
    return {"name": name, "pass": passed, "observed": observed}


def preflight(runner: Runner = command_runner, *, health_url: str | None = None) -> dict[str, object]:
    checks: list[dict[str, object]] = []
    auth = runner(("gh", "auth", "status"), None)
    checks.append(_check("gh_auth", auth.returncode == 0, "authenticated" if auth.returncode == 0 else "unavailable"))
    try:
        org = _api(runner, "/orgs/HBNetwork")
        repo = _api(runner, f"/repos/{REPOSITORY}")
        workflows = _api(runner, f"/repos/{REPOSITORY}/actions/workflows?per_page=100")
        broker = _run(
            runner,
            (
                "gh",
                "api",
                f"/repos/{REPOSITORY}/contents/{BROKER_PATH}?ref={DEFAULT_BRANCH}",
                "-H",
                "Accept: application/vnd.github.raw+json",
            ),
        )
        validator = None
        if "tools/rerun_broker.py" in broker:
            validator = _run(
                runner,
                (
                    "gh",
                    "api",
                    f"/repos/{REPOSITORY}/contents/{BROKER_VALIDATOR_PATH}?ref={DEFAULT_BRANCH}",
                    "-H",
                    "Accept: application/vnd.github.raw+json",
                ),
            )
        broker_state = broker_status(broker, validator)
        names = {item.get("name") for item in workflows.get("workflows", []) if isinstance(item, dict)}
        checks.extend(
            (
                _check("organization_identity", org.get("id") == ORG_ID, org.get("id")),
                _check("repository_identity", repo.get("id") == REPOSITORY_ID, repo.get("id")),
                _check("repository_public", repo.get("private") is False, not bool(repo.get("private", True))),
                _check("default_branch", repo.get("default_branch") == DEFAULT_BRANCH, repo.get("default_branch")),
                _check(
                    "required_workflows", WORKFLOWS <= names, sorted(name for name in names if isinstance(name, str))
                ),
                _check("default_broker", broker_state in {"legacy", "hamsterdan"}, broker_state),
            )
        )
    except OperatorError as error:
        checks.append(_check("provider_inventory", False, str(error)))
    if health_url:
        url = health_url.rstrip("/") + "/healthz"
        result = runner(("curl", "--fail", "--silent", "--show-error", "--max-time", "10", url), None)
        healthy = False
        if result.returncode == 0:
            try:
                value = json.loads(result.stdout)
                healthy = isinstance(value, dict)
            except json.JSONDecodeError:
                pass
        checks.append(_check("app_host_health", healthy, "healthy" if healthy else "unavailable"))
    return {"command": "preflight", "ok": all(bool(item["pass"]) for item in checks), "checks": checks}


def scenario_value(scenario: str) -> dict[str, object]:
    behavior: dict[str, str] = {"kind": "pass"}
    if scenario == "first-attempt-flake":
        behavior = {"kind": "first_attempt_flake", "fingerprint": "scenario:first-attempt-flake:v1"}
    elif scenario not in {"clean-green", "hero-review"}:
        raise OperatorError("unsupported scenario")
    return {
        "schema_version": 1,
        "scenario": scenario,
        "behavior": behavior,
        "review_lenses": ["correctness", "test-quality", "risk"],
    }


def _clone(runner: Runner, root: Path) -> Path:
    checkout = root / "demo-pr-readiness"
    _run(runner, ("git", "clone", "--origin", "origin", f"https://github.com/{REPOSITORY}.git", str(checkout)))
    _run(runner, ("git", "fetch", "origin", DEFAULT_BRANCH), checkout)
    return checkout


def _assert_only(runner: Runner, checkout: Path, admitted: set[str]) -> None:
    changed = set(_run(runner, ("git", "diff", "--name-only", "origin/main...HEAD"), checkout).splitlines())
    if changed != admitted:
        raise OperatorError(f"refusing unexpected changed paths: {sorted(changed)}")


def create(scenario: str, runner: Runner = command_runner) -> dict[str, object]:
    stamp = time.strftime("%Y%m%d-%H%M%S", time.gmtime())
    branch = f"hamsterdan/{scenario}-{stamp}"
    title = f"Hamsterdan demo: {scenario}"
    with tempfile.TemporaryDirectory(prefix="hamsterdan-operator-") as temporary:
        checkout = _clone(runner, Path(temporary))
        _run(runner, ("git", "switch", "--create", branch, "origin/main"), checkout)
        prepared = _json(runner, ("python", "tools/scenario_control.py", "prepare", scenario), checkout)
        admitted = prepared.get("admitted_changed_paths") if isinstance(prepared, dict) else None
        if (
            not isinstance(admitted, list)
            or not admitted
            or not all(isinstance(path, str) and path for path in admitted)
            or str(SCENARIO_PATH) not in admitted
        ):
            raise OperatorError("scenario preparation returned malformed admitted paths")
        admitted_paths = set(admitted)
        _run(runner, ("python", "tools/scenario_control.py", "--attempt", "2"), checkout)
        changed = set(_run(runner, ("git", "diff", "--name-only"), checkout).splitlines())
        changed.update(_run(runner, ("git", "ls-files", "--others", "--exclude-standard"), checkout).splitlines())
        if not changed or not changed <= admitted_paths:
            raise OperatorError(f"refusing unexpected changed paths: {sorted(changed)}")
        _run(runner, ("git", "add", "--", *sorted(changed)), checkout)
        _run(runner, ("git", "commit", "-m", title), checkout)
        _assert_only(runner, checkout, changed)
        _run(runner, ("git", "push", "--set-upstream", "origin", branch), checkout)
        _run(
            runner,
            (
                "gh",
                "pr",
                "create",
                "--repo",
                REPOSITORY,
                "--base",
                DEFAULT_BRANCH,
                "--head",
                branch,
                "--title",
                title,
                "--body",
                "Controlled Hamsterdan qualification scenario. Do not merge automatically.",
            ),
            checkout,
        )
        pr = _json(
            runner, ("gh", "pr", "view", branch, "--repo", REPOSITORY, "--json", "number,url,headRefName"), checkout
        )
        if scenario == "hero-review":
            _run(
                runner,
                (
                    "gh",
                    "api",
                    "--method",
                    "POST",
                    f"/repos/{REPOSITORY}/pulls/{pr['number']}/requested_reviewers",
                    "-f",
                    f"reviewers[]={HERO_REVIEWER}",
                ),
                checkout,
            )
        head = _run(runner, ("git", "rev-parse", "HEAD"), checkout)
    return {
        "command": "create",
        "ok": True,
        "number": pr["number"],
        "url": pr["url"],
        "head": head,
        "branch": branch,
        "requested_reviewer": HERO_REVIEWER if scenario == "hero-review" else None,
    }


def prepare_broker(runner: Runner = command_runner) -> dict[str, object]:
    prepared = _json(
        runner,
        (
            "gh",
            "pr",
            "list",
            "--repo",
            REPOSITORY,
            "--state",
            "open",
            "--search",
            "in:title Hamsterdan broker identity cutover",
            "--json",
            "number,url,headRefName",
            "--limit",
            "10",
        ),
    )
    matching = [item for item in prepared if str(item.get("headRefName", "")).startswith("hamsterdan/broker-cutover-")]
    if matching:
        item = matching[0]
        return {
            "command": "prepare-broker",
            "ok": True,
            "status": "prepared",
            "changed": False,
            "number": item["number"],
            "url": item["url"],
            "branch": item["headRefName"],
        }
    stamp = time.strftime("%Y%m%d-%H%M%S", time.gmtime())
    branch = f"hamsterdan/broker-cutover-{stamp}"
    with tempfile.TemporaryDirectory(prefix="hamsterdan-broker-") as temporary:
        checkout = _clone(runner, Path(temporary))
        source = (checkout / BROKER_PATH).read_text(encoding="utf-8")
        validator_path = checkout / BROKER_VALIDATOR_PATH
        validator = validator_path.read_text(encoding="utf-8") if validator_path.is_file() else None
        state = broker_status(source, validator)
        if state == "hamsterdan":
            return {"command": "prepare-broker", "ok": True, "status": "current", "changed": False}
        if state != "legacy" or source.count(OLD_MARKER) != 2 or source.count(LEGACY_BROKER_AUTHORIZATION) != 1:
            raise OperatorError("default broker is malformed; refusing automated preparation")
        _run(runner, ("git", "switch", "--create", branch, "origin/main"), checkout)
        target = source.replace(OLD_MARKER, NEW_MARKER).replace(LEGACY_BROKER_AUTHORIZATION, APP_BROKER_AUTHORIZATION)
        if (
            broker_status(target) != "hamsterdan"
            or target.count(NEW_MARKER) != 2
            or target.count(APP_BROKER_AUTHORIZATION) != 1
        ):
            raise OperatorError("broker transformation did not produce strict Hamsterdan grammar")
        (checkout / BROKER_PATH).write_text(target, encoding="utf-8")
        _run(runner, ("git", "add", "--", str(BROKER_PATH)), checkout)
        _run(runner, ("git", "commit", "-m", "Hamsterdan broker identity cutover"), checkout)
        _assert_only(runner, checkout, {str(BROKER_PATH)})
        _run(runner, ("git", "push", "--set-upstream", "origin", branch), checkout)
        _run(
            runner,
            (
                "gh",
                "pr",
                "create",
                "--repo",
                REPOSITORY,
                "--base",
                DEFAULT_BRANCH,
                "--head",
                branch,
                "--title",
                "Hamsterdan broker identity cutover",
                "--body",
                "Merge only after the Hamsterdan App host is ready; never run legacy and App writers together.",
            ),
            checkout,
        )
        pr = _json(
            runner, ("gh", "pr", "view", branch, "--repo", REPOSITORY, "--json", "number,url,headRefName"), checkout
        )
    return {
        "command": "prepare-broker",
        "ok": True,
        "status": "prepared",
        "changed": True,
        "number": pr["number"],
        "url": pr["url"],
        "branch": branch,
    }


def _safe_comment(
    comment: dict[str, Any], bot_login: str, *, inline: bool = False
) -> tuple[dict[str, object] | None, list[dict[str, object]]]:
    body, owner = str(comment.get("body", "")), str(comment.get("user", {}).get("login", ""))
    url, identifier = comment.get("html_url"), comment.get("id")
    markers: list[dict[str, object]] = []
    kind: str | None = None
    if DASHBOARD_RE.search(body):
        kind = "dashboard"
    immutable = IMMUTABLE_RE.search(body)
    if immutable:
        kind = immutable.group("kind")
        markers.append(
            {
                "type": kind,
                "operation": immutable.group("operation"),
                "head": immutable.group("head"),
                "comment_id": identifier,
                "url": url,
                "owner": owner,
            }
        )
    for marker in MARKER_RE.finditer(body):
        marker_kind = marker.group("identity")
        markers.append(
            {
                "type": marker_kind,
                "run_id": int(marker.group("run")),
                "head": marker.group("head"),
                "operation": marker.group("operation"),
                "comment_id": identifier,
                "url": url,
                "owner": owner,
            }
        )
        if marker_kind == NEW_MARKER:
            kind = NEW_MARKER
    if kind:
        safe: dict[str, object] = {
            "id": identifier,
            "url": url,
            "owner": owner,
            "type": kind,
            "inline": inline,
            "owned_by_app": owner.casefold() == bot_login.casefold(),
        }
        if kind == "finding":
            batch = (
                not inline
                and body.startswith("## Hamsterdan review findings\n\n")
                and FINDINGS_DIGEST_RE.search(body) is not None
            )
            matches = list(BATCH_FINDING_RE.finditer(body)) if batch else []
            sections = [
                body[match.start() : matches[index + 1].start() if index + 1 < len(matches) else len(body)]
                for index, match in enumerate(matches)
            ] or [body]
            if inline:
                line = comment.get("line") or comment.get("original_line")
                locations = [(str(comment.get("path", "")), line) if type(line) is int and line > 0 else None]
            else:
                locations = [
                    (primary.group("path"), int(primary.group("line")))
                    if (primary := PRIMARY_LOCATION_RE.search(section)) is not None
                    else None
                    for section in sections
                ]
            safe.update(
                {
                    "finding_count": len(sections),
                    "hero_finding_count": sum(location in HERO_FINDING_LOCATIONS for location in locations),
                    "suggestion_count": sum(
                        location == HERO_SUGGESTION_LOCATION and "```suggestion\n" in section
                        for location, section in zip(locations, sections, strict=True)
                    ),
                    "conceptual_count": sum(location == HERO_CONCEPTUAL_LOCATION for location in locations),
                    "related_location_count": sum(
                        location == HERO_RELATED_LOCATION and "\nRelated locations:\n- " in section
                        for location, section in zip(locations, sections, strict=True)
                    ),
                }
            )
        return safe, markers
    return None, markers


def inspect(
    pr_number: int,
    runner: Runner = command_runner,
    *,
    bot_login: str = APP_BOT_LOGIN,
    expect_hero_review: bool = False,
    expect_readiness: bool = True,
) -> dict[str, object]:
    if pr_number < 1:
        raise OperatorError("PR number must be positive")
    pull = _api(runner, f"/repos/{REPOSITORY}/pulls/{pr_number}")
    comments = _api(runner, f"/repos/{REPOSITORY}/issues/{pr_number}/comments?per_page=100")
    review_comments = _api(runner, f"/repos/{REPOSITORY}/pulls/{pr_number}/comments?per_page=100")
    head = str(pull.get("head", {}).get("sha", ""))
    commit = _api(runner, f"/repos/{REPOSITORY}/commits/{head}")
    runs_value = _api(runner, f"/repos/{REPOSITORY}/actions/runs?event=pull_request&head_sha={head}&per_page=100")
    safe_comments: list[dict[str, object]] = []
    markers: list[dict[str, object]] = []
    for comment in comments[:100] if isinstance(comments, list) else []:
        safe, found = _safe_comment(comment, bot_login)
        if safe:
            safe_comments.append(safe)
        markers.extend(found)
    for comment in review_comments[:100] if isinstance(review_comments, list) else []:
        safe, found = _safe_comment(comment, bot_login, inline=True)
        if safe:
            safe_comments.append(safe)
        markers.extend(found)
    runs: list[dict[str, object]] = []
    for item in runs_value.get("workflow_runs", [])[:20]:
        attempt = int(item.get("run_attempt", 1))
        jobs_value = _api(runner, f"/repos/{REPOSITORY}/actions/runs/{item['id']}/attempts/{attempt}/jobs?per_page=100")
        runs.append(
            {
                "id": item.get("id"),
                "name": item.get("name"),
                "attempt": attempt,
                "head": item.get("head_sha"),
                "status": item.get("status"),
                "conclusion": item.get("conclusion"),
                "url": item.get("html_url"),
                "jobs": [
                    {
                        "id": job.get("id"),
                        "name": job.get("name"),
                        "status": job.get("status"),
                        "conclusion": job.get("conclusion"),
                    }
                    for job in jobs_value.get("jobs", [])[:100]
                ],
            }
        )
    new_markers = [item for item in markers if item["type"] == NEW_MARKER]
    old_markers = [item for item in markers if item["type"] == OLD_MARKER]
    owned = bool(safe_comments) and all(item["owned_by_app"] for item in safe_comments)
    marker_owned = all(str(item.get("owner", "")).casefold() == bot_login.casefold() for item in new_markers)
    kinds = {str(item["type"]) for item in safe_comments if item["owned_by_app"]}
    checks = [
        _check(
            "pull_identity",
            pull.get("base", {}).get("repo", {}).get("id") == REPOSITORY_ID,
            pull.get("base", {}).get("repo", {}).get("id"),
        ),
        _check("hamsterdan_comment_ownership", owned and marker_owned, bot_login),
        _check("dashboard_present", "dashboard" in kinds, "dashboard" in kinds),
        _check(
            "readiness_advisory_present" if expect_readiness else "readiness_advisory_absent",
            ("readiness" in kinds) is expect_readiness,
            "readiness" in kinds,
        ),
        _check("legacy_markers_absent", not old_markers, len(old_markers)),
        _check("workflow_heads_match", all(run["head"] == head for run in runs), head),
    ]
    if expect_hero_review:
        findings = [item for item in safe_comments if item["type"] == "finding" and item["owned_by_app"]]
        finding_count = sum(cast(int, item["hero_finding_count"]) for item in findings)
        suggestion_count = sum(cast(int, item["suggestion_count"]) for item in findings)
        conceptual_count = sum(cast(int, item["conceptual_count"]) for item in findings)
        related_count = sum(cast(int, item["related_location_count"]) for item in findings)
        checks.extend(
            (
                _check("hero_findings", finding_count >= 3, finding_count),
                _check("hero_suggestion", suggestion_count > 0, suggestion_count),
                _check("hero_conceptual", conceptual_count > 0, conceptual_count),
                _check("hero_related_locations", related_count > 0, related_count),
            )
        )
    authored = commit.get("commit", {})
    result = {
        "command": "inspect",
        "repository": REPOSITORY,
        "number": pr_number,
        "pull": {
            "url": pull.get("html_url"),
            "state": pull.get("state"),
            "draft": pull.get("draft"),
            "head": head,
            "head_ref": pull.get("head", {}).get("ref"),
            "base_ref": pull.get("base", {}).get("ref"),
        },
        "comments": safe_comments[:100],
        "markers": markers[:100],
        "runs": runs,
        "attribution": {
            "commit_author": authored.get("author"),
            "commit_committer": authored.get("committer"),
            "authenticated_author": commit.get("author", {}).get("login")
            if isinstance(commit.get("author"), dict)
            else None,
            "authenticated_committer": commit.get("committer", {}).get("login")
            if isinstance(commit.get("committer"), dict)
            else None,
        },
        "checks": checks,
    }
    result["ok"] = all(bool(item["pass"]) for item in checks)
    return result


def _authority_policy(rules: object) -> tuple[bool, int, bool]:
    if not isinstance(rules, list) or not all(isinstance(rule, dict) for rule in rules):
        raise OperatorError("GitHub authority policy evidence is malformed")
    if len(rules) >= 100:
        raise OperatorError("GitHub authority policy exceeds one bounded page")
    strict, approvals, resolution = False, 0, False
    for rule in cast(list[dict[str, Any]], rules):
        if rule.get("type") == "required_status_checks":
            parameters = rule.get("parameters")
            if (
                not isinstance(parameters, dict)
                or type(parameters.get("strict_required_status_checks_policy")) is not bool
                or not isinstance(parameters.get("required_status_checks"), list)
            ):
                raise OperatorError("GitHub authority policy evidence is malformed")
            strict |= parameters["strict_required_status_checks_policy"]
            for check in parameters["required_status_checks"]:
                if not isinstance(check, dict) or not isinstance(check.get("context"), str) or not check["context"]:
                    raise OperatorError("GitHub authority policy evidence is malformed")
        elif rule.get("type") == "pull_request":
            parameters = rule.get("parameters")
            count = parameters.get("required_approving_review_count") if isinstance(parameters, dict) else None
            conversations = (
                parameters.get("required_review_thread_resolution") if isinstance(parameters, dict) else None
            )
            if type(count) is not int or count < 0 or type(conversations) is not bool:
                raise OperatorError("GitHub authority policy evidence is malformed")
            approvals = max(approvals, count)
            resolution |= conversations
    return strict, approvals, resolution


def _latest_reviews(value: object) -> dict[str, str]:
    if not isinstance(value, list) or not all(isinstance(review, dict) for review in value):
        raise OperatorError("GitHub review authority evidence is malformed")
    if len(value) >= 100:
        raise OperatorError("GitHub review authority exceeds one bounded page")
    latest: dict[str, tuple[str, str, str, int]] = {}
    for review in cast(list[dict[str, Any]], value):
        user = review.get("user")
        login = user.get("login") if isinstance(user, dict) else None
        state, submitted, identifier = review.get("state"), review.get("submitted_at"), review.get("id")
        if (
            not isinstance(login, str)
            or not login
            or not isinstance(state, str)
            or not isinstance(submitted, str)
            or type(identifier) is not int
        ):
            raise OperatorError("GitHub review authority evidence is malformed")
        normalized = state.upper()
        if normalized not in {"APPROVED", "CHANGES_REQUESTED", "DISMISSED"}:
            continue
        key = login.casefold()
        if key not in latest or (submitted, identifier) > latest[key][2:]:
            latest[key] = (login, normalized, submitted, identifier)
    return {
        login: state
        for login, state, _, _ in sorted(latest.values(), key=lambda item: item[0].casefold())
        if state != "DISMISSED"
    }


def _review_facts(pr_number: int, runner: Runner) -> tuple[int, str | None]:
    owner, repository = REPOSITORY.split("/", 1)
    value = _json(
        runner,
        (
            "gh",
            "api",
            "graphql",
            "-f",
            f"query={AUTHORITY_REVIEW_FACTS}",
            "-F",
            f"owner={owner}",
            "-F",
            f"repository={repository}",
            "-F",
            f"number={pr_number}",
        ),
    )
    try:
        pull = value["data"]["repository"]["pullRequest"]
        decision = pull["reviewDecision"]
        threads = pull["reviewThreads"]
        nodes, page = threads["nodes"], threads["pageInfo"]
    except KeyError, TypeError:
        raise OperatorError("GitHub review-thread authority evidence is malformed") from None
    if (
        not isinstance(nodes, list)
        or not all(
            isinstance(node, dict) and isinstance(node.get("id"), str) and type(node.get("isResolved")) is bool
            for node in nodes
        )
        or not isinstance(page, dict)
        or type(page.get("hasNextPage")) is not bool
        or decision not in {None, "APPROVED", "CHANGES_REQUESTED", "REVIEW_REQUIRED"}
    ):
        raise OperatorError("GitHub review-thread authority evidence is malformed")
    if page["hasNextPage"]:
        raise OperatorError("GitHub review-thread authority exceeds one bounded page")
    return sum(not node["isResolved"] for node in nodes), decision


def inspect_authority(pr_number: int, expected: str, runner: Runner = command_runner) -> dict[str, object]:
    """Inspect real GitHub authority without copying provider objects into the Net."""
    if pr_number < 1:
        raise OperatorError("PR number must be positive")
    if expected not in AUTHORITY_EXPECTATIONS:
        raise OperatorError("unsupported authority expectation")
    pull = _api(runner, f"/repos/{REPOSITORY}/pulls/{pr_number}")
    if not isinstance(pull, dict):
        raise OperatorError("GitHub pull-request authority evidence is malformed")
    try:
        head, base_value = pull["head"], pull["base"]
        head_sha, base_ref = head["sha"], base_value["ref"]
        author = pull["user"]["login"]
        if (
            not isinstance(head_sha, str)
            or not re.fullmatch(r"[0-9a-fA-F]{40}", head_sha)
            or not isinstance(base_ref, str)
            or not base_ref
            or not isinstance(author, str)
            or not author
        ):
            raise TypeError
    except KeyError, TypeError:
        raise OperatorError("GitHub pull-request authority evidence is malformed") from None
    encoded_base = quote(base_ref, safe="")
    reference = _api(runner, f"/repos/{REPOSITORY}/git/ref/heads/{encoded_base}")
    try:
        base_sha = reference["object"]["sha"]
    except KeyError, TypeError:
        raise OperatorError("GitHub base authority evidence is malformed") from None
    if not isinstance(base_sha, str) or not re.fullmatch(r"[0-9a-fA-F]{40}", base_sha):
        raise OperatorError("GitHub base authority evidence is malformed")
    comparison = _api(runner, f"/repos/{REPOSITORY}/compare/{base_sha}...{head_sha}")
    behind = comparison.get("behind_by") if isinstance(comparison, dict) else None
    if type(behind) is not int or behind < 0:
        raise OperatorError("GitHub comparison authority evidence is malformed")
    strict, required, resolution = _authority_policy(
        _api(runner, f"/repos/{REPOSITORY}/rules/branches/{encoded_base}?per_page=100")
    )
    requested_value = _api(runner, f"/repos/{REPOSITORY}/pulls/{pr_number}/requested_reviewers")
    requested_users = requested_value.get("users") if isinstance(requested_value, dict) else None
    requested_teams = requested_value.get("teams") if isinstance(requested_value, dict) else None
    if (
        not isinstance(requested_users, list)
        or not all(isinstance(user, dict) for user in requested_users)
        or not isinstance(requested_teams, list)
        or not all(isinstance(team, dict) for team in requested_teams)
    ):
        raise OperatorError("GitHub requested-reviewer authority evidence is malformed")
    requested = sorted(
        str(user["login"]) for user in requested_users if isinstance(user.get("login"), str) and user["login"]
    )
    teams = sorted(str(team["slug"]) for team in requested_teams if isinstance(team.get("slug"), str) and team["slug"])
    reviews = _latest_reviews(_api(runner, f"/repos/{REPOSITORY}/pulls/{pr_number}/reviews?per_page=100"))
    approvals = sorted(
        login for login, state in reviews.items() if state == "APPROVED" and login.casefold() != author.casefold()
    )
    changes = sorted(login for login, state in reviews.items() if state == "CHANGES_REQUESTED")
    unresolved, review_decision = _review_facts(pr_number, runner)
    mergeable, mergeable_state, draft = pull.get("mergeable"), pull.get("mergeable_state"), pull.get("draft")
    if mergeable not in {True, False, None} or not isinstance(mergeable_state, str) or type(draft) is not bool:
        raise OperatorError("GitHub mergeability authority evidence is malformed")
    if mergeable is None:
        raise OperatorError("GitHub mergeability authority is indeterminate; retry inspection")
    final_pull = _api(runner, f"/repos/{REPOSITORY}/pulls/{pr_number}")
    final_reference = _api(runner, f"/repos/{REPOSITORY}/git/ref/heads/{encoded_base}")
    try:
        final_basis = (
            final_pull["head"]["sha"],
            final_pull["base"]["ref"],
            final_reference["object"]["sha"],
        )
    except KeyError, TypeError:
        raise OperatorError("GitHub final authority basis is malformed") from None
    if final_basis != (head_sha, base_ref, base_sha):
        raise OperatorError("GitHub authority changed during inspection")
    authority = {
        "draft": draft,
        "head": head_sha.lower(),
        "base": base_sha.lower(),
        "base_ref": base_ref,
        "behind_by": behind,
        "mergeable": mergeable,
        "mergeable_state": mergeable_state,
        "strict_base": strict,
        "required_approvals": required,
        "conversation_resolution": resolution,
        "requested_reviewers": requested,
        "requested_teams": teams,
        "latest_reviews": [{"reviewer": login, "state": state} for login, state in sorted(reviews.items())],
        "distinct_approvals": approvals,
        "changes_requested": changes,
        "unresolved_threads": unresolved,
        "review_decision": review_decision,
    }
    expectations = {
        "non-draft": not draft,
        "strict-stale": not draft and strict and behind > 0 and mergeable is True,
        "conflict": not draft and (mergeable is False or mergeable_state == "dirty"),
        "review-requested": bool(requested or teams),
        "changes-requested": bool(changes),
        "required-approval": required > 0 and review_decision == "APPROVED",
        "unresolved-thread": resolution and unresolved > 0,
        "collaboration-clear": (
            not requested
            and not teams
            and not changes
            and (required == 0 or review_decision == "APPROVED")
            and unresolved == 0
        ),
    }
    check = _check(expected, expectations[expected], authority)
    return {
        "command": "inspect-authority",
        "repository": REPOSITORY,
        "number": pr_number,
        "url": pull.get("html_url"),
        "expectation": expected,
        "authority": authority,
        "checks": [check],
        "ok": check["pass"],
    }


def parser() -> argparse.ArgumentParser:
    value = argparse.ArgumentParser(prog="python -m hamsterdan.operator")
    commands = value.add_subparsers(dest="command", required=True)
    pre = commands.add_parser("preflight")
    pre.add_argument("--health-url")
    create_parser = commands.add_parser("create")
    create_parser.add_argument("--scenario", choices=CREATABLE_SCENARIOS, required=True)
    commands.add_parser("prepare-broker")
    inspect_parser = commands.add_parser("inspect")
    inspect_parser.add_argument("--pr", type=int, required=True)
    inspect_parser.add_argument("--bot-login", default=APP_BOT_LOGIN)
    inspect_parser.add_argument("--expect-hero-review", action="store_true")
    inspect_parser.add_argument("--expect-readiness", choices=("present", "absent"), default="present")
    authority_parser = commands.add_parser("inspect-authority")
    authority_parser.add_argument("--pr", type=int, required=True)
    authority_parser.add_argument("--expect", choices=AUTHORITY_EXPECTATIONS, required=True)
    setup_parser = commands.add_parser("qualification-setup")
    setup_parser.add_argument("--credential-file", type=Path, required=True)
    setup_parser.add_argument("--target-file", type=Path, required=True)
    setup_parser.add_argument("--spent-marker", type=Path, required=True)
    return value


def main() -> int:
    args = parser().parse_args()
    try:
        if args.command == "preflight":
            output = preflight(health_url=args.health_url)
        elif args.command == "create":
            output = create(args.scenario)
        elif args.command == "prepare-broker":
            output = prepare_broker()
        elif args.command == "inspect":
            output = inspect(
                args.pr,
                bot_login=args.bot_login,
                expect_hero_review=args.expect_hero_review,
                expect_readiness=args.expect_readiness == "present",
            )
        elif args.command == "qualification-setup":
            output = qualification_setup(args.credential_file, args.target_file, args.spent_marker)
        else:
            output = inspect_authority(args.pr, args.expect)
    except OperatorError as error:
        output = {"command": args.command, "ok": False, "error": str(error)}
    print(json.dumps(output, sort_keys=True))
    return 0 if output.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
