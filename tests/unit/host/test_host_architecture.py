"""Assert host composition and credential isolation boundaries."""

import ast
from dataclasses import fields
from pathlib import Path

from hamsterdan.agents import CodingRequest, ConversationRequest, ReviewRequest


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    return {node.module or "" for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)} | {
        alias.name for node in ast.walk(tree) if isinstance(node, ast.Import) for alias in node.names
    }


def test_only_host_composes_agent_and_github_siblings() -> None:
    source = Path("src/hamsterdan")
    for sibling in ("agents", "github_app", "readiness"):
        for path in (source / sibling).rglob("*.py"):
            imports = _imports(path)
            assert not any(name.startswith("hamsterdan.host") for name in imports)
            others = {"agents", "github_app", "readiness"} - {sibling}
            assert not any(name.startswith(f"hamsterdan.{other}") for other in others for name in imports)

    imports = set().union(*(_imports(path) for path in (source / "host").glob("*.py")))
    assert {"hamsterdan.agents", "hamsterdan.github_app.gateway", "hamsterdan.readiness.net"} <= imports
    assert not any(name.startswith("examples") for name in imports)

    for path in source.rglob("*.py"):
        if any(name.startswith("petrus.agenticus") for name in _imports(path)):
            assert path.is_relative_to(source / "agents") or path.is_relative_to(source / "host")


def test_agent_requests_are_credential_free() -> None:
    request_fields = {
        field.name.casefold() for kind in (ReviewRequest, ConversationRequest, CodingRequest) for field in fields(kind)
    }
    for forbidden in ("github_token", "installation_token", "private_key", "credential"):
        assert forbidden not in request_fields
