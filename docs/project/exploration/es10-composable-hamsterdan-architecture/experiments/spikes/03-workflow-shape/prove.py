"""Experiment 3 spike proofs. Run from this directory:

    uv run --frozen python prove.py

Proof 1 (structure): the spike `workflow` package is acyclic, contains no
package-object imports (the mechanism behind the current facade cycle), and
imports nothing outside Petrus definition modules, pydantic, and the stdlib.

Proof 2 (run): one decision runs end to end — HeadSeen/RunSeen observations
fold into facts, escalation requests a typed rerun Activity under a stable
operation identity, and the typed terminal folds back into the ladder —
driven only by a Petrus Engine over in-memory History with a fake activity.

Proof 3 (loud registry): removing a token class from the registry fails at
build-time validation with a message naming the color.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

from petrus.engine import Engine
from petrus.impetus.history_store import InMemoryHistoryStore
from petrus.impetus.petrinet import NetPath, Token
from petrus.motus.activity import activity as motus_activity
from petrus.motus.dispatch import InlineDispatch

from workflow.activities import RerunFault, RerunLanded, RerunMoved, RerunReq
from workflow.net.gating import VariantPayloadConverter, wire_gates
from workflow.net.topology import GATES, MANIFEST, build_net, seed_marking

PACKAGE_ROOT = Path(__file__).parent / "workflow"

ALLOWED_EXTERNAL_PREFIXES = (
    "petrus.impetus",
    "petrus.motus.activity",
    "pydantic",
    # stdlib used by the spike
    "dataclasses",
    "collections.abc",
    "json",
    "re",
    "types",
    "typing",
    "__future__",
)


def _modules() -> dict[str, Path]:
    modules = {}
    for path in sorted(PACKAGE_ROOT.rglob("*.py")):
        relative = path.relative_to(PACKAGE_ROOT.parent).with_suffix("")
        parts = relative.parts
        name = ".".join(parts[:-1] if parts[-1] == "__init__" else parts)
        modules[name] = path
    return modules


def _imports(path: Path) -> list[str]:
    tree = ast.parse(path.read_text())
    found = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                raise AssertionError(f"{path}: relative import — the spike uses full module paths only")
            found.append(node.module or "")
            # `from pkg import submodule` creates the package-object edge
            # behind the current facade cycle; forbid it structurally.
            for alias in node.names:
                if (PACKAGE_ROOT.parent / Path(*(node.module or "").split(".")) / f"{alias.name}.py").exists():
                    raise AssertionError(
                        f"{path}: package-object import 'from {node.module} import {alias.name}' — "
                        f"import the module by its full path instead"
                    )
    return found


def prove_structure() -> None:
    modules = _modules()
    edges: dict[str, set[str]] = {name: set() for name in modules}
    for name, path in modules.items():
        for imported in _imports(path):
            if imported in modules:
                edges[name].add(imported)
                continue
            forbidden = ("hamsterdan", "host", "github_app", "agents")
            if imported.split(".")[0] in forbidden:
                raise AssertionError(f"{name}: forbidden import {imported!r}")
            if not imported.startswith(ALLOWED_EXTERNAL_PREFIXES):
                raise AssertionError(f"{name}: unexpected external import {imported!r}")

    # cycle detection over intra-package edges
    state: dict[str, int] = {}  # 1 = visiting, 2 = done
    stack: list[str] = []

    def visit(node: str) -> None:
        if state.get(node) == 1:
            raise AssertionError(f"import cycle: {' -> '.join((*stack[stack.index(node) :], node))}")
        if state.get(node) == 2:
            return
        state[node] = 1
        stack.append(node)
        for successor in sorted(edges[node]):
            visit(successor)
        stack.pop()
        state[node] = 2

    for name in modules:
        visit(name)
    print(f"proof 1 OK: {len(modules)} modules, acyclic, no package-object imports, externals within allowance")


def prove_run() -> None:
    world: dict = {"rerun_operations": []}
    converter = VariantPayloadConverter()

    @motus_activity(converter=converter)
    def rerun_gate(work: RerunReq) -> RerunLanded | RerunMoved | RerunFault:
        world["rerun_operations"].append(work.op)
        return RerunLanded(fingerprint=work.fingerprint, op=work.op, run_id=work.run_id, attempt=work.attempt)

    definitions = {rerun_gate.declaration.name: rerun_gate}
    built = build_net()
    engine = Engine.create(
        built.net,
        "spike-pr",
        history=InMemoryHistoryStore(),
        dispatch=InlineDispatch(definitions),
        marking=seed_marking("spike:pr-1"),
        handlers=wire_gates(built, GATES, definitions, MANIFEST),
        guards=dict(built.guards),
        activities=tuple(definition.declaration for definition in definitions.values()),
    )

    def drive(limit: int = 100) -> None:
        for _ in range(limit):
            if not engine.advance().ready:
                return
        raise AssertionError(f"engine did not quiesce in {limit} advances")

    def one(place: str) -> dict:
        [data] = [token.data for token in engine.marking.place(NetPath(place))]
        return data

    head = {"head": "abc123", "base": "def456", "policy": "p1", "incarnation": 1}
    engine.deliver("on_head", Token("HeadSeen", head), identity="h-1")
    drive()
    assert one("ci.state")["head"] == "abc123", "observation did not fold into the CI baton"

    run = {"head": "abc123", "run_id": 7, "attempt": 1, "conclusion": "failure", "fingerprint": "fp-1"}
    engine.deliver("on_runs", Token("RunSeen", run), identity="r-1")
    drive()

    expected_operation = "rerun:fp-1:7:1"
    assert world["rerun_operations"] == [expected_operation], (
        f"gate saw operations {world['rerun_operations']}, expected [{expected_operation!r}]"
    )
    ladder = one("esc.ladder")
    assert (ladder["settled"], ladder["rungs"], ladder["fingerprint"]) == ("landed", 1, "fp-1"), (
        f"typed terminal did not fold into the ladder: {ladder}"
    )
    assert not any(name == "hamsterdan" or name.startswith("hamsterdan.") for name in sys.modules), (
        "the run imported hamsterdan production code"
    )
    print(
        "proof 2 OK: observation -> fact -> RerunReq"
        f" (operation {expected_operation!r}) -> RerunLanded folded; no hamsterdan imports"
    )


def prove_loud_registry() -> None:
    import workflow.net.topology as topology

    built = topology.build_net()
    broken = dict(topology.TOKEN_CLASSES)
    del broken["CiState"]
    try:
        topology._validate(built.net, broken, topology.GATES, topology.MANIFEST)
    except ValueError as error:
        assert "CiState" in str(error), f"build-time failure does not name the color: {error}"
        print(f"proof 3 OK: build-time validation failed loudly: {error}")
        return
    raise AssertionError("validation accepted a registry missing a declared place color")


if __name__ == "__main__":
    prove_structure()
    prove_run()
    prove_loud_registry()
    print("all proofs passed")
