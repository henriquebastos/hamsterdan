"""Assert host composition and credential isolation boundaries."""

import ast
from dataclasses import fields
from pathlib import Path

from hamsterdan.agents import CodingRequest, ConversationRequest, ReviewRequest
from hamsterdan.host.application import PrReadinessApplication


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


def test_agent_requests_are_credential_free_and_mentions_are_exact() -> None:
    request_fields = {
        field.name.casefold() for kind in (ReviewRequest, ConversationRequest, CodingRequest) for field in fields(kind)
    }
    for forbidden in ("github_token", "installation_token", "private_key", "credential"):
        assert forbidden not in request_fields

    app = object.__new__(PrReadinessApplication)
    app.bot_login = "hamster-dan[bot]"
    assert app._addressed_text("/hamsterdan status") is None
    assert app._addressed_text("@HaMsTeR-DaN please explain") == "please explain"
    assert app._addressed_text("@hamster-dan") == ""
    assert app._addressed_text("@hamsterdan please explain") is None
    assert app._addressed_text("@hamsterdan-other hello") is None
    assert app._addressed_text("/hamsterdangler status") is None
