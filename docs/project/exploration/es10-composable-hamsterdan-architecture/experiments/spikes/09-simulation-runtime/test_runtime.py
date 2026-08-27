from __future__ import annotations

import ast
import inspect
import math
import unittest
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any

from runtime import (
    ActionRef,
    Artifact,
    Budget,
    BudgetExceeded,
    LeafExecuted,
    LeafOffered,
    OneLeafViolation,
    SimulationError,
    StaleGeneration,
    StepCompleted,
    Timeline,
    replay,
)


class ResponseLost(RuntimeError):
    pass


@dataclass
class _Store:
    scheduled: dict[str, int] = field(default_factory=dict)
    effects: dict[str, str] = field(default_factory=dict)
    completed: set[str] = field(default_factory=set)
    sources: dict[str, str] = field(default_factory=dict)


class _Module:
    def __init__(self, name: str) -> None:
        self.name = name
        self.store = _Store()

    def open(self, _context: object) -> _Generation:
        return _Generation(self.name, self.store)

    def drop(self, _generation: _Generation) -> None:
        pass

    def close(self, _generation: _Generation) -> None:
        pass

    def resource_usage(self, _generation: _Generation | None) -> dict[str, int]:
        return {
            f"{self.name}.effects": len(self.store.effects),
            f"{self.name}.pending": len(self.store.scheduled.keys() - self.store.completed),
        }


class _Generation:
    def __init__(self, module: str, store: _Store) -> None:
        self.module = module
        self.store = store

    def command(self, name: str, payload: object, _context: object) -> object:
        if name != "schedule" or type(payload) is not dict or set(payload) != {"operation", "at_us"}:
            raise ValueError("expected one exact schedule command")
        operation, at_us = payload["operation"], payload["at_us"]
        if type(operation) is not str or type(at_us) is not int:
            raise ValueError("schedule values have invalid types")
        previous = self.store.scheduled.get(operation)
        if previous is not None and previous != at_us:
            raise ValueError("operation was rescheduled at a different instant")
        self.store.scheduled[operation] = at_us
        return {"operation": operation, "at_us": at_us, "existing": previous is not None}

    def observe(self, name: str, payload: object, _context: object) -> object:
        if name != "state" or payload not in (None, {}):
            raise ValueError("expected the state observation without parameters")
        return {
            "scheduled": dict(sorted(self.store.scheduled.items())),
            "effects": dict(sorted(self.store.effects.items())),
            "completed": sorted(self.store.completed),
            "sources": dict(sorted(self.store.sources.items())),
        }

    def eligible_actions(self, _context: object) -> tuple[ActionRef, ...]:
        return tuple(
            ActionRef(module=self.module, name="apply", identity=operation, eligible_at_us=at_us)
            for operation, at_us in sorted(self.store.scheduled.items())
            if operation not in self.store.completed
        )

    async def step(self, action: ActionRef, context: Any) -> object:
        result = await context.call(
            "write",
            {"operation": action.identity},
            lambda: self._write(action.identity, context),
        )
        self.store.completed.add(action.identity)
        self.store.sources[action.identity] = result["source"]
        return {"operation": action.identity, **result}

    def _write(self, operation: str, context: Any) -> object:
        if operation in self.store.effects:
            return {"source": "lookup", "marker": self.store.effects[operation]}
        marker = context.choose("marker", ("left", "right"))
        self.store.effects[operation] = marker
        if any(fault.payload == {"response_lost": True} for fault in context.faults("write.after_commit")):
            raise ResponseLost(f"response lost after {self.module}:{operation}")
        return {"source": "effect", "marker": marker}


class _TwoLeafGeneration(_Generation):
    async def step(self, action: ActionRef, context: Any) -> object:
        await context.call("first", {"operation": action.identity}, lambda: {"first": True})
        return await context.call("second", {"operation": action.identity}, lambda: {"second": True})


class _TwoLeafModule(_Module):
    def open(self, _context: object) -> _Generation:
        return _TwoLeafGeneration(self.name, self.store)


RESOURCE_LIMITS = {
    "alpha.effects": 16,
    "alpha.pending": 16,
    "beta.effects": 16,
    "beta.pending": 16,
}

DEFAULT_BUDGET = Budget(
    operations=256,
    owner_steps=64,
    eligible_actions=16,
    leaf_calls=64,
    choice_draws=64,
    active_faults=16,
    generations=16,
    logical_time_us=1_000,
    journal_entries=1_024,
    artifact_bytes=1_000_000,
    resources=RESOURCE_LIMITS,
)


def _pair() -> tuple[tuple[_Module, _Module], dict[str, _Store]]:
    alpha, beta = _Module("alpha"), _Module("beta")
    return (alpha, beta), {"alpha": alpha.store, "beta": beta.store}


