"""Executable package and dependency boundaries for the standalone application."""

from __future__ import annotations

import ast
import importlib.util
from pathlib import Path

import hamsterdan

ROOT = Path(__file__).parents[1]
SOURCE = ROOT / "src" / "hamsterdan"
SIBLINGS = frozenset({"agents", "github_app", "readiness"})


def _imports(source: str, package: str, filename: str = "<fixture>") -> set[str]:
    tree = ast.parse(source, filename=filename)
    imports: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(name.name for name in node.names)
        elif isinstance(node, ast.ImportFrom):
            module = (
                importlib.util.resolve_name("." * node.level + (node.module or ""), package)
                if node.level
                else node.module or ""
            )
            imports.add(module)
            imports.update(f"{module}.{name.name}" for name in node.names if name.name != "*")
    return imports


def _source_imports(path: Path) -> set[str]:
    relative = path.relative_to(SOURCE)
    package = ".".join(("hamsterdan", *relative.parts[:-1]))
    return _imports(path.read_text(encoding="utf-8"), package, str(path.relative_to(ROOT)))


def _hamsterdan_imports(path: Path) -> set[str]:
    return {name for name in _source_imports(path) if name == "hamsterdan" or name.startswith("hamsterdan.")}


def _matches_module(name: str, module: str) -> bool:
    return name == module or name.startswith(module + ".")


def test_import_scanner_resolves_relative_imports() -> None:
    assert "hamsterdan.agents" in _imports("from ..agents import AgentRunner", "hamsterdan.host")


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

    host_imports: set[str] = set()
    for path in permitted.rglob("*.py"):
        host_imports.update(_hamsterdan_imports(path))
    expected = {"hamsterdan.agents", "hamsterdan.github_app.gateway", "hamsterdan.readiness.net_v5"}
    assert expected <= host_imports, (
        f"host is missing concrete composition import(s): {sorted(expected - host_imports)}"
    )


def test_sibling_and_contract_packages_never_import_host() -> None:
    for owner in (*SIBLINGS, "contracts"):
        for path in (SOURCE / owner).rglob("*.py"):
            imported = _hamsterdan_imports(path)
            assert not any(_matches_module(name, "hamsterdan.host") for name in imported), (
                f"{path.relative_to(ROOT)} imports host"
            )


def test_host_never_imports_examples() -> None:
    for path in (SOURCE / "host").rglob("*.py"):
        imported = _source_imports(path)
        assert not any(name == "examples" or name.startswith("examples.") for name in imported), (
            f"{path.relative_to(ROOT)} imports examples"
        )


def test_agenticus_imports_remain_in_agents_and_host() -> None:
    permitted = {"agents", "host"}
    for path in SOURCE.rglob("*.py"):
        imported = _source_imports(path)
        if any(_matches_module(name, "petrus.agenticus") for name in imported):
            assert path.relative_to(SOURCE).parts[0] in permitted, (
                f"{path.relative_to(ROOT)} imports Petrus Agenticus outside agents or host"
            )


def test_project_rejects_petrus_root_and_compatibility_facades() -> None:
    for path in SOURCE.rglob("*.py"):
        imported = _source_imports(path)
        forbidden = {name for name in imported if name == "petrus" or name == "impetus" or name.startswith("impetus.")}
        assert not forbidden, f"{path.relative_to(ROOT)} uses Petrus facade import(s): {sorted(forbidden)}"


def test_host_owns_petrus_runtime_custody() -> None:
    runtime_prefixes = ("petrus.engine", "petrus.motus.dispatch", "petrus.motus.worker")
    for path in SOURCE.rglob("*.py"):
        if path.is_relative_to(SOURCE / "host"):
            continue
        imported = _source_imports(path)
        escaped = {name for name in imported if any(_matches_module(name, module) for module in runtime_prefixes)}
        assert not escaped, f"{path.relative_to(ROOT)} imports host-owned Petrus runtime concept(s): {sorted(escaped)}"


def test_provider_libraries_remain_at_owned_boundaries() -> None:
    for path in SOURCE.rglob("*.py"):
        imported = _source_imports(path)
        relative = path.relative_to(SOURCE)
        owner = relative.parts[0]
        provider_imports = {
            name for name in imported if any(_matches_module(name, module) for module in ("githubkit", "httpx"))
        }
        assert not provider_imports or owner == "github_app", (
            f"{path.relative_to(ROOT)} imports GitHub provider library outside github_app: {sorted(provider_imports)}"
        )
        fastapi_imports = {name for name in imported if _matches_module(name, "fastapi")}
        assert not fastapi_imports or owner == "host", (
            f"{path.relative_to(ROOT)} imports FastAPI outside host: {sorted(fastapi_imports)}"
        )
