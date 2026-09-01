# Copyright (c) 2026 Henrique Bastos

"""Package boundaries admitted by the first CV21 tracer."""

from __future__ import annotations

import ast
from graphlib import CycleError, TopologicalSorter
import importlib.util
from pathlib import Path

import pytest


ROOT = Path(__file__).parents[1]
SOURCE = ROOT / "src" / "hamsterdan2"
BRIDGE = SOURCE / "readiness" / "workflow_bridge.py"
RUNTIME = SOURCE / "readiness" / "runtime.py"
GITHUB_WEBHOOKS = SOURCE / "github_app" / "webhooks.py"
HOST_API = SOURCE / "host" / "api.py"
HOST_APPLICATION = SOURCE / "host" / "application.py"
HOST_COMPOSITION = SOURCE / "host" / "composition.py"
INGRESS = SOURCE / "readiness" / "ingress.py"
INGRESS_VALUES = SOURCE / "readiness" / "ingress_values.py"
PROJECTION = SOURCE / "readiness" / "projection.py"
WORKFLOW_OBSERVATIONS = SOURCE / "workflow" / "observations.py"
PROCESS_SIMULATION = SOURCE / "simulation" / "process.py"
LEGACY_ALLOWLIST = frozenset(
    {
        "hamsterdan.contracts.readiness_v5",
        "hamsterdan.readiness.net_v5.gating",
        "hamsterdan.readiness.net_v5.topology",
    }
)
PACKAGE_INITIALIZERS = tuple(SOURCE.rglob("__init__.py"))


def imports_from(source: str, package: str, filename: str = "<fixture>") -> set[str]:
    tree = ast.parse(source, filename=filename)
    imports: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            module = (
                importlib.util.resolve_name("." * node.level + (node.module or ""), package)
                if node.level
                else node.module or ""
            )
            imports.add(module)
    return imports


def module_name(path: Path) -> str:
    relative = path.relative_to(SOURCE).with_suffix("")
    parts = relative.parts[:-1] if relative.name == "__init__" else relative.parts
    return ".".join(("hamsterdan2", *parts))


def source_imports(path: Path) -> set[str]:
    package = (
        module_name(path.parent / "__init__.py")
        if path.is_relative_to(SOURCE)
        else ".".join(path.relative_to(ROOT).parts[:-1])
    )
    return imports_from(path.read_text(encoding="utf-8"), package, str(path.relative_to(ROOT)))


def matches_module(name: str, module: str) -> bool:
    return name == module or name.startswith(f"{module}.")


def test_import_scanner_resolves_relative_imports() -> None:
    assert "hamsterdan2.workflow" in imports_from("from ..workflow import values", "hamsterdan2.readiness")


def test_packages_do_not_reexport_children_or_offer_facades() -> None:
    for path in PACKAGE_INITIALIZERS:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path.relative_to(ROOT)))
        imports = [node for node in ast.walk(tree) if isinstance(node, ast.Import | ast.ImportFrom)]
        assignments = [
            node
            for node in tree.body
            if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name) and node.target.id == "__all__"
        ]
        assert imports == [], f"{path.relative_to(ROOT)} reexports a child"
        assert len(assignments) == 1
        assignment = assignments[0]
        assert assignment.value is not None
        assert ast.literal_eval(assignment.value) == []


def test_source_import_graph_is_acyclic_and_avoids_package_objects() -> None:
    paths = tuple(SOURCE.rglob("*.py"))
    modules = {module_name(path): path for path in paths}
    package_names = {module_name(path) for path in PACKAGE_INITIALIZERS}
    graph = {module_name(path): {name for name in source_imports(path) if name in modules} for path in paths}
    package_imports = {
        path: sorted(source_imports(path) & package_names) for path in paths if source_imports(path) & package_names
    }

    assert package_imports == {}
    try:
        tuple(TopologicalSorter(graph).static_order())
    except CycleError as error:
        pytest.fail(f"hamsterdan2 import cycle: {error.args}")


def test_only_the_workflow_bridge_imports_the_exact_legacy_allowlist() -> None:
    paths = (*SOURCE.rglob("*.py"), *(ROOT / "tests2").rglob("*.py"))
    legacy_imports = {
        path: {name for name in source_imports(path) if name == "hamsterdan" or name.startswith("hamsterdan.")}
        for path in paths
        if any(name == "hamsterdan" or name.startswith("hamsterdan.") for name in source_imports(path))
    }

    assert legacy_imports == {BRIDGE: LEGACY_ALLOWLIST}


def test_production_never_imports_simulation() -> None:
    for path in SOURCE.rglob("*.py"):
        if "simulation" in path.relative_to(SOURCE).parts:
            continue
        escaped = {
            name
            for name in source_imports(path)
            if name == "hamsterdan2.simulation"
            or name.startswith("hamsterdan2.simulation.")
            or ".simulation." in name
            or name.endswith(".simulation")
        }
        assert escaped == set(), f"{path.relative_to(ROOT)} imports simulation: {sorted(escaped)}"


