from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from hamsterdan import operator
from hamsterdan.host.publication_qualification import AtomicSetupPush, SetupCategory, SetupPhase, qualify_setup

REMOTE = "https://github.com/example/private-fixture.git"


def git(cwd: Path, *arguments: str) -> str:
    result = subprocess.run(("git", *arguments), cwd=cwd, capture_output=True, text=True, check=True)
    return result.stdout.strip()


def fixture(tmp_path: Path) -> tuple[Path, str, str]:
    work = tmp_path / "work"
    work.mkdir()
    git(work, "init", "--quiet", "--initial-branch=main")
    git(work, "config", "user.name", "Qualification")
    git(work, "config", "user.email", "qualification@invalid")
    (work / "base").write_text("base\n")
    git(work, "add", "base")
    git(work, "commit", "--quiet", "-m", "base")
    base = git(work, "rev-parse", "HEAD")
    (work / "head").write_text("head\n")
    git(work, "add", "head")
    git(work, "commit", "--quiet", "-m", "head")
    return work, base, git(work, "rev-parse", "HEAD")


def test_actual_local_atomic_push_preserves_admitted_command_and_restart_fence(tmp_path: Path) -> None:
    work, base, head = fixture(tmp_path)
    bare = tmp_path / "remote.git"
    git(tmp_path, "init", "--bare", "--quiet", str(bare))
    marker_parent = tmp_path / "custody"
    marker_parent.mkdir(mode=0o700)
    marker = marker_parent / "spent"
    admitted: list[tuple[str, ...]] = []

    def adapter(command: tuple[str, ...]) -> int:
        admitted.append(command)
        local = (*command[:3], str(bare), *command[4:])
        return subprocess.run(local, cwd=work, capture_output=True, check=False).returncode

    outcome = AtomicSetupPush(marker).push(REMOTE, base, head, adapter)

    assert outcome.command_succeeded
    assert admitted == [
        ("git", "push", "--atomic", REMOTE, f"{base}:refs/heads/main", f"{head}:refs/heads/hamsterdan/ds11-live-v4")
    ]
    assert git(tmp_path, "--git-dir", str(bare), "rev-parse", "refs/heads/main") == base
    assert git(tmp_path, "--git-dir", str(bare), "rev-parse", "refs/heads/hamsterdan/ds11-live-v4") == head
    assert marker.exists()

    replay = AtomicSetupPush(marker).push(REMOTE, base, head, adapter)
    assert replay.category is SetupCategory.ALREADY_SPENT
    assert len(admitted) == 1 and marker.exists()


def test_actual_local_atomic_rejection_creates_neither_requested_ref(tmp_path: Path) -> None:
    work, base, head = fixture(tmp_path)
    bare = tmp_path / "remote.git"
    git(tmp_path, "init", "--bare", "--quiet", str(bare))
    git(work, "push", str(bare), f"{head}:refs/heads/main")
    marker_parent = tmp_path / "custody"
    marker_parent.mkdir(mode=0o700)

    def adapter(command: tuple[str, ...]) -> int:
        local = (*command[:3], str(bare), *command[4:])
        return subprocess.run(local, cwd=work, capture_output=True, check=False).returncode

    outcome = AtomicSetupPush(marker_parent / "spent").push(REMOTE, base, head, adapter)

    assert outcome.category is SetupCategory.PUSH_UNCONFIRMED
    assert git(tmp_path, "--git-dir", str(bare), "rev-parse", "refs/heads/main") == head
    missing = subprocess.run(
        ("git", "--git-dir", str(bare), "rev-parse", "--verify", "refs/heads/hamsterdan/ds11-live-v4"),
        capture_output=True,
        check=False,
    )
    assert missing.returncode != 0


