"""The routine pytest policy rejects silent loss of selected evidence."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[1]


@pytest.mark.parametrize(
    "parallel",
    [(), ("-n", "2", "--dist", "loadscope")],
    ids=("serial", "xdist"),
)
def test_forbid_skips_turns_a_selected_skip_into_failure(parallel: tuple[str, ...]) -> None:
    result = subprocess.run(
        (
            "uv",
            "run",
            "--frozen",
            "pytest",
            "-q",
            "-o",
            "addopts=",
            "--forbid-skips",
            *parallel,
            "tests/fixtures/skip_probe.py",
        ),
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 1
    assert "forbidden skips: 1" in result.stdout
    assert "test_missing_evidence" in result.stdout
