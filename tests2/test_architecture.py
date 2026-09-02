# Copyright (c) 2026 Henrique Bastos

"""Architecture boundaries for the glossary-aligned CV21 Intake flow."""

from __future__ import annotations

import ast
from graphlib import CycleError, TopologicalSorter
import importlib.util
from pathlib import Path

from hamsterdan2.host.database import APPLICATION_TABLES, SCHEMA
from hamsterdan2.workflow.observations import HeadObservation

import pytest


ROOT = Path(__file__).parents[1]
SOURCE = ROOT / "src" / "hamsterdan2"
BRIDGE = SOURCE / "readiness" / "workflow_bridge.py"
RUNTIME = SOURCE / "readiness" / "runtime.py"
GITHUB_WEBHOOKS = SOURCE / "github_app" / "webhooks.py"
HOST_API = SOURCE / "host" / "api.py"
HOST_APPLICATION = SOURCE / "host" / "application.py"
HOST_COMPOSITION = SOURCE / "host" / "composition.py"
LEGACY_ALLOWLIST = frozenset(
    {
        "hamsterdan.contracts.readiness_v5",
        "hamsterdan.readiness.net_v5.gating",
        "hamsterdan.readiness.net_v5.topology",
    }
)


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


def calls_in(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path.relative_to(ROOT)))
    return [
        node.func.id if isinstance(node.func, ast.Name) else node.func.attr
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name | ast.Attribute)
    ]


def test_packages_do_not_reexport_children_or_offer_facades() -> None:
    for path in SOURCE.rglob("__init__.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path.relative_to(ROOT)))
        imports = [node for node in ast.walk(tree) if isinstance(node, ast.Import | ast.ImportFrom)]
        exports = [
            ast.literal_eval(node.value)
            for node in tree.body
            if isinstance(node, ast.AnnAssign)
            and isinstance(node.target, ast.Name)
            and node.target.id == "__all__"
            and node.value is not None
        ]
        assert imports == []
        assert exports == [[]]


def test_source_import_graph_is_acyclic_and_avoids_package_objects() -> None:
    paths = tuple(SOURCE.rglob("*.py"))
    modules = {module_name(path): path for path in paths}
    package_names = {module_name(path) for path in SOURCE.rglob("__init__.py")}
    graph = {module_name(path): {name for name in source_imports(path) if name in modules} for path in paths}
    package_importers = {
        path.relative_to(ROOT): sorted(source_imports(path) & package_names)
        for path in paths
        if source_imports(path) & package_names
    }

    assert package_importers == {}
    try:
        tuple(TopologicalSorter(graph).static_order())
    except CycleError as error:
        pytest.fail(f"hamsterdan2 import cycle: {error.args}")


def test_only_the_workflow_bridge_imports_current_hamsterdan_code() -> None:
    paths = (*SOURCE.rglob("*.py"), *(ROOT / "tests2").rglob("*.py"))
    legacy = {
        path: {name for name in source_imports(path) if matches_module(name, "hamsterdan")}
        for path in paths
        if any(matches_module(name, "hamsterdan") for name in source_imports(path))
    }

    assert legacy == {BRIDGE: LEGACY_ALLOWLIST}


def test_inner_workflow_and_github_boundaries_have_no_outer_runtime_dependencies() -> None:
    workflow_forbidden = ("hamsterdan2.github_app", "hamsterdan2.host", "hamsterdan2.readiness", "petrus", "sqlite3")
    github_forbidden = ("hamsterdan2.host", "hamsterdan2.readiness", "hamsterdan2.workflow", "petrus", "sqlite3")
    for path in (SOURCE / "workflow").rglob("*.py"):
        assert not {
            name for name in source_imports(path) if any(matches_module(name, item) for item in workflow_forbidden)
        }
    for path in (SOURCE / "github_app").rglob("*.py"):
        assert not {
            name for name in source_imports(path) if any(matches_module(name, item) for item in github_forbidden)
        }


def test_framework_boundaries_are_confined_to_their_owners() -> None:
    githubkit = {
        path: sorted(name for name in source_imports(path) if matches_module(name, "githubkit"))
        for path in SOURCE.rglob("*.py")
        if any(matches_module(name, "githubkit") for name in source_imports(path))
    }
    fastapi = {
        path for path in SOURCE.rglob("*.py") if any(matches_module(name, "fastapi") for name in source_imports(path))
    }

    assert githubkit == {GITHUB_WEBHOOKS: ["githubkit.webhooks"]}
    assert fastapi == {HOST_API, HOST_COMPOSITION}


def test_http_stops_at_verification_and_inbox_storage() -> None:
    forbidden_imports = ("hamsterdan2.readiness", "hamsterdan2.workflow", "petrus")
    assert not {
        name for name in source_imports(HOST_API) if any(matches_module(name, item) for item in forbidden_imports)
    }
    assert set(calls_in(HOST_API)).isdisjoint(
        {
            "process_delivery",
            "authorization_for",
            "accept_delivery",
            "complete_delivery",
            "build_readiness_runtime",
        }
    )

    tree = ast.parse(GITHUB_WEBHOOKS.read_text(encoding="utf-8"), filename=str(GITHUB_WEBHOOKS.relative_to(ROOT)))
    verify_method = next(node for node in ast.walk(tree) if isinstance(node, ast.FunctionDef) and node.name == "verify")
    verify_calls = {
        node.func.id
        for node in ast.walk(verify_method)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }
    assert "parse_envelope" not in verify_calls


def test_webhook_inbox_worker_is_host_owned_and_not_a_motus_worker() -> None:
    imports = source_imports(HOST_APPLICATION)
    tree = ast.parse(HOST_APPLICATION.read_text(encoding="utf-8"), filename=str(HOST_APPLICATION.relative_to(ROOT)))
    worker = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == "WebhookInboxWorker")

    assert worker.bases == []
    assert not any(matches_module(name, "petrus.motus.worker") for name in imports)


