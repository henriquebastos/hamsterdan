# Copyright (c) 2026 Henrique Bastos

"""Audit that replacement enums stay private to their owning module."""

import ast
from pathlib import Path
from typing import cast


SOURCE_ROOT = Path("src/hamsterdan2")
ENUM_OWNERS: dict[str, str] = {}


def python_files(root: Path) -> list[Path]:
    return sorted(root.rglob("*.py"))


def module_name(path: Path, root: Path) -> str:
    return ".".join(path.relative_to(root).with_suffix("").parts)


def enum_imports(tree: ast.Module) -> list[tuple[str, str]]:
    imports = (node for node in ast.walk(tree) if isinstance(node, ast.ImportFrom) and node.module is not None)
    return [
        (cast("str", node.module), alias.name) for node in imports for alias in node.names if alias.name in ENUM_OWNERS
    ]


def member_chains(tree: ast.Module) -> list[str]:
    attributes = (node for node in ast.walk(tree) if isinstance(node, ast.Attribute))
    named = ((node.value, node.attr) for node in attributes if isinstance(node.value, ast.Name))
    return [f"{value.id}.{attribute}" for value, attribute in named if value.id in ENUM_OWNERS and attribute.isupper()]


def violations_in(path: Path, root: Path) -> list[str]:
    module = module_name(path, root)
    if any(module == owner for owner in ENUM_OWNERS.values()):
        return []
    tree = ast.parse(path.read_text(encoding="utf-8"))
    imports = [f"{module}: from {source} import {name}" for source, name in enum_imports(tree)]
    chains = [f"{module}: {chain}" for chain in member_chains(tree)]
    return imports + chains


def test_enums_are_read_through_predicates_outside_their_owner() -> None:
    found = [violation for path in python_files(SOURCE_ROOT) for violation in violations_in(path, SOURCE_ROOT)]

    assert not found, "Enum vocabulary leaked; read state through is_*/can_*/has_* predicates:\n" + "\n".join(found)
