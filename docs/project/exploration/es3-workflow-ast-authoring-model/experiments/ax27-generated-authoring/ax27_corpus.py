"""AX27 corpus — candidate authoring sources as a generator would emit them.

One correct candidate, ten characteristic generator mistakes, and two
honest residue cases that no pre-motion review can catch. Every
candidate is a complete module against the general vocabulary
(AX23 ``transform``/``classify``/``then``/``merge``/``loop``, AX24
``par``) with the single authoring contract ``workflow() -> Block``.

Each mistake is the kind a code generator plausibly produces: a
misremembered port name, a step chained against the wrong color, a
name reused across leaves, a merge across different colors, a loop on
an exit that does not exist, truncated output. The expectation tuple
records where the authority must refuse it and which fragments the
message must carry for a mechanical repair to be possible.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from textwrap import dedent

_PRELUDE = """\
from ax23_blocks import classify, then, transform
from ax24_parallel import par


def intake():
    return transform("intake", lambda r: {"sku": r["sku"], "amount": r["amount"]}, accepts="Raw", returns="Order")


def reserve():
    return transform("reserve", lambda o: {"sku": o["sku"], "reserved": True}, accepts="Order", returns="Reservation")


def taxes():
    return transform("taxes", lambda o: {"sku": o["sku"], "tax": round(o["amount"] * 0.2, 2)}, accepts="Order", returns="Taxes")


def charge():
    return transform("charge", lambda q: {"sku": q["stock"]["sku"], "total": q["taxes"]["tax"] + 10.0}, accepts="Quote", returns="Receipt")


def judge():
    return classify(
        "judge",
        lambda r: ("settled", r) if r["total"] <= 15.0 else ("review", r),
        accepts="Receipt",
        outcomes={"settled": "Settlement", "review": "Review"},
        pure=True,
    )
"""


@dataclass(frozen=True)
class Candidate:
    name: str
    source: str
    expect: str  # "ok" | "refused" | "residue"
    stage: str | None = None
    fragments: tuple[str, ...] = field(default=())


def _candidate(
    name: str, body: str, *, expect: str, stage: str | None = None, fragments: tuple[str, ...] = ()
) -> Candidate:
    return Candidate(name, _PRELUDE + "\n\n" + dedent(body), expect=expect, stage=stage, fragments=fragments)


GOOD = _candidate(
    "good",
    """\
    def workflow():
        gathered = then(intake(), par("gather", {"stock": reserve(), "taxes": taxes()}, returns="Quote"), on="out")
        return then(then(gathered, charge(), on="out"), judge(), on="out")
    """,
    expect="ok",
)


MISTAKES = (
    _candidate(
        "wrong_exit_name",
        """\
        def workflow():
            return then(intake(), reserve(), on="output")
        """,
        expect="refused",
        stage="author",
        fragments=("'output'", "its exits are ['out']"),
    ),
    _candidate(
        "color_mismatch",
        """\
        def workflow():
            return then(intake(), charge(), on="out")
        """,
        expect="refused",
        stage="author",
        fragments=("Order", "Quote", "colors differ"),
    ),
    _candidate(
        "leaf_name_collision",
        """\
        def workflow():
            def normalize():
                return transform("normalize", lambda o: o, accepts="Order", returns="Order")

            return then(normalize(), normalize(), on="out")
        """,
        expect="refused",
        stage="author",
        fragments=("share node names", "must be unique"),
    ),
    _candidate(
        "merge_color_mismatch",
        """\
        from ax23_blocks import merge

        def workflow():
            return merge(judge(), "settled", "review", into="done")
        """,
        expect="refused",
        stage="author",
        fragments=("cannot merge", "colors differ"),
    ),
    _candidate(
        "loop_missing_exit",
        """\
        from ax23_blocks import loop

        def workflow():
            return loop(judge(), on="retry")
        """,
        expect="refused",
        stage="author",
        fragments=("'retry'", "its exits are"),
    ),
    _candidate(
        "loop_only_exit",
        """\
        from ax23_blocks import loop

        def workflow():
            noop = transform("noop", lambda o: o, accepts="Order", returns="Order")
            return loop(noop, on="out")
        """,
        expect="refused",
        stage="author",
        fragments=("only exit", "no way out"),
    ),
    _candidate(
        "classify_duplicate_colors",
        """\
        def workflow():
            return classify(
                "decide",
                lambda r: ("yes", r),
                accepts="Receipt",
                outcomes={"yes": "Answer", "no": "Answer"},
            )
        """,
        expect="refused",
        stage="author",
        fragments=("outcome colors must be distinct",),
    ),
    _candidate(
        "par_single_branch",
        """\
        def workflow():
            return then(intake(), par("gather", {"stock": reserve()}, returns="Quote"), on="out")
        """,
        expect="refused",
        stage="author",
        fragments=("at least two branches",),
    ),
    _candidate(
        "truncated_source",
        """\
        def workflow():
            return then(intake(), par("gather", {"stock": reserve(),
        """,
        expect="refused",
        stage="source",
        fragments=(),
    ),
    _candidate(
        "dataclass_surgery_orphan",
        """\
        from dataclasses import replace
        from ax23_blocks import KernelPlace

        def workflow():
            block = intake()
            return replace(block, nodes=(*block.nodes, KernelPlace("orphan", "X")))
        """,
        expect="refused",
        stage="sound",
        fragments=("orphan", "no entry"),
    ),
)


#: Honest residue: composition cannot see these; only motion can.
RESIDUE = (
    _candidate(
        "undeclared_runtime_outcome",
        """\
        def workflow():
            return classify(
                "decide",
                lambda r: ("oops", r),
                accepts="Receipt",
                outcomes={"yes": "Answer", "no": "Refusal"},
                pure=True,
            )
        """,
        expect="residue",
    ),
    _candidate(
        "data_driven_nontermination",
        """\
        from ax23_blocks import loop

        def workflow():
            spinner = classify(
                "spin",
                lambda j: ("retry", {"tries": j["tries"] + 1}),
                accepts="Job",
                outcomes={"done": "Result", "retry": "Job"},
                pure=True,
            )
            return loop(spinner, on="retry")
        """,
        expect="residue",
    ),
)


#: The repair-loop pair: v1 carries the wrong exit name; v2 is v1 with
#: exactly the mechanical fix the feedback message dictates.
REPAIR_V1 = MISTAKES[0]
REPAIR_V2 = Candidate("wrong_exit_name_repaired", REPAIR_V1.source.replace('on="output"', 'on="out"'), expect="ok")