def setup_orchestration(tmp_path: Path, **overrides):
    custody = tmp_path / "orchestration-custody"
    custody.mkdir(mode=0o700)
    calls: list[str] = []
    values = {
        "identity": lambda: calls.append("identity") is None,
        "target": lambda: calls.append("target") is None,
        "pre_push": lambda: calls.append("pre_push") is None,
        "runner": lambda _command: calls.append("push") or 0,
        "readback": lambda: calls.append("readback") is None,
        "pull_request": lambda: calls.append("pull_request") is None,
        "current_cas": lambda: calls.append("current_cas") is None,
        "stale_cas": lambda: calls.append("stale_cas") is None,
        "cleanup": lambda: calls.append("cleanup") is None,
    }
    values.update(overrides)
    outcome = qualify_setup(
        identity=values["identity"],
        target=values["target"],
        pre_push=values["pre_push"],
        push=AtomicSetupPush(custody / "spent"),
        remote=REMOTE,
        base="a" * 40,
        head="b" * 40,
        runner=values["runner"],
        readback=values["readback"],
        pull_request=values["pull_request"],
        current_cas=values["current_cas"],
        stale_cas=values["stale_cas"],
        cleanup=values["cleanup"],
    )
    return outcome, calls, custody / "spent"


def test_timeout_before_spend_suppresses_push_readback_pr_and_cas(tmp_path: Path) -> None:
    coordinate = "owner/private-timeout-coordinate"

    def timeout() -> bool:
        raise subprocess.TimeoutExpired(("gh", "api", f"/repos/{coordinate}"), 30, stderr="secret-canary")

    outcome, calls, marker = setup_orchestration(tmp_path, identity=timeout)

    assert calls == ["cleanup"]
    assert not marker.exists()
    assert outcome.first_cause_phase is SetupPhase.IDENTITY
    assert outcome.first_cause_category is SetupCategory.BOUNDARY_UNAVAILABLE
    assert coordinate not in json.dumps(outcome.sanitized())
    assert "secret-canary" not in json.dumps(outcome.sanitized())


def test_timeout_after_spend_reads_back_once_never_retries_and_preserves_marker(tmp_path: Path) -> None:
    attempts = 0
    readbacks = 0

    def timeout(command: tuple[str, ...]) -> int:
        nonlocal attempts
        attempts += 1
        raise subprocess.TimeoutExpired(command, 30, output="secret-canary", stderr="coordinate-canary")

    def readback() -> bool:
        nonlocal readbacks
        readbacks += 1
        return False

    outcome, calls, marker = setup_orchestration(tmp_path, runner=timeout, readback=readback)

    assert attempts == 1 and readbacks == 1
    assert calls == ["identity", "target", "pre_push", "cleanup"]
    assert marker.exists()
    assert outcome.first_cause_phase is SetupPhase.PUSH
    assert outcome.first_cause_category is SetupCategory.BOUNDARY_UNAVAILABLE
    assert outcome.pull_request is None and outcome.current_cas is None and outcome.stale_cas is None
    assert all(canary not in json.dumps(outcome.sanitized()) for canary in ("secret-canary", "coordinate-canary"))


def test_exact_readback_admits_read_only_pr_current_and_stale_cas_in_order(tmp_path: Path) -> None:
    outcome, calls, marker = setup_orchestration(tmp_path)

    assert calls == [
        "identity",
        "target",
        "pre_push",
        "push",
        "readback",
        "pull_request",
        "current_cas",
        "stale_cas",
        "cleanup",
    ]
    assert marker.exists() and outcome.accepted
    assert outcome.current_cas is not None and outcome.current_cas.confirmed
    assert outcome.stale_cas is not None and outcome.stale_cas.confirmed


def test_cleanup_uncertainty_does_not_replace_push_first_cause(tmp_path: Path) -> None:
    outcome, _, _ = setup_orchestration(
        tmp_path,
        runner=lambda _command: 1,
        readback=lambda: False,
        cleanup=lambda: False,
    )

    assert outcome.first_cause_phase is SetupPhase.PUSH
    assert outcome.first_cause_category is SetupCategory.PUSH_UNCONFIRMED
    assert not outcome.cleanup.confirmed
    assert outcome.cleanup.category is SetupCategory.OBSERVATION_UNCONFIRMED


