"""ES-004 AX11 focused tests — payload shape contracts.

Claims under test:

- Nominal fusion: identical payload types fuse; different types
  refuse even when structurally identical — production's
  ChangeResult/RepairResult twins are the proof that same shape is
  not same meaning.
- The refusal is explained in fields: the AX4 mystery
  (ProvisionalHead → FindingPublicationRequest) becomes a named
  error listing exactly what the producer cannot provide.
- Adapters derive their contract from their signature; untyped or
  mis-typed adapters are refused with both port names.
- Guard field paths are validated against the payload type,
  traversing nested dataclasses — AX26's named limit, closed at the
  deterministic layer.
- The static twins: both pyright (pinned, via uvx) and ty (the
  project's own CI checker) reject all three marked mistakes and
  stay clean on the good fixture. Shape errors are structural, so —
  unlike AX26's generic constraints — ty catches every one today.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

import pytest
from ax11_shape import Port, ShapeError, adapter, fuse, fuse_through, guard_fields, missing_fields, required, shape
from hamsterdan.contracts.readiness import (
    ChangeResult,
    ConversationClassificationRequest,
    FindingPublicationRequest,
    RepairResult,
)
from shape_cases_good import announce_repair

HERE = Path(__file__).resolve().parent
FIXTURES = ("shape_cases_good.py", "shape_cases_bad.py")
PYRIGHT = "pyright@1.1.411"


@dataclass(frozen=True)
class ProvisionalHead:
    """AX3/AX4's exit payload, reproduced verbatim: the producer half
    of the original mystery."""

    provisional_head: str
    reused: bool


# -- rule 1: nominal fusion, structural twins refused -------------------------------------------


def test_identical_payload_types_fuse():
    fuse(Port("repair.settled", RepairResult), Port("accept.repair", RepairResult))


def test_structural_twins_do_not_fuse():
    """ChangeResult and RepairResult carry identical field lists
    (contracts/readiness.py:546-570); fusing them would corrupt
    repair lineage. Shape must never be identity."""
    assert shape(ChangeResult) == shape(RepairResult)
    with pytest.raises(ShapeError, match="same shape is not same meaning"):
        fuse(Port("change.settled", ChangeResult), Port("accept.repair", RepairResult))


# -- rule 2: the AX4 mystery becomes a field-level error -----------------------------------------


def test_the_ax4_mystery_is_now_a_named_error():
    with pytest.raises(ShapeError) as refusal:
        fuse(Port("committed", ProvisionalHead), Port("announce", FindingPublicationRequest))
    message = str(refusal.value)
    assert "'committed' (ProvisionalHead)" in message
    assert "'announce' (FindingPublicationRequest)" in message
    for field in ("operation", "epoch", "findings"):  # what the adapter had to invent
        assert field in message


def test_the_diff_names_type_mismatches_not_just_absences():
    @dataclass(frozen=True)
    class AlmostRight:
        epoch: str  # production wants int
        head: str
        operation: str
        base_head: str
        policy_digest: str
        findings: list[dict]
        lineage: list[dict]

    diff = missing_fields(AlmostRight, FindingPublicationRequest)
    assert diff == {"epoch": "is str, consumer wants int"}


def test_defaulted_fields_are_not_required():
    assert "fingerprint" not in required(RepairResult)  # has a default
    assert "epoch" in required(RepairResult)


# -- rule 3: adapters from signatures -------------------------------------------------------------


def test_typed_adapter_closes_the_gap():
    announce = adapter(announce_repair)
    assert (announce.accepts, announce.returns) == (RepairResult, FindingPublicationRequest)
    fuse_through(
        Port("repair.settled", RepairResult),
        announce,
        Port("announce", FindingPublicationRequest),
    )


def test_untyped_adapter_is_refused():
    def mystery(value):  # no annotations: the AX4 adapter's original sin
        return value

    with pytest.raises(ShapeError, match="the signature IS the contract"):
        adapter(mystery)


def test_misdeclared_adapter_is_refused_at_the_exact_seam():
    with pytest.raises(ShapeError, match="'committed' .* 'committed→announce_repair'"):
        fuse_through(
            Port("committed", ProvisionalHead),  # produces the wrong type for this adapter
            adapter(announce_repair),
            Port("announce", FindingPublicationRequest),
        )


# -- guard fields: AX26's named limit, closed ------------------------------------------------------


def test_guard_paths_validate_including_nested_dataclasses():
    guard_fields(Port("repair.settled", RepairResult), "fingerprint", "ok")
    guard_fields(
        Port("classify", ConversationClassificationRequest),
        "comment.actor_login",  # nested WorkflowModel traversal
        "control.repair_in_flight",
    )


def test_phantom_guard_field_names_the_type_and_the_candidates():
    with pytest.raises(ShapeError, match="RepairResult has no field 'risk_score'"):
        guard_fields(Port("repair.settled", RepairResult), "risk_score")


def test_guard_path_through_a_scalar_is_refused():
    with pytest.raises(ShapeError, match="epoch is int, which cannot have field 'value'"):
        guard_fields(Port("repair.settled", RepairResult), "epoch.value")


# -- the static twins: both checkers, all three mistakes ------------------------------------------


def expected_lines() -> set[int]:
    text = (HERE / "shape_cases_bad.py").read_text().splitlines()
    return {number for number, line in enumerate(text, start=1) if line.rstrip().endswith("# expect-error")}


def error_lines(diagnostics: list[tuple[str, int]], file: str) -> set[int]:
    return {line for name, line in diagnostics if name == file}


@pytest.fixture(scope="module")
def ty_run() -> list[tuple[str, int]]:
    ty = Path(sys.executable).parent / "ty"
    if not ty.is_file():
        pytest.skip("ty not installed in this environment")
    result = subprocess.run(
        [str(ty), "check", "--output-format", "concise", *FIXTURES],
        cwd=HERE,
        capture_output=True,
        text=True,
        timeout=300,
        check=False,
    )
    return [
        (Path(match.group(1)).name, int(match.group(2)))
        for match in re.finditer(r"([\w./-]+\.py):(\d+):\d+: error\[", result.stdout)
    ]


@pytest.fixture(scope="module")
def pyright_run() -> list[tuple[str, int]]:
    if shutil.which("uvx") is None:
        pytest.skip("uvx unavailable: cannot run pinned pyright")
    result = subprocess.run(
        ["uvx", PYRIGHT, "--pythonpath", sys.executable, "--outputjson", *FIXTURES],
        cwd=HERE,
        capture_output=True,
        text=True,
        timeout=300,
        check=False,
    )
    return [
        (Path(d["file"]).name, d["range"]["start"]["line"] + 1)
        for d in json.loads(result.stdout)["generalDiagnostics"]
        if d["severity"] == "error"
    ]


class TestTy:
    def test_all_marked_shape_mistakes_rejected_and_nothing_else(self, ty_run):
        assert error_lines(ty_run, "shape_cases_bad.py") == expected_lines()

    def test_good_adapter_is_clean(self, ty_run):
        assert error_lines(ty_run, "shape_cases_good.py") == set()


class TestPyright:
    def test_all_marked_shape_mistakes_rejected_and_nothing_else(self, pyright_run):
        assert error_lines(pyright_run, "shape_cases_bad.py") == expected_lines()

    def test_good_adapter_is_clean(self, pyright_run):
        assert error_lines(pyright_run, "shape_cases_good.py") == set()