def test_workflow_values_have_no_runtime_or_outer_dependencies() -> None:
    forbidden = (
        "hamsterdan2.github_app",
        "hamsterdan2.host",
        "hamsterdan2.readiness",
        "hamsterdan2.simulation",
        "petrus",
        "pathlib",
        "sqlite3",
        "fastapi",
        "httpx",
    )
    for path in (SOURCE / "workflow").rglob("*.py"):
        escaped = {name for name in source_imports(path) if any(matches_module(name, prefix) for prefix in forbidden)}
        assert escaped == set(), f"{path.relative_to(ROOT)} imports outer/runtime concepts: {sorted(escaped)}"


def test_github_boundary_has_no_host_workflow_or_runtime_dependencies() -> None:
    forbidden = (
        "hamsterdan2.host",
        "hamsterdan2.readiness",
        "hamsterdan2.workflow",
        "petrus",
        "fastapi",
        "httpx",
        "sqlite3",
    )
    for path in (SOURCE / "github_app").rglob("*.py"):
        if "simulation" in path.relative_to(SOURCE).parts:
            continue
        escaped = {name for name in source_imports(path) if any(matches_module(name, prefix) for prefix in forbidden)}
        assert escaped == set(), f"{path.relative_to(ROOT)} imports outer/runtime concepts: {sorted(escaped)}"


def test_githubkit_is_confined_to_the_webhook_boundary() -> None:
    imports = {
        path: sorted(name for name in source_imports(path) if matches_module(name, "githubkit"))
        for path in SOURCE.rglob("*.py")
        if any(matches_module(name, "githubkit") for name in source_imports(path))
    }

    assert imports == {GITHUB_WEBHOOKS: ["githubkit.webhooks"]}


def test_fastapi_and_webhook_app_construction_stay_at_the_host_http_rim() -> None:
    fastapi_importers = {
        path for path in SOURCE.rglob("*.py") if any(matches_module(name, "fastapi") for name in source_imports(path))
    }
    constructors = []
    composition_calls = []
    for path in SOURCE.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path.relative_to(ROOT)))
        constructors.extend(
            path
            for node in ast.walk(tree)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "FastAPI"
        )
        composition_calls.extend(
            path
            for node in ast.walk(tree)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "create_webhook_app"
        )

    assert fastapi_importers == {HOST_API, HOST_COMPOSITION}
    assert constructors == [HOST_API]
    assert composition_calls == [HOST_COMPOSITION]


def test_webhook_http_rim_cannot_open_workflow_runtime() -> None:
    forbidden = (
        "hamsterdan2.readiness",
        "hamsterdan2.workflow",
        "petrus",
    )
    escaped = {name for name in source_imports(HOST_API) if any(matches_module(name, prefix) for prefix in forbidden)}

    assert escaped == set()


def test_http_acknowledgement_cannot_invoke_staging_bridge_history_or_fold() -> None:
    forbidden_names = {
        "accept_staged_observation",
        "build_observation_acceptance_authority",
        "build_staging_authority",
        "stage",
        "stage_delivery",
        "open_readiness",
        "build_readiness_runtime",
        "accept",
        "fold",
    }
    tree = ast.parse(HOST_API.read_text(encoding="utf-8"), filename=str(HOST_API.relative_to(ROOT)))
    calls = {
        node.func.id for node in ast.walk(tree) if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    } | {
        node.func.attr for node in ast.walk(tree) if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
    }
    assert calls.isdisjoint(forbidden_names)

    composition = ast.parse(
        HOST_COMPOSITION.read_text(encoding="utf-8"),
        filename=str(HOST_COMPOSITION.relative_to(ROOT)),
    )
    webhook_builder = next(
        node for node in composition.body if isinstance(node, ast.FunctionDef) and node.name == "build_webhook_app"
    )
    calls = {
        node.func.id
        for node in ast.walk(webhook_builder)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }
    assert calls == {"GitHubWebhook", "create_webhook_app"}


def test_staging_path_stops_before_bridge_history_fold_and_petrus() -> None:
    forbidden = (
        "hamsterdan2.readiness.runtime",
        "hamsterdan2.readiness.workflow_bridge",
        "hamsterdan",
        "petrus",
    )
    for path in (HOST_APPLICATION, INGRESS, INGRESS_VALUES, PROJECTION, WORKFLOW_OBSERVATIONS):
        escaped = {name for name in source_imports(path) if any(matches_module(name, prefix) for prefix in forbidden)}
        assert escaped == set(), f"{path.relative_to(ROOT)} crosses the task-3 stopping boundary: {sorted(escaped)}"


def test_concrete_staging_authority_construction_stays_in_host_composition() -> None:
    constructors = []
    for path in SOURCE.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path.relative_to(ROOT)))
        constructors.extend(
            path
            for node in ast.walk(tree)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "StagingAuthority"
        )

    assert constructors == [HOST_COMPOSITION]


def test_concrete_history_acceptance_authority_construction_stays_in_host_composition() -> None:
    constructors = []
    for path in SOURCE.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path.relative_to(ROOT)))
        constructors.extend(
            path
            for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "ObservationAcceptanceAuthority"
        )

    assert constructors == [HOST_COMPOSITION]


