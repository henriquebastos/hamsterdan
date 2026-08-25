"""ES-010 experiment 1: current import DAG, SCCs, fan-in, and fan-out.

Throwaway exploration evidence, not maintained production code. Reuses the
relative-import-aware AST approach owned by tests/test_architecture.py.

Run from the repository root:

    uv run python docs/project/exploration/es10-composable-hamsterdan-architecture/experiments/tools/import_graph.py
"""

from __future__ import annotations

import ast
import importlib.util
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).parents[6]
SOURCE = ROOT / "src" / "hamsterdan"


def module_name(path: Path) -> str:
    relative = path.relative_to(SOURCE)
    parts = list(relative.parts)
    if parts[-1] == "__init__.py":
        parts = parts[:-1]
    else:
        parts[-1] = parts[-1][:-3]
    return ".".join(("hamsterdan", *parts))


def raw_imports(path: Path) -> set[str]:
    package = module_name(path)
    if not path.name == "__init__.py":
        package = package.rsplit(".", 1)[0]
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            module = (
                importlib.util.resolve_name("." * node.level + (node.module or ""), package)
                if node.level
                else node.module or ""
            )
            names.add(module)
            names.update(f"{module}.{alias.name}" for alias in node.names if alias.name != "*")
    return names


def resolve_to_modules(names: set[str], modules: set[str]) -> set[str]:
    """Map imported dotted names to the longest known hamsterdan module prefix."""
    resolved: set[str] = set()
    for name in names:
        if not (name == "hamsterdan" or name.startswith("hamsterdan.")):
            continue
        candidate = name
        while candidate and candidate not in modules:
            candidate = candidate.rpartition(".")[0]
        if candidate:
            resolved.add(candidate)
    return resolved


def tarjan_sccs(graph: dict[str, set[str]]) -> list[list[str]]:
    index: dict[str, int] = {}
    lowlink: dict[str, int] = {}
    on_stack: set[str] = set()
    stack: list[str] = []
    counter = 0
    sccs: list[list[str]] = []

    def strongconnect(node: str) -> None:
        nonlocal counter
        index[node] = lowlink[node] = counter
        counter += 1
        stack.append(node)
        on_stack.add(node)
        for target in sorted(graph.get(node, ())):
            if target not in index:
                strongconnect(target)
                lowlink[node] = min(lowlink[node], lowlink[target])
            elif target in on_stack:
                lowlink[node] = min(lowlink[node], index[target])
        if lowlink[node] == index[node]:
            component: list[str] = []
            while True:
                member = stack.pop()
                on_stack.discard(member)
                component.append(member)
                if member == node:
                    break
            sccs.append(sorted(component))

    sys.setrecursionlimit(10_000)
    for node in sorted(graph):
        if node not in index:
            strongconnect(node)
    return sccs


def main() -> None:
    paths = sorted(SOURCE.rglob("*.py"))
    modules = {module_name(path) for path in paths}
    graph: dict[str, set[str]] = {module: set() for module in sorted(modules)}
    for path in paths:
        owner = module_name(path)
        graph[owner] |= resolve_to_modules(raw_imports(path), modules) - {owner}

    fan_out = {module: len(targets) for module, targets in graph.items()}
    fan_in: dict[str, int] = defaultdict(int)
    for targets in graph.values():
        for target in targets:
            fan_in[target] += 1

    print("== modules ==")
    print(len(modules))

    print("\n== cycles (SCCs with more than one module) ==")
    cycles = [scc for scc in tarjan_sccs(graph) if len(scc) > 1]
    if not cycles:
        print("none")
    for scc in cycles:
        print("  " + " <-> ".join(scc))

    print("\n== fan-in (top 20) ==")
    for module, count in sorted(fan_in.items(), key=lambda item: -item[1])[:20]:
        print(f"  {count:3d}  {module}")

    print("\n== fan-out (top 20) ==")
    for module, count in sorted(fan_out.items(), key=lambda item: -item[1])[:20]:
        print(f"  {count:3d}  {module}")

    print("\n== edges ==")
    for module in sorted(graph):
        for target in sorted(graph[module]):
            print(f"  {module} -> {target}")


if __name__ == "__main__":
    main()
