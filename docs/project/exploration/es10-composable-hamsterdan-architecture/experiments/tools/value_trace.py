"""ES-010 experiment 2: producer/consumer trace for every workflow value.

Throwaway exploration evidence, not maintained production code. For every
name defined in ``contracts/readiness_v5.py`` (classes and type aliases) plus
the four live ``contracts/readiness.py`` names found by experiment 1, this
scans every module under ``src/hamsterdan`` and reports:

- ``C`` constructions (``ast.Call`` whose func resolves to the name);
- ``R`` other name references (annotations, ``isinstance``, unions, reads);
- ``S`` string-literal occurrences (token colors, History record vocabulary).

Run from the repository root:

    uv run python docs/project/exploration/es10-composable-hamsterdan-architecture/experiments/tools/value_trace.py
"""

from __future__ import annotations

import ast
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).parents[6]
SOURCE = ROOT / "src" / "hamsterdan"
VOCAB = SOURCE / "contracts" / "readiness_v5.py"
LIVE_RETIRED = ("WorkflowModel", "AdmittedConversation", "ChangeResult", "RepairResult")


def module_name(path: Path) -> str:
    relative = path.relative_to(SOURCE)
    parts = list(relative.parts)
    if parts[-1] == "__init__.py":
        parts = parts[:-1]
    else:
        parts[-1] = parts[-1][:-3]
    return ".".join(("hamsterdan", *parts))


def defined_names(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    names: list[str] = []
    for node in tree.body:
        if isinstance(node, ast.ClassDef):
            names.append(node.name)
        elif isinstance(node, ast.Assign) and len(node.targets) == 1:
            target = node.targets[0]
            if isinstance(target, ast.Name):
                names.append(target.id)
        elif isinstance(node, ast.TypeAlias) and isinstance(node.name, ast.Name):
            names.append(node.name.id)
    return names


def trace(path: Path, names: set[str]) -> dict[str, tuple[int, int, int]]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    calls: dict[str, int] = defaultdict(int)
    refs: dict[str, int] = defaultdict(int)
    strings: dict[str, int] = defaultdict(int)
    call_func_nodes = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            func = node.func
            name = None
            if isinstance(func, ast.Name):
                name = func.id
            elif isinstance(func, ast.Attribute):
                name = func.attr
            if name in names:
                calls[name] += 1
                call_func_nodes.add(id(func))
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and node.id in names and id(node) not in call_func_nodes:
            refs[node.id] += 1
        elif isinstance(node, ast.Attribute) and node.attr in names and id(node) not in call_func_nodes:
            refs[node.attr] += 1
        elif isinstance(node, ast.Constant) and isinstance(node.value, str):
            for token in node.value.replace(":", " ").replace(".", " ").split():
                if token in names:
                    strings[token] += 1
    return {
        name: (calls[name], refs[name], strings[name])
        for name in names
        if calls[name] or refs[name] or strings[name]
    }


def main() -> None:
    names = set(defined_names(VOCAB)) | set(LIVE_RETIRED)
    per_name: dict[str, dict[str, tuple[int, int, int]]] = defaultdict(dict)
    for path in sorted(SOURCE.rglob("*.py")):
        module = module_name(path)
        for name, counts in trace(path, names).items():
            per_name[name][module] = counts
    for name in sorted(names):
        sites = per_name.get(name, {})
        print(f"== {name} ==")
        if not sites:
            print("  (no references)")
        for module, (c, r, s) in sorted(sites.items()):
            marks = []
            if c:
                marks.append(f"C{c}")
            if r:
                marks.append(f"R{r}")
            if s:
                marks.append(f"S{s}")
            print(f"  {module:60s} {' '.join(marks)}")


if __name__ == "__main__":
    main()