def test_process_loss_evidence_drives_the_composed_asgi_boundary() -> None:
    imports = source_imports(PROCESS_SIMULATION)
    tree = ast.parse(
        PROCESS_SIMULATION.read_text(encoding="utf-8"),
        filename=str(PROCESS_SIMULATION.relative_to(ROOT)),
    )
    calls = {node.func.id for node in ast.walk(tree) if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)}

    assert "hamsterdan2.host.composition" in imports
    assert "build_webhook_app" in calls
    assert "hamsterdan2.host.delivery" not in imports
    assert "hamsterdan2.github_app.webhooks" not in imports


def test_readiness_runtime_alone_owns_engine_history_and_dispatch() -> None:
    runtime_modules = (
        "petrus.engine",
        "petrus.impetus.history_store",
        "petrus.impetus.instance",
        "petrus.motus.dispatch",
    )
    escaped = {
        path: sorted(
            name for name in source_imports(path) if any(matches_module(name, module) for module in runtime_modules)
        )
        for path in SOURCE.rglob("*.py")
        if path != RUNTIME
        and "simulation" not in path.relative_to(SOURCE).parts
        and any(matches_module(name, module) for name in source_imports(path) for module in runtime_modules)
    }

    assert escaped == {}
    assert {
        name for name in source_imports(RUNTIME) if any(matches_module(name, module) for module in runtime_modules)
    } == {
        "petrus.engine",
        "petrus.engine.sqlite",
        "petrus.impetus.instance",
        "petrus.motus.dispatch",
    }
    tree = ast.parse(RUNTIME.read_text(encoding="utf-8"), filename=str(RUNTIME.relative_to(ROOT)))
    fenced_constructors = {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module == "petrus.engine.sqlite"
        for alias in node.names
    }
    calls = {node.func.id for node in ast.walk(tree) if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)}
    assert fenced_constructors == {"create_engine", "load_engine"}
    assert fenced_constructors <= calls


def petrus_acceptance_usage(
    paths: tuple[Path, ...],
) -> tuple[dict[Path, list[str]], dict[Path, list[str]], dict[Path, int]]:
    trees = {path: ast.parse(path.read_text(encoding="utf-8"), filename=str(path.relative_to(ROOT))) for path in paths}
    calls = {
        path: [
            node.func.attr
            for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr in {"accept_delivery", "complete_delivery", "deliver", "advance"}
        ]
        for path, tree in trees.items()
    }
    private_accesses = {
        path: [node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute) and node.attr == "_instance"]
        for path, tree in trees.items()
    }
    private_instance_names = {
        path: sum(isinstance(node, ast.Name) and node.id == "Instance" for node in ast.walk(tree))
        for path, tree in trees.items()
    }
    return (
        {path: values for path, values in calls.items() if values},
        {path: values for path, values in private_accesses.items() if values},
        {path: count for path, count in private_instance_names.items() if count},
    )


def test_history_acceptance_uses_only_the_identified_public_petrus_cut() -> None:
    paths = tuple(path for path in SOURCE.rglob("*.py") if "simulation" not in path.relative_to(SOURCE).parts)
    calls, private_accesses, private_instance_names = petrus_acceptance_usage(paths)

    assert calls == {RUNTIME: ["accept_delivery"]}
    assert private_accesses == {}
    assert private_instance_names == {}


def test_history_is_the_only_workflow_admission_ledger() -> None:
    schema_paths = (SOURCE / "host" / "catalog.py", INGRESS)
    for path in schema_paths:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path.relative_to(ROOT)))
        schemas = [
            ast.literal_eval(node.value)
            for node in tree.body
            if isinstance(node, ast.Assign)
            and any(isinstance(target, ast.Name) and target.id == "SCHEMA" for target in node.targets)
        ]
        assert len(schemas) == 1
        normalized = schemas[0].lower()
        assert "history_accept" not in normalized
        assert "accepted_delivery" not in normalized
        assert "admission_pointer" not in normalized


def test_simulation_is_the_only_petrus_testing_consumer() -> None:
    for path in SOURCE.rglob("*.py"):
        imports_testing = any(matches_module(name, "petrus.testing") for name in source_imports(path))
        assert not imports_testing or "simulation" in path.relative_to(SOURCE).parts, (
            f"{path.relative_to(ROOT)} imports Petrus testing mechanics outside simulation"
        )


def test_ds1_constructs_no_worker_or_worker_dispatch() -> None:
    forbidden = ("petrus.motus.worker", "petrus.motus.worker_dispatch")
    imported = {
        path: sorted(name for name in source_imports(path) if any(matches_module(name, module) for module in forbidden))
        for path in SOURCE.rglob("*.py")
        if any(matches_module(name, module) for name in source_imports(path) for module in forbidden)
    }

    assert imported == {}


def test_concrete_hamsterdan_construction_stays_in_host_composition() -> None:
    constructors = []
    for path in SOURCE.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path.relative_to(ROOT)))
        constructors.extend(
            path
            for node in ast.walk(tree)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "Hamsterdan"
        )

    assert constructors == [SOURCE / "host" / "composition.py"]
