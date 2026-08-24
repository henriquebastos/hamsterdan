from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).parents[2]


def test_build_context_admits_only_declared_image_inputs() -> None:
    dockerignore = (ROOT / ".dockerignore").read_text().splitlines()

    assert dockerignore[0] == "**"
    assert set(dockerignore[1:]) == {
        "!deployment/Containerfile",
        "!deployment/pi/",
        "!deployment/pi/package-lock.json",
        "!deployment/pi/package.json",
        "!pyproject.toml",
        "!README.md",
        "!src/",
        "!src/**",
        "!uv.lock",
    }


def test_container_build_has_pinned_runtime_and_secret_mount() -> None:
    containerfile = (ROOT / "deployment" / "Containerfile").read_text()

    assert containerfile.startswith("# syntax=docker/dockerfile:1.7@sha256:")
    assert containerfile.count("FROM ") >= 2
    assert all("@sha256:" in line for line in containerfile.splitlines() if line.startswith("FROM "))
    assert "--mount=type=secret,id=petrus_github_token" in containerfile
    assert "uv sync --frozen --no-dev" in containerfile
    assert "npm ci" in containerfile
    assert "ARG PETRUS_GITHUB_TOKEN" not in containerfile
    assert "USER hamsterdan" in containerfile
    assert 'ENTRYPOINT ["/opt/hamsterdan/.venv/bin/python", "-m", "hamsterdan.host"]' in containerfile


def test_pi_runtime_is_locked_to_the_qualified_node_and_agent_versions() -> None:
    package = json.loads((ROOT / "deployment" / "pi" / "package.json").read_text())
    lock = json.loads((ROOT / "deployment" / "pi" / "package-lock.json").read_text())

    assert package["dependencies"] == {
        "@earendil-works/pi-coding-agent": "0.83.0",
        "node": "22.19.0",
    }
    assert lock["packages"][""]["dependencies"] == package["dependencies"]
    assert lock["packages"]["node_modules/@earendil-works/pi-coding-agent"]["version"] == "0.83.0"
    assert lock["packages"]["node_modules/node"]["version"] == "22.19.0"
