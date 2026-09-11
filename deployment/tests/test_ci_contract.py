from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).parents[2]


def test_image_workflow_is_a_manual_adapter_over_the_release_command() -> None:
    workflow = (ROOT / ".github" / "workflows" / "image.yml").read_text()

    assert "workflow_dispatch:" in workflow
    assert "docker/setup-buildx-action@v3" in workflow
    assert "1password/load-secrets-action" not in workflow
    assert "OP_SERVICE_ACCOUNT_TOKEN_BUILD" not in workflow
    assert "PETRUS_GITHUB_TOKEN" not in workflow
    assert workflow.count("python deployment/release.py build") == 1
    assert workflow.count("python deployment/release.py verify") == 1
    assert "deployment/release.py publish" not in workflow
    assert "packages: write" not in workflow