def test_concrete_application_construction_stays_in_host_composition() -> None:
    owners: dict[str, list[Path]] = {name: [] for name in ("Hamsterdan", "WebhookInboxWorker", "PullRequestAuthority")}
    for path in SOURCE.rglob("*.py"):
        called = calls_in(path)
        for name, paths in owners.items():
            if name in called:
                paths.append(path)

    assert owners == {
        "Hamsterdan": [HOST_COMPOSITION],
        "WebhookInboxWorker": [HOST_COMPOSITION],
        "PullRequestAuthority": [HOST_COMPOSITION],
    }


def test_application_storage_has_exactly_two_tables_and_no_downstream_completion_ledger() -> None:
    lowered = SCHEMA.lower()

    assert {"pr_workflows", "webhook_inbox"} == APPLICATION_TABLES
    assert lowered.count("create table if not exists") == 2
    assert "manifest" not in lowered
    assert "grant" not in lowered
    assert "staging" not in lowered
    assert "completion" not in lowered
    assert "dispatch" not in lowered


def test_composition_names_exactly_three_shared_sqlite_files() -> None:
    sqlite_names = {
        node.value
        for node in ast.walk(
            ast.parse(
                HOST_COMPOSITION.read_text(encoding="utf-8"),
                filename=str(HOST_COMPOSITION.relative_to(ROOT)),
            )
        )
        if isinstance(node, ast.Constant) and isinstance(node.value, str) and node.value.endswith(".sqlite3")
    }
    all_sqlite_names = {
        node.value
        for path in SOURCE.rglob("*.py")
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"), filename=str(path.relative_to(ROOT))))
        if isinstance(node, ast.Constant) and isinstance(node.value, str) and node.value.endswith(".sqlite3")
    }

    assert sqlite_names == {"hamsterdan.sqlite3", "history.sqlite3", "dispatch.sqlite3"}
    assert all_sqlite_names == sqlite_names


def test_only_readiness_runtime_calls_public_petrus_delivery_phases() -> None:
    phase_calls = {
        path: [
            name for name in calls_in(path) if name in {"accept_delivery", "complete_delivery", "deliver", "advance"}
        ]
        for path in SOURCE.rglob("*.py")
    }
    phase_calls = {path: calls for path, calls in phase_calls.items() if calls}

    assert {path: sorted(calls) for path, calls in phase_calls.items()} == {
        RUNTIME: ["accept_delivery", "accept_delivery", "complete_delivery"]
    }


def test_observation_semantics_exclude_transport_policy_and_provider_time() -> None:
    assert set(HeadObservation.model_fields) == {
        "version",
        "family",
        "pr_identity",
        "generation",
        "head",
        "base",
        "lifecycle_state",
        "draft",
        "merged",
        "mergeable",
    }
