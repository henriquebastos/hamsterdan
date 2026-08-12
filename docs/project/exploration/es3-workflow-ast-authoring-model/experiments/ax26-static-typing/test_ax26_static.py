"""AX26 focused tests — what each checker actually catches, pinned.

Two halves:

- The checker harness runs pyright 1.1.411 and ty 0.0.63 (both pinned)
  over the fixtures and asserts, line by line, which marked mistakes
  each one rejects. The differences are assertions, not anecdotes: a
  version bump that changes the story fails a test and forces the
  record to be updated.
- The runtime half proves the façade is a shadow, not a fantasy: the
  same typed values lower through AX23/AX24 unchanged and run on the
  frozen engine, TypedDict data flowing as the plain dicts it already
  is.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
from ax23_blocks import check_sound
from ax26_typed import TPure, t_fn, t_par2, t_route, t_then
from cases_good import escalate, judge, parse, reserve, settle, taxes, workflow
from petrus.engine import Engine
from petrus.impetus.history_store import InMemoryHistoryStore
from petrus.impetus.net_definition import project_net_definition, serialize_net_definition
from petrus.impetus.petrinet import Marking, NetPath, Token
from petrus.motus.dispatch import InlineDispatch
from test_ax11_fragment import drive_bounded, place_data

HERE = Path(__file__).resolve().parent
REPO = next(p for p in HERE.parents if (p / "pyproject.toml").is_file())
FIXTURES = ("ax26_typed.py", "cases_good.py", "cases_bad.py", "cases_infer.py")

PYRIGHT = "pyright@1.1.411"
SIBLINGS = ("ax11-real-fragment", "ax19-kernel-boundary", "ax23-completed-algebra", "ax24-parallel-blocks")


def marked_lines(marker: str) -> dict[str, int]:
    """Map each marked case (by the name it assigns) to its line number."""
    found: dict[str, int] = {}
    for number, line in enumerate((HERE / "cases_bad.py").read_text().splitlines(), start=1):
        if line.rstrip().endswith(f"# {marker}"):
            found[line.split("=")[0].strip()] = number
    return found


EXPECTED = marked_lines("expect-error")
HOLES = marked_lines("expect-hole")

#: ty 0.0.63 reveals fully precise types (see the inference test) but does
#: not yet fail calls whose generic constraints are unsatisfiable — every
#: miss below is a generic-parameter mismatch; every catch is structural
#: (missing argument, overload arity, nominal subclass at the top level).
TY_MISSES = {"bad_sequence", "bad_handler", "bad_merge", "bad_par"}


@pytest.fixture(scope="module")
def pyright_run() -> dict:
    if shutil.which("uvx") is None:
        pytest.skip("uvx unavailable: cannot run pinned pyright")
    result = subprocess.run(
        ["uvx", PYRIGHT, "--pythonpath", sys.executable, "--outputjson", *FIXTURES],
        cwd=HERE,
        capture_output=True,
        text=True,
        timeout=300,
        check=False,  # a non-zero exit just means diagnostics were found
    )
    return json.loads(result.stdout)


@pytest.fixture(scope="module")
def ty_run() -> str:
    ty = Path(sys.executable).parent / "ty"
    if not ty.is_file():
        pytest.skip("ty not installed in this environment")
    search = [arg for sibling in SIBLINGS for arg in ("--extra-search-path", str(HERE.parent / sibling))]
    result = subprocess.run(
        [str(ty), "check", "--output-format", "concise", *search, "--extra-search-path", str(HERE), *FIXTURES],
        cwd=HERE,
        capture_output=True,
        text=True,
        timeout=300,
        check=False,  # a non-zero exit just means diagnostics were found
    )
    return result.stdout


def error_lines(diagnostics: list[tuple[str, int]], file: str) -> set[int]:
    return {line for name, line in diagnostics if name == file}


def pyright_errors(run: dict) -> list[tuple[str, int]]:
    return [
        (Path(d["file"]).name, d["range"]["start"]["line"] + 1)
        for d in run["generalDiagnostics"]
        if d["severity"] == "error"
    ]


def ty_errors(output: str) -> list[tuple[str, int]]:
    found = []
    for match in re.finditer(r"([\w./-]+\.py):(\d+):\d+: error\[", output):
        found.append((Path(match.group(1)).name, int(match.group(2))))
    return found


class TestPyright:
    def test_every_marked_mistake_is_rejected_and_nothing_else(self, pyright_run: dict) -> None:
        lines = error_lines(pyright_errors(pyright_run), "cases_bad.py")
        assert lines == set(EXPECTED.values())

    def test_the_facade_and_good_cases_are_clean(self, pyright_run: dict) -> None:
        errors = pyright_errors(pyright_run)
        assert error_lines(errors, "ax26_typed.py") == set()
        assert error_lines(errors, "cases_good.py") == set()

    def test_the_known_hole_union_widening_of_a_contradicted_leaf(self, pyright_run: dict) -> None:
        # Two independent sources for O (fn's return and returns=) widen
        # to `Raw | Order` instead of conflicting. t_fn closes the hole
        # by having one source.
        assert set(HOLES.values()).isdisjoint(error_lines(pyright_errors(pyright_run), "cases_bad.py"))


class TestTy:
    def test_structural_mistakes_are_rejected(self, ty_run: str) -> None:
        lines = error_lines(ty_errors(ty_run), "cases_bad.py")
        caught = {name for name, line in EXPECTED.items() if line in lines}
        assert caught == set(EXPECTED) - TY_MISSES

    def test_generic_mismatches_are_the_misses(self, ty_run: str) -> None:
        lines = error_lines(ty_errors(ty_run), "cases_bad.py")
        assert {EXPECTED[name] for name in TY_MISSES}.isdisjoint(lines)

    def test_the_facade_and_good_cases_are_clean(self, ty_run: str) -> None:
        errors = ty_errors(ty_run)
        assert error_lines(errors, "ax26_typed.py") == set()
        assert error_lines(errors, "cases_good.py") == set()


class TestInference:
    """The hover an author lives with: both checkers reveal the same
    fully precise types for every probe, including the purity overload
    and the signature-inferred leaf."""

    PROBES = (
        "TBlock[Raw, Reservation]",
        "TBlock[Order, Join2[Reservation, Taxes]]",
        "TPure[Order, Order]",
        "TBlock[Raw, Receipt]",
        "TPure[Order, Order]",
        "TBlock[Receipt, Done]",
        "TPure[Raw, Order]",
    )

    def test_pyright_reveals_precise_types(self, pyright_run: dict) -> None:
        revealed = [
            re.search(r'is "(.+)"', d["message"]).group(1)  # type: ignore
            for d in pyright_run["generalDiagnostics"]
            if d["severity"] == "information" and Path(d["file"]).name == "cases_infer.py"
        ]
        assert tuple(revealed) == self.PROBES

    def test_ty_reveals_the_same_types(self, ty_run: str) -> None:
        revealed = re.findall(r"cases_infer\.py:\d+:\d+: info\[revealed-type\] Revealed type: `(.+)`", ty_run)
        assert tuple(revealed) == self.PROBES


# -- the runtime half: the shadow is real -------------------------------------------------


def run_typed(block, seed: Token) -> Engine:
    lowered_block = check_sound(block.inner)
    from ax23_blocks import compile_block

    lowered = compile_block("ax26-net", lowered_block)
    engine = Engine.create(
        lowered.built.net,
        "ax26",
        history=InMemoryHistoryStore(),
        dispatch=InlineDispatch({}),
        marking=Marking({NetPath(block.inner.entry.place): (seed,)}),
        handlers=dict(lowered.handlers),
        guards=dict(lowered.built.guards),
        activities=(),
    )
    drive_bounded(engine)
    return engine


class TestRuntime:
    def test_the_typed_workflow_runs_end_to_end_cheap_order_settles(self) -> None:
        engine = run_typed(workflow, Token("Raw", {"payload": "ab"}))
        assert place_data(engine, workflow.inner.exits["out"].place) == [{"ok": True}]

    def test_the_expensive_order_takes_the_other_route(self) -> None:
        engine = run_typed(workflow, Token("Raw", {"payload": "x" * 960}))
        assert place_data(engine, workflow.inner.exits["out"].place) == [{"ok": False}]

    def test_the_par_aggregate_is_the_typed_join_shape(self) -> None:
        both = t_par2("both", first=reserve, second=taxes)
        engine = run_typed(both, Token("Order", {"sku": "ab", "amount": 20}))
        [joined] = place_data(engine, both.inner.exits["out"].place)
        assert joined == {"first": {"sku": "ab", "hold_id": "H-ab"}, "second": {"tax": 2}}

    def test_t_fn_derives_the_colors_from_the_signature(self) -> None:
        def promote(raw: dict) -> dict:  # pragma: no cover - never fired
            return raw

        promote.__annotations__ = {"raw": dict, "return": dict}
        block = t_fn(promote)
        assert block.inner.entry.color == "dict"
        assert isinstance(t_fn(promote, pure=True), TPure)

    def test_types_become_the_same_colors_the_algebra_uses(self) -> None:
        assert parse.inner.entry.color == "Raw"
        assert parse.inner.exits["out"].color == "Order"
        assert judge.inner.exits["yes"].color == "Receipt"
        assert judge.inner.exits["no"].color == "Review"

    def test_route_lowers_to_then_plus_merge_with_one_exit(self) -> None:
        from cases_good import Done

        routed = t_route(judge, when_yes=settle, when_no=escalate, returns=Done)
        assert sorted(routed.inner.exits) == ["out"]
        assert routed.inner.exits["out"].color == "Done"

    def test_lowering_stays_deterministic(self) -> None:
        from ax23_blocks import compile_block

        def rendered() -> bytes:
            built = compile_block("ax26-det", workflow.inner).built
            return serialize_net_definition(project_net_definition(built.net))

        assert rendered() == rendered()

    def test_the_static_purity_story_matches_the_runtime_flag(self) -> None:
        # The overloads say pure ∘ pure = pure; the block underneath
        # must agree, or the shadow lies.
        assert parse.inner.pure
        assert not reserve.inner.pure
        assert not t_then(parse, reserve).inner.pure
        assert t_then(parse, taxes).inner.pure  # pure ∘ pure, statically TPure
