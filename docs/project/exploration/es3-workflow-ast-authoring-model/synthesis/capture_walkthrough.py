"""Capture every intermediate representation of the canonical ES-003
workflow — receive → parallel(reserve, taxes) → charge → judge/route —
from authoring expression to replay, using the real spike code
(AX23 algebra, AX24 parallel, AX26 typed façade) on the frozen engine.

Run from the repo root:

    .venv/bin/python docs/project/exploration/es3-workflow-ast-authoring-model/synthesis/capture_walkthrough.py

The output is deterministic; the committed copy lives in
walkthrough-capture.txt and is quoted throughout
04-end-to-end-walkthrough.md. If spike code changes, re-run and re-commit.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
EXPERIMENTS = HERE.parent / "experiments"
for sibling in (
    "ax11-real-fragment",
    "ax19-kernel-boundary",
    "ax23-completed-algebra",
    "ax24-parallel-blocks",
    "ax26-static-typing",
):
    sys.path.insert(0, str(EXPERIMENTS / sibling))

from ax19_kernel import BoundaryTransition, KernelPlace  # noqa: E402
from ax23_blocks import check_sound, compile_block  # noqa: E402
from cases_good import workflow  # noqa: E402  (the typed canonical workflow)
from petrus.engine import Engine  # noqa: E402
from petrus.impetus.history_store import InMemoryHistoryStore  # noqa: E402
from petrus.impetus.net_definition import project_net_definition, serialize_net_definition  # noqa: E402
from petrus.impetus.petrinet import Marking, NetPath, Token  # noqa: E402


def banner(title: str) -> None:
    print()
    print("=" * 78)
    print(f"  {title}")
    print("=" * 78)


def marking_snapshot(engine: Engine, places: list[str]) -> list[str]:
    lines = []
    for name in places:
        tokens = engine.marking.place(NetPath(name))
        if tokens:
            rendered = ", ".join(f"{t.color}{json.dumps(t.data, sort_keys=True)}" for t in tokens)
            lines.append(f"    {name}: [{rendered}]")
    return lines or ["    (empty)"]


def main() -> None:
    # ---------------------------------------------------------------- stage 1
    banner("STAGE 1 — the authoring expression (what the author wrote)")
    print(
        """
  In cases_good.py (AX26), the canonical workflow is composed from typed
  leaves. This is the entire authoring surface — no places, transitions,
  or arcs are mentioned:

      both     = t_par2("both", first=reserve, second=taxes)
      routed   = t_route(judge, when_yes=settle, when_no=escalate, returns=Done)
      workflow = t_then(t_then(t_then(parse, both), charge), routed)
"""
    )

    # ---------------------------------------------------------------- stage 2
    banner("STAGE 2 — the typed value (what pyright/ty see)")
    print(f"\n  type(workflow)        = {type(workflow).__name__}")
    print("  static type           = TBlock[Raw, Done]   (revealed identically by pyright and ty)")
    print("  This layer is advisory: it exists so composition mistakes fail in the editor.")

    # ---------------------------------------------------------------- stage 3
    block = workflow.inner
    banner("STAGE 3 — the Block value (the composition algebra's view, AX23)")
    print(f"\n  name    = {block.name!r}")
    print(f"  pure    = {block.pure}")
    print(f"  entry   = Port(place={block.entry.place!r}, color={block.entry.color!r})")
    print("  exits:")
    for exit_name, port in block.exits.items():
        print(f"    {exit_name!r}: Port(place={port.place!r}, color={port.color!r})")
    print("  contexts:", dict(block.contexts) or "{}")

    # ---------------------------------------------------------------- stage 4
    banner("STAGE 4 — the kernel nodes inside the Block (AX18/AX19 IR)")
    places = [n for n in block.nodes if isinstance(n, KernelPlace)]
    transitions = [n for n in block.nodes if isinstance(n, BoundaryTransition)]
    print(f"\n  {len(places)} places, {len(transitions)} transitions\n")
    print("  places (name: color):")
    for p in places:
        print(f"    {p.name}: {p.color}")
    print("\n  transitions (arcs as mode(place), guard if any):")
    for t in transitions:
        arcs = ", ".join(f"{a.mode.name.lower()}({a.place})" for a in t.arcs)
        guard = f"  guard={t.guard!r}" if t.guard else ""
        print(f"    {t.name}: {arcs}{guard}")

    # ---------------------------------------------------------------- stage 5
    banner("STAGE 5 — soundness check + lowering to the frozen Petrus net")
    checked = check_sound(block)
    lowered = compile_block("walkthrough", checked)
    definition = serialize_net_definition(project_net_definition(lowered.built.net))
    print(f"\n  check_sound: passed (every node lies on an entry→exit path)")
    print(f"  serialized NetDefinition: {len(definition)} bytes, deterministic")
    print("  serialized definition (verbatim):\n")
    parsed = json.loads(definition)
    print("    " + "\n    ".join(json.dumps(parsed, indent=2, sort_keys=True).splitlines()))

    # ---------------------------------------------------------------- stage 6
    banner("STAGE 6 — execution on the frozen engine, one advance at a time")
    place_names = [p.name for p in places]
    history = InMemoryHistoryStore()
    engine = Engine.create(
        lowered.built.net,
        "walkthrough-run",
        history=history,
        dispatch=__import__("petrus.motus.dispatch", fromlist=["InlineDispatch"]).InlineDispatch({}),
        marking=Marking({NetPath(block.entry.place): (Token("Raw", {"payload": "ab"}),)}),
        handlers=dict(lowered.handlers),
        guards=dict(lowered.built.guards),
        activities=(),
    )
    print(f"\n  seed: Raw{{'payload': 'ab'}} placed on {block.entry.place!r}")
    print("\n  initial marking:")
    print("\n".join(marking_snapshot(engine, place_names)))
    step = 0
    while True:
        result = engine.advance()
        if not result.ready:
            break
        step += 1
        print(f"\n  after advance {step}:")
        print("\n".join(marking_snapshot(engine, place_names)))
    print(f"\n  quiesced after {step} advances")

    # ---------------------------------------------------------------- stage 7
    banner("STAGE 7 — the persisted history (the durable truth)")
    records = list(history.records)
    print(f"\n  {len(records)} records:")
    for i, record in enumerate(records):
        print(f"    {i:2d}  {type(record).__name__}")

    # ---------------------------------------------------------------- stage 8
    banner("STAGE 8 — replay: recompile from source, load the history")
    relowered = compile_block("walkthrough", check_sound(workflow.inner))
    resumed = Engine.load(
        relowered.built.net,
        "walkthrough-run",
        history=history,
        dispatch=__import__("petrus.motus.dispatch", fromlist=["InlineDispatch"]).InlineDispatch({}),
        handlers=dict(relowered.handlers),
        guards=dict(relowered.built.guards),
        activities=(),
    )
    print("\n  recompiled lowering is byte-identical:",
          serialize_net_definition(project_net_definition(relowered.built.net)) == definition)
    same = all(
        [t.data for t in resumed.marking.place(NetPath(n))] == [t.data for t in engine.marking.place(NetPath(n))]
        for n in place_names
    )
    print("  replayed marking equals live marking on every place:", same)
    print("\n  final marking after replay:")
    print("\n".join(marking_snapshot(resumed, place_names)))


if __name__ == "__main__":
    main()
