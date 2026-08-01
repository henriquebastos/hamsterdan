"""Executable package and dependency boundaries for the standalone application."""

from __future__ import annotations

import ast
import importlib.util
from pathlib import Path

import hamsterdan

ROOT = Path(__file__).parents[1]
SOURCE = ROOT / "src" / "hamsterdan"
SIBLINGS = frozenset({"agents", "github_app", "readiness"})


def _hamsterdan_imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path.relative_to(ROOT)))
    relative = path.relative_to(SOURCE)
    package = ".".join(("hamsterdan", *relative.parts[:-1]))
    imports: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(name.name for name in node.names if name.name.startswith("hamsterdan."))
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                module = importlib.util.resolve_name("." * node.level + (node.module or ""), package)
            else:
                module = node.module or ""
            if module == "hamsterdan" or module.startswith("hamsterdan."):
                imports.add(module)
                imports.update(f"{module}.{name.name}" for name in node.names if name.name != "*")
    return imports


def test_project_uses_the_petrus_distribution_without_compatibility_facades() -> None:
    from petrus.engine import Engine
    from petrus.impetus.dsl import NetSpec
    from petrus.impetus.petrinet import Net
    from petrus.motus.activity import ActivityDefinition

    assert all(value is not None for value in (ActivityDefinition, Engine, Net, NetSpec))
    assert importlib.util.find_spec("impetus") is None
    assert hamsterdan.__all__ == []


def test_sibling_subsystems_never_import_one_another() -> None:
    for owner in SIBLINGS:
        forbidden = {f"hamsterdan.{sibling}" for sibling in SIBLINGS - {owner}}
        for path in (SOURCE / owner).rglob("*.py"):
            imported = _hamsterdan_imports(path)
            escaped = {
                name
                for name in imported
                if any(name == prefix or name.startswith(prefix + ".") for prefix in forbidden)
            }
            assert not escaped, f"{path.relative_to(ROOT)} imports sibling subsystem(s): {sorted(escaped)}"


def test_only_host_may_import_concrete_sibling_subsystems() -> None:
    permitted = SOURCE / "host"
    for path in SOURCE.rglob("*.py"):
        if path.is_relative_to(permitted):
            continue
        imported = _hamsterdan_imports(path)
        concrete = {
            name
            for name in imported
            if any(name == f"hamsterdan.{owner}" or name.startswith(f"hamsterdan.{owner}.") for owner in SIBLINGS)
        }
        owner = path.relative_to(SOURCE).parts[0]
        own_prefix = f"hamsterdan.{owner}"
        escaped = {name for name in concrete if name != own_prefix and not name.startswith(own_prefix + ".")}
        assert not escaped, f"{path.relative_to(ROOT)} composes concrete subsystem(s): {sorted(escaped)}"
