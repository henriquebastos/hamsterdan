"""AX28 focused tests — one file to first motion through a general harness.

The claims under test:

- One authoring file (domain steps + composition + ``first_motion``)
  reaches a quiescent instance on the frozen engine, with the branch
  routing live and both exits reachable.
- The harness hides no durable artifact: the canonical definition is
  deterministic, the History records are real, and replay over a fresh
  compile of the same block rebuilds the identical marking.
- The harness is general: a structurally different net (a data-driven
  cycle from ``loop``) runs through the *same* ``first_motion`` with
  zero additional composition — the generality ruling's criterion.
- Validation is not weakened: an unsound block is refused before any
  motion, and a non-quiescing net hits a diagnostic budget instead of
  spinning silently.
- The store choice is surfaced, never hidden: an explicitly supplied
  History Store is used as given and labeled as such.
"""

from __future__ import annotations

from dataclasses import replace

import pytest
from ax23_blocks import Block, CompositionError, KernelPlace, classify, loop
from ax28_motion import MotionError, first_motion
from ax28_one_file import demo, order_workflow
from petrus.impetus.history_store import InMemoryHistoryStore

# -- the one-file example -------------------------------------------------------------


class TestOneFile:
    def test_the_one_file_example_reaches_first_motion(self) -> None:
        motion = demo()
        assert motion.settled == {
            "settled": [{"sku": "sku-1", "total": 12.0}],
            "review": [],
        }
        assert len(motion.records) > 0

    def test_the_branch_routes_live(self) -> None:
        motion = demo({"sku": "sku-2", "amount": 100.0})
        assert motion.settled == {
            "settled": [],
            "review": [{"sku": "sku-2", "total": 30.0}],
        }

    def test_the_definition_is_deterministic_across_motions(self) -> None:
        assert demo().definition == demo().definition

    def test_replay_rebuilds_the_identical_marking(self) -> None:
        motion = demo()
        replayed = motion.replay()
        assert replayed.settled == motion.settled
        assert len(replayed.records) == len(motion.records)


# -- generality: a structurally different net, the same harness ----------------------


def bounded_attempts() -> Block:
    def attempt(job: dict) -> tuple[str, dict]:
        tries = job["tries"] + 1
        if tries >= 3:
            return "done", {"tries": tries}
        return "retry", {"tries": tries}

    return classify(
        "attempt",
        attempt,
        accepts="Job",
        outcomes={"done": "Result", "retry": "Job"},
        pure=True,
    )


class TestGenerality:
    def test_a_cyclic_net_runs_through_the_same_harness(self) -> None:
        # ``loop`` fuses the retry exit back into the entry: the authored
        # tree compiles to a cyclic net, and the very same ``first_motion``
        # drives it — no per-shape composition, which is the generality
        # ruling's criterion for a primitive-level mechanism.
        motion = first_motion(loop(bounded_attempts(), on="retry"), {"tries": 0}, net_name="retry")
        assert motion.settled == {"done": [{"tries": 3}]}

    def test_the_cyclic_net_replays_too(self) -> None:
        motion = first_motion(loop(bounded_attempts(), on="retry"), {"tries": 0}, net_name="retry")
        assert motion.replay().settled == motion.settled


# -- honesty: validation, budgets, and the visible store choice ----------------------


class TestHonesty:
    def test_an_unsound_block_is_refused_before_motion(self) -> None:
        healthy = order_workflow()
        broken = replace(healthy, nodes=(*healthy.nodes, KernelPlace("orphan", "X")))
        with pytest.raises(CompositionError, match="orphan"):
            first_motion(broken, {"sku": "s", "amount": 1.0})

    def test_a_non_quiescing_net_hits_the_diagnostic_budget(self) -> None:
        def forever(job: dict) -> tuple[str, dict]:
            return "retry", {"tries": job["tries"] + 1}

        spinner = classify(
            "spinner",
            forever,
            accepts="Job",
            outcomes={"done": "Result", "retry": "Job"},
            pure=True,
        )
        with pytest.raises(MotionError, match="did not quiesce within 10 advances"):
            first_motion(loop(spinner, on="retry"), {"tries": 0}, limit=10)

    def test_a_supplied_store_is_used_and_labeled(self) -> None:
        store = InMemoryHistoryStore()
        motion = first_motion(order_workflow(), {"sku": "s", "amount": 10.0}, history=store)
        assert motion.history is store
        assert motion.store_defaulted is False
        assert demo().store_defaulted is True
