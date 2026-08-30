# Copyright (c) 2026 Henrique Bastos

"""The strict feedback profile remains executable and replacement-only."""

from __future__ import annotations

import os
from pathlib import Path
import stat
import subprocess
from typing import TYPE_CHECKING


if TYPE_CHECKING:
    from pathlib import Path as PathType


ROOT = Path(__file__).parents[1]
CHECK = ROOT / "scripts" / "check"
EXPECTED_COMMANDS = [
    "run ruff check --config quality/hamsterdan2/ruff.toml src/hamsterdan2 tests2",
    "run ruff format --check --config quality/hamsterdan2/ruff.toml src/hamsterdan2 tests2",
    "run ty check src/hamsterdan2 tests2",
    "run ast-grep test --config quality/hamsterdan2/sgconfig.yml --skip-snapshot-tests",
    "run ast-grep scan --config quality/hamsterdan2/sgconfig.yml src/hamsterdan2 tests2",
    "run pytest -q -o addopts= tests2",
]
EXPECTED_QUICK_COMMANDS = [
    "run ruff check src/hamsterdan tests deployment",
    "run ruff format --check src/hamsterdan tests deployment",
    "run ty check src/hamsterdan deployment",
    "run pytest -q tests/test_architecture.py",
    *EXPECTED_COMMANDS,
]


def feedback_environment(tmp_path: PathType) -> tuple[dict[str, str], PathType]:
    executable_directory = tmp_path / "bin"
    executable_directory.mkdir()
    log = tmp_path / "commands.log"
    uv = executable_directory / "uv"
    uv.write_text('#!/usr/bin/env bash\nprintf \'%s\\n\' "$*" >> "$CHECK_LOG"\n', encoding="utf-8")
    uv.chmod(stat.S_IRWXU)
    environment = {
        **os.environ,
        "CHECK_LOG": str(log),
        "PATH": f"{executable_directory}:{os.environ['PATH']}",
    }
    return environment, log


def test_hamsterdan2_profile_invokes_only_the_isolated_replacement_gate(tmp_path: PathType) -> None:
    environment, log = feedback_environment(tmp_path)

    result = subprocess.run(  # noqa: S603 -- the repository-owned executable and arguments are fixed.
        (CHECK, "hamsterdan2"),
        cwd=ROOT,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0
    assert log.read_text(encoding="utf-8").splitlines() == EXPECTED_COMMANDS


def test_hamsterdan2_profile_refuses_path_overrides(tmp_path: PathType) -> None:
    environment, log = feedback_environment(tmp_path)

    result = subprocess.run(  # noqa: S603 -- the repository-owned executable and arguments are fixed.
        (CHECK, "hamsterdan2", "src/hamsterdan"),
        cwd=ROOT,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 2
    assert "does not accept paths" in result.stderr
    assert not log.exists()


def test_default_quick_composes_current_and_replacement_feedback_without_scope_leakage(tmp_path: PathType) -> None:
    environment, log = feedback_environment(tmp_path)

    result = subprocess.run(  # noqa: S603 -- the repository-owned executable and arguments are fixed.
        (CHECK, "quick"),
        cwd=ROOT,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0
    assert log.read_text(encoding="utf-8").splitlines() == EXPECTED_QUICK_COMMANDS
