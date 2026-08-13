"""AX27 focused tests — generated authoring against the composition authority.

The claims under test:

- ``review`` is total: every candidate in the corpus — correct,
  characteristic generator mistakes, truncated text, dataclass
  surgery — comes back as structured Feedback at the expected stage.
- The messages are repair-grade: every refusal names the offending
  element, and the counted majority carries the remedy (the available
  alternatives) verbatim — pinned as numbers, not anecdotes.
- The loop shape works mechanically: the wrong-exit candidate's
  feedback message alone dictates the one-token fix, and the repaired
  candidate passes review.
- Review never executes the net — proven behaviorally, not by code
  inspection: with ``Engine.create``/``Engine.load`` poisoned, review
  of the good candidate still succeeds.
- The honest residue is demonstrated: an undeclared runtime outcome
  and a data-driven non-termination both pass review and are caught
  only by the explicitly separate motion stage (AX28's harness).
- The no-execution static stage fires: pinned pyright rejects the
  generated typed-façade mistake from source text alone, on exactly
  the marked line.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
from ax23_blocks import CompositionError
from ax27_corpus import GOOD, MISTAKES, REPAIR_V1, REPAIR_V2, RESIDUE
from ax27_review import review
from ax28_motion import MotionError, first_motion
from petrus.engine import Engine

HERE = Path(__file__).resolve().parent
PYRIGHT = "pyright@1.1.411"

# -- totality and stages ---------------------------------------------------------------


class TestStages:
    def test_the_good_candidate_passes_with_net_statistics(self) -> None:
        feedback = review(GOOD.name, GOOD.source)
        assert feedback.verdict == "ok"
        assert feedback.places > 0
        assert feedback.transitions > 0
        assert feedback.exits == ("review", "settled")
        assert feedback.definition_bytes > 0

    def test_review_is_deterministic(self) -> None:
        first = review(GOOD.name, GOOD.source)
        second = review(GOOD.name, GOOD.source)
        assert first == second

    @pytest.mark.parametrize("candidate", MISTAKES, ids=lambda c: c.name)
    def test_each_generator_mistake_is_refused_at_its_stage(self, candidate) -> None:
        feedback = review(candidate.name, candidate.source)
        assert feedback.verdict == "refused"
        assert feedback.stage == candidate.stage
        for fragment in candidate.fragments:
            assert fragment in feedback.message, f"{candidate.name}: {fragment!r} not in {feedback.message!r}"

    @pytest.mark.parametrize("candidate", MISTAKES, ids=lambda c: c.name)
    def test_refusal_source_positions_are_stage_honest(self, candidate) -> None:
        # source- and author-stage refusals point into the candidate's
        # own text; a sound-stage refusal happens after workflow() has
        # returned, so it names the offending *node*, never a line —
        # an honest limit the loop's operator must know.
        feedback = review(candidate.name, candidate.source)
        if candidate.stage == "sound":
            assert feedback.line is None
        else:
            assert feedback.line is not None
            assert 1 <= feedback.line <= len(candidate.source.splitlines())


# -- message quality, pinned as numbers ------------------------------------------------


class TestMessageQuality:
    def test_the_remedy_count_is_pinned(self) -> None:
        # A remedy means the message carries the concrete alternatives
        # verbatim — the actual exits, both colors, the branch list —
        # not merely what is wrong. Pinned so a message regression
        # fails a test. The other five refusals name the offending
        # element and state the violated rule, but repair needs the
        # candidate source too.
        remedies = 0
        for candidate in MISTAKES:
            message = review(candidate.name, candidate.source).message or ""
            if any(mark in message for mark in ("its exits are", "colors differ", "not one of", "at least two")):
                remedies += 1
        assert remedies == 5  # of 10 mistakes


# -- the mechanical repair loop --------------------------------------------------------


class TestRepairLoop:
    def test_the_feedback_message_alone_dictates_the_fix(self) -> None:
        feedback = review(REPAIR_V1.name, REPAIR_V1.source)
        assert feedback.verdict == "refused"
        # The message names the wrong port and lists the real ones:
        assert "'output'" in feedback.message
        assert "its exits are ['out']" in feedback.message
        # The repaired candidate is v1 with exactly that substitution:
        assert REPAIR_V2.source == REPAIR_V1.source.replace('on="output"', 'on="out"')
        assert review(REPAIR_V2.name, REPAIR_V2.source).verdict == "ok"


# -- review never executes the net -----------------------------------------------------


class TestNoMotion:
    def test_review_succeeds_with_the_engine_poisoned(self, monkeypatch) -> None:
        def poisoned(*args, **kwargs):
            raise AssertionError("review must never construct an Engine")

        monkeypatch.setattr(Engine, "create", poisoned)
        monkeypatch.setattr(Engine, "load", poisoned)
        assert review(GOOD.name, GOOD.source).verdict == "ok"


# -- the honest residue: only motion catches these -------------------------------------


class TestResidue:
    def test_an_undeclared_runtime_outcome_passes_review(self) -> None:
        candidate = RESIDUE[0]
        feedback = review(candidate.name, candidate.source)
        assert feedback.verdict == "ok"

    def test_only_motion_catches_the_undeclared_outcome(self) -> None:
        namespace: dict = {}
        exec(compile(RESIDUE[0].source, "<residue>", "exec"), namespace)  # noqa: S102 — residue demo needs the block
        with pytest.raises(CompositionError, match="classified 'oops'"):
            first_motion(namespace["workflow"](), {"total": 1.0})

    def test_data_driven_nontermination_passes_review(self) -> None:
        candidate = RESIDUE[1]
        assert review(candidate.name, candidate.source).verdict == "ok"

    def test_only_motion_catches_the_nontermination(self) -> None:
        namespace: dict = {}
        exec(compile(RESIDUE[1].source, "<residue>", "exec"), namespace)  # noqa: S102 — residue demo needs the block
        with pytest.raises(MotionError, match="did not quiesce"):
            first_motion(namespace["workflow"](), {"tries": 0}, limit=10)


# -- the no-execution static stage -----------------------------------------------------


@pytest.fixture(scope="module")
def pyright_run() -> dict:
    if shutil.which("uvx") is None:
        pytest.skip("uvx unavailable: cannot run pinned pyright")
    result = subprocess.run(
        ["uvx", PYRIGHT, "--pythonpath", sys.executable, "--outputjson", "cases_generated_static.py"],
        cwd=HERE,
        capture_output=True,
        text=True,
        timeout=300,
        check=False,  # a non-zero exit just means diagnostics were found
    )
    return json.loads(result.stdout)


class TestStaticStage:
    def test_pyright_rejects_the_generated_mistake_from_source_alone(self, pyright_run) -> None:
        marked = next(
            number
            for number, line in enumerate((HERE / "cases_generated_static.py").read_text().splitlines(), start=1)
            if line.rstrip().endswith("# expect-error")
        )
        errors = [d for d in pyright_run["generalDiagnostics"] if d["severity"] == "error"]
        assert errors, "the pinned checker must reject the generated mistake"
        # pyright reports the overload failure as two diagnostics; both
        # must sit on the marked line and nowhere else.
        assert {d["range"]["start"]["line"] + 1 for d in errors} == {marked}