class PairSimulationContract(unittest.TestCase):
    """Independent modules share execution mechanics without sharing semantic state."""

    def test_pair_shares_time_ordering_crash_and_exact_replay(self) -> None:
        modules, stores = _pair()
        timeline = Timeline.open(modules, DEFAULT_BUDGET, seed=9)

        timeline.command("alpha", "schedule", {"operation": "before", "at_us": 1})
        timeline.advance(1)
        offered = timeline.start()
        self.assertIsInstance(offered, LeafOffered)
        timeline.crash("before_leaf")
        with self.assertRaises(StaleGeneration):
            timeline.start()
        timeline = timeline.restart()
        self.assertIsInstance(timeline.step(), StepCompleted)

        timeline.command("alpha", "schedule", {"operation": "ambiguous", "at_us": 2})
        timeline.fault("alpha", "write.after_commit", occurrence=1, payload={"response_lost": True})
        timeline.advance(2)
        self.assertIsInstance(timeline.start(), LeafOffered)
        executed = timeline.execute()
        self.assertIsInstance(executed, LeafExecuted)
        self.assertEqual(executed.error.kind, "ResponseLost")
        timeline.crash("after_leaf")
        timeline = timeline.restart()
        recovered = timeline.step()
        self.assertIsInstance(recovered, StepCompleted)
        self.assertEqual(recovered.value["source"], "lookup")

        timeline.command("beta", "schedule", {"operation": "returned", "at_us": 3})
        timeline.advance(3)
        self.assertIsInstance(timeline.step(), StepCompleted)
        timeline.crash("after_owner_return")
        timeline = timeline.restart()

        timeline.command("alpha", "schedule", {"operation": "tie-a", "at_us": 10})
        timeline.command("beta", "schedule", {"operation": "tie-b", "at_us": 10})
        timeline.advance(10)
        self.assertIsInstance(timeline.step(), StepCompleted)
        self.assertIsInstance(timeline.step(), StepCompleted)

        alpha = timeline.observe("alpha", "state")
        beta = timeline.observe("beta", "state")
        self.assertEqual((timeline.now_us, alpha.instant_us, beta.instant_us), (10, 10, 10))
        self.assertEqual(alpha.value["completed"], ["ambiguous", "before", "tie-a"])
        self.assertEqual(beta.value["completed"], ["returned", "tie-b"])
        self.assertEqual(stores["alpha"].effects.keys(), {"before", "ambiguous", "tie-a"})
        self.assertEqual(stores["beta"].effects.keys(), {"returned", "tie-b"})

        artifact = timeline.artifact("independent-pair")
        encoded = artifact.encode()
        decoded = Artifact.decode(encoded)
        report = replay(decoded, lambda: _pair()[0])

        self.assertTrue(report.exact)
        self.assertEqual(report.operations, len(artifact.operations))
        self.assertEqual(report.journal_digest, artifact.journal_digest)
        self.assertEqual(decoded, artifact)
        self.assertEqual(artifact.modules, ("alpha", "beta"))
        self.assertEqual(artifact.origin["algorithm"], "sha256-counter-v1")
        leaf_records = [operation["result"] for operation in artifact.operations if operation["kind"] == "execute"]
        self.assertTrue(leaf_records)
        self.assertTrue(all(set(result) == {"action", "leaf", "outcome"} for result in leaf_records))
        owner_return_records = [
            operation["result"] for operation in artifact.operations if operation["kind"] == "finish"
        ]
        self.assertTrue(owner_return_records)
        self.assertTrue(all(set(result) == {"action", "outcome"} for result in owner_return_records))
        self.assertNotIn("ResponseLost", encoded.decode())
        selected = [
            operation["result"]["action"]["module"]
            for operation in artifact.operations
            if operation["kind"] == "start" and operation["result"]["status"] == "offered"
        ]
        self.assertEqual(set(selected[-2:]), {"alpha", "beta"})
        scheduler_draws = [
            choice["selected"].split(":", 1)[0]
            for operation in artifact.operations
            for choice in operation["choices"]
            if choice["stream"] == "runtime:event_order"
        ]
        self.assertEqual(scheduler_draws, selected[-2:-1])
        self.assertEqual(
            [operation["result"]["phase"] for operation in artifact.operations if operation["kind"] == "crash"],
            ["offered", "executed", "idle"],
        )

    def test_one_owner_step_cannot_yield_a_second_leaf(self) -> None:
        module = _TwoLeafModule("alpha")
        budget = replace(DEFAULT_BUDGET, resources={"alpha.effects": 4, "alpha.pending": 4})
        timeline = Timeline.open((module,), budget, seed=1)
        timeline.command("alpha", "schedule", {"operation": "two", "at_us": 0})

        self.assertIsInstance(timeline.start(), LeafOffered)
        self.assertIsInstance(timeline.execute(), LeafExecuted)
        with self.assertRaises(OneLeafViolation):
            timeline.finish()

    def test_budget_failure_is_explicit_and_replayable(self) -> None:
        modules, _stores = _pair()
        budget = replace(DEFAULT_BUDGET, operations=1)
        timeline = Timeline.open(modules, budget, seed=3)
        timeline.command("alpha", "schedule", {"operation": "first", "at_us": 1})

        with self.assertRaisesRegex(BudgetExceeded, "operations"):
            timeline.command("beta", "schedule", {"operation": "second", "at_us": 1})

        artifact = timeline.artifact("operation-budget")
        report = replay(artifact, lambda: _pair()[0])
        self.assertTrue(report.exact)
        self.assertEqual(artifact.operations[-1]["kind"], "failure")
        self.assertFalse(artifact.operations[-1]["accepted"])
        with self.assertRaisesRegex(SimulationError, "already ended"):
            timeline.observe("alpha", "state")

    def test_owner_step_budget_stops_before_another_leaf_effect(self) -> None:
        modules, stores = _pair()
        timeline = Timeline.open(modules, replace(DEFAULT_BUDGET, owner_steps=1), seed=4)
        timeline.command("alpha", "schedule", {"operation": "first", "at_us": 0})
        timeline.command("beta", "schedule", {"operation": "second", "at_us": 1})

        self.assertIsInstance(timeline.step(), StepCompleted)
        timeline.advance(1)
        with self.assertRaisesRegex(BudgetExceeded, "owner_steps"):
            timeline.step()

        self.assertEqual(sum(len(store.effects) for store in stores.values()), 1)
        artifact = timeline.artifact("owner-step-budget")
        self.assertTrue(replay(artifact, lambda: _pair()[0]).exact)
        self.assertEqual(artifact.operations[-1]["attempt"]["kind"], "start")

    def test_journal_budget_failure_after_an_accepted_operation_replays_exactly(self) -> None:
        modules, _stores = _pair()
        timeline = Timeline.open(modules, replace(DEFAULT_BUDGET, journal_entries=3), seed=5)

        with self.assertRaisesRegex(BudgetExceeded, "journal_entries"):
            timeline.command("alpha", "schedule", {"operation": "accepted", "at_us": 0})

        artifact = timeline.artifact("journal-budget")
        self.assertTrue(replay(artifact, lambda: _pair()[0]).exact)
        self.assertEqual(artifact.operations[-1]["kind"], "failure")
        self.assertTrue(artifact.operations[-1]["accepted"])
        self.assertEqual(artifact.operations[-1]["error"]["bound"], "journal_entries")

    def test_leaf_budget_failure_discards_the_frame_and_replays_exactly(self) -> None:
        modules, _stores = _pair()
        timeline = Timeline.open(modules, replace(DEFAULT_BUDGET, leaf_calls=1), seed=6)
        timeline.command("alpha", "schedule", {"operation": "first", "at_us": 0})
        timeline.command("beta", "schedule", {"operation": "second", "at_us": 1})
        self.assertIsInstance(timeline.step(), StepCompleted)
        timeline.advance(1)
        self.assertIsInstance(timeline.start(), LeafOffered)

        with self.assertRaisesRegex(BudgetExceeded, "leaf_calls"):
            timeline.execute()

        artifact = timeline.artifact("leaf-budget")
        self.assertTrue(replay(artifact, lambda: _pair()[0]).exact)
        self.assertEqual(artifact.operations[-1]["attempt"]["kind"], "execute")

    def test_generation_budget_failure_after_crash_has_an_exact_artifact(self) -> None:
        modules, _stores = _pair()
        timeline = Timeline.open(modules, replace(DEFAULT_BUDGET, generations=1), seed=7)
        timeline.crash("generation-limit")

        with self.assertRaisesRegex(BudgetExceeded, "generations"):
            timeline.restart()

        artifact = timeline.artifact("generation-budget")
        self.assertIsNone(artifact.generation)
        self.assertTrue(replay(artifact, lambda: _pair()[0]).exact)
        self.assertEqual(artifact.operations[-1]["attempt"]["kind"], "restart")

    def test_artifact_byte_budget_is_enforced(self) -> None:
        modules, _stores = _pair()
        timeline = Timeline.open(modules, replace(DEFAULT_BUDGET, artifact_bytes=64), seed=8)
        timeline.command("alpha", "schedule", {"operation": "first", "at_us": 1})

        with self.assertRaisesRegex(BudgetExceeded, "artifact_bytes"):
            timeline.artifact("too-large")

    def test_runtime_source_has_no_application_semantics_or_dependency(self) -> None:
        source = Path(inspect.getfile(Timeline)).read_text()
        tree = ast.parse(source)
        imported = {
            alias.name.split(".")[0]
            for node in ast.walk(tree)
            if isinstance(node, (ast.Import, ast.ImportFrom))
            for alias in node.names
        }
        identifiers = {node.id.lower() for node in ast.walk(tree) if isinstance(node, ast.Name)}

        self.assertNotIn("petrus", imported)
        self.assertNotIn("hamsterdan", imported)
        self.assertTrue({"workflow", "readiness", "github", "agent", "host"}.isdisjoint(identifiers))

    def test_budget_rejects_non_finite_or_boolean_limits(self) -> None:
        with self.assertRaises(ValueError):
            replace(DEFAULT_BUDGET, logical_time_us=True)
        with self.assertRaises(ValueError):
            replace(DEFAULT_BUDGET, resources={"alpha.effects": math.inf})
        with self.assertRaises(ValueError):
            replace(DEFAULT_BUDGET, journal_entries=1)


if __name__ == "__main__":
    unittest.main()