def test_operator_route_isolates_environment_erases_private_material_and_retains_only_closed_evidence(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    custody = tmp_path / "custody"
    custody.mkdir(mode=0o700)
    credential = custody / "credential"
    target_file = custody / "target"
    marker = custody / "spent"
    secret = "credential-secret-canary"
    coordinate = "owner/private-coordinate-canary"
    credential.write_text(secret)
    target_file.write_text(json.dumps({"repository": coordinate, "account_id": 7, "repository_id": 11}))
    credential.chmod(0o600)
    target_file.chmod(0o600)
    monkeypatch.setenv("GH_TOKEN", "ambient-gh-token-canary")
    monkeypatch.setenv("GITHUB_TOKEN", "ambient-github-token-canary")
    monkeypatch.setenv("GIT_TRACE", "1")
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", "/private/ambient-config")
    observed_environments: list[dict[str, str]] = []
    observed_commands: list[tuple[str, ...]] = []
    roots: list[Path] = []
    base, head = "a" * 40, "b" * 40
    remote_state: dict[str, str] = {}

    def fake_runner(
        command: tuple[str, ...],
        cwd: Path,
        environment: dict[str, str],
        input_bytes: bytes | None,
    ) -> subprocess.CompletedProcess[bytes]:
        observed_commands.append(command)
        observed_environments.append(dict(environment))
        roots.append(Path(environment["HOME"]).parent)
        stderr = f"{secret}:{coordinate}:private-diagnostic".encode()
        executable = Path(command[0]).name
        assert input_bytes is None
        assert environment["GH_TOKEN"] == secret
        if executable == "gh" and command[1:] == ("api", "/user"):
            return subprocess.CompletedProcess(command, 0, b'{"id":7}', stderr)
        if executable == "gh" and command[1:] == ("api", f"/repos/{coordinate}"):
            body = {
                "full_name": coordinate,
                "id": 11,
                "private": False,
                "archived": False,
                "disabled": False,
                "size": 0,
                "default_branch": "main",
                "permissions": {"push": True},
            }
            return subprocess.CompletedProcess(command, 0, json.dumps(body).encode(), stderr)
        if executable != "git":
            raise AssertionError(command)
        if "rev-parse" in command:
            value = base if sum("rev-parse" in call for call in observed_commands) == 1 else head
            return subprocess.CompletedProcess(command, 0, (value + "\n").encode(), stderr)
        if "ls-remote" in command:
            names = command[command.index("ls-remote") + 3 :]
            if not names:
                output = remote_state
            else:
                output = {name: value for name, value in remote_state.items() if name in names}
            encoded = "".join(f"{value}\t{name}\n" for name, value in output.items()).encode()
            return subprocess.CompletedProcess(command, 0, encoded, stderr)
        if "push" in command:
            remote_state.update({"refs/heads/main": base, "refs/heads/hamsterdan/ds11-live-v4": head})
        return subprocess.CompletedProcess(command, 0, b"private-stdout-canary", stderr)

    result = operator.qualification_setup(credential, target_file, marker, runner=fake_runner)
    retained = json.dumps(result)

    assert result["ok"] is True and marker.exists()
    assert not credential.exists() and not target_file.exists()
    assert roots and all(not root.exists() for root in roots)
    assert all(
        forbidden not in environment
        for environment in observed_environments
        for forbidden in ("GITHUB_TOKEN", "GIT_TRACE", "GIT_CONFIG_COUNT")
    )
    assert all(environment["GIT_TERMINAL_PROMPT"] == "0" for environment in observed_environments)
    assert not any(command[1:3] == ("auth", "login") for command in observed_commands)
    git_commands = [command for command in observed_commands if Path(command[0]).name == "git"]
    assert git_commands and all("credential.helper=" in command for command in git_commands)
    assert all("core.hooksPath=/dev/null" in command for command in git_commands)
    assert all("http.followRedirects=false" in command for command in git_commands)
    assert all(
        canary not in retained
        for canary in (secret, coordinate, "private-diagnostic", "private-stdout-canary", "ambient-gh-token-canary")
    )
