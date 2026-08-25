"""The repository feedback command is bounded and self-describing."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

ROOT = Path(__file__).parents[1]
CHECK = ROOT / "scripts" / "check"


def _run(
    *arguments: str,
    cwd: Path = ROOT,
    environment: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        (str(CHECK), *arguments),
        cwd=cwd,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )


def _fake_tools(tmp_path: Path) -> tuple[dict[str, str], Path]:
    tools = tmp_path / "bin"
    tools.mkdir()
    log = tmp_path / "commands.log"
    program = (
        "#!/bin/sh\n"
        'printf \'%s|%s|%s\\n\' "$PWD" "$UV_FROZEN" "$*" >> "$CHECK_LOG"\n'
        'case "$*" in\n'
        "    *'ast-grep test'*) exit \"${FAKE_AST_GREP_TEST_EXIT:-${FAKE_TOOL_EXIT:-0}}\" ;;\n"
        '    *) exit "${FAKE_TOOL_EXIT:-0}" ;;\n'
        "esac\n"
    )
    for name in ("bun", "uv"):
        path = tools / name
        _ = path.write_text(program, encoding="utf-8")
        path.chmod(0o755)
    environment = os.environ | {
        "CHECK_LOG": str(log),
        "PATH": os.pathsep.join((str(tools), os.environ["PATH"])),
    }
    return environment, log


def test_check_script_is_valid_shell_and_describes_maintained_profiles() -> None:
    syntax = subprocess.run(("bash", "-n", str(CHECK)), cwd=ROOT, capture_output=True, text=True, check=False)
    assert syntax.returncode == 0, syntax.stderr

    result = _run("--help")
    assert result.returncode == 0
    assert "scripts/check quick [PATH ...]" in result.stdout
    for profile in ("full", "release", "audit", "mutation"):
        assert f"scripts/check {profile}" in result.stdout

    script = CHECK.read_text(encoding="utf-8")
    assert "export UV_FROZEN=1" in script
    assert "tests/test_architecture.py" in script
    assert "--forbid-skips" in script
    assert "-n 4 --dist load --maxschedchunk=1" in script
    assert "ruff check src tests --select C901" in script
    assert "ast-grep scan" in script
    assert "mutmut run" in script


def test_quick_resolves_the_repository_and_forwards_selected_paths(tmp_path: Path) -> None:
    environment, log = _fake_tools(tmp_path)

    result = _run("quick", "tests/test_architecture.py", cwd=ROOT / "docs", environment=environment)

    assert result.returncode == 0, result.stderr
    assert log.read_text(encoding="utf-8").splitlines() == [
        f"{ROOT}|1|run ruff check tests/test_architecture.py",
        f"{ROOT}|1|run ruff format --check tests/test_architecture.py",
        f"{ROOT}|1|run ty check src deployment",
        f"{ROOT}|1|run pytest -q tests/test_architecture.py",
    ]


def test_quick_defaults_to_maintained_python_paths(tmp_path: Path) -> None:
    environment, log = _fake_tools(tmp_path)

    result = _run("quick", environment=environment)

    assert result.returncode == 0, result.stderr
    commands = log.read_text(encoding="utf-8").splitlines()
    assert commands[:2] == [
        f"{ROOT}|1|run ruff check src tests deployment",
        f"{ROOT}|1|run ruff format --check src tests deployment",
    ]


def test_bounded_profiles_reject_paths_without_running_tools() -> None:
    for profile in ("full", "release", "audit", "mutation"):
        result = _run(profile, "tests/test_architecture.py")
        assert result.returncode == 2
        assert f"scripts/check {profile} does not accept paths" in result.stderr


def test_audit_reports_findings_without_becoming_a_gate(tmp_path: Path) -> None:
    environment, _ = _fake_tools(tmp_path)
    environment["FAKE_TOOL_EXIT"] = "1"
    environment["FAKE_AST_GREP_TEST_EXIT"] = "0"

    result = _run("audit", environment=environment)

    assert result.returncode == 0
    assert "reported findings" in result.stdout


def test_audit_and_mutation_propagate_broken_probe_status(tmp_path: Path) -> None:
    environment, _ = _fake_tools(tmp_path)
    environment["FAKE_TOOL_EXIT"] = "1"
    environment["FAKE_AST_GREP_TEST_EXIT"] = "2"
    audit = _run("audit", environment=environment)
    environment["FAKE_TOOL_EXIT"] = "1"
    mutation = _run("mutation", environment=environment)

    assert audit.returncode == 2
    assert "audit probe failed (2)" in audit.stderr
    assert mutation.returncode == 1
    assert "mutation probe failed (1)" in mutation.stderr


def test_unknown_profile_fails_with_usage() -> None:
    result = _run("unknown")
    assert result.returncode == 2
    assert "usage: scripts/check quick" in result.stderr
