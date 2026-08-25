from __future__ import annotations

import stat
from pathlib import Path

import pytest

from deployment import deploy, exe_access, runtime


def environment() -> dict[str, str]:
    return {
        "ANTHROPIC_AGENT_API_KEY": "anthropic-agent-key-canary",
        "ANTHROPIC_API_KEY": "personal-key-must-not-win",
        "GITHUB_APP_CLIENT_ID": "Iv1_runtime",
        "GITHUB_APP_ID": "17",
        "GITHUB_APP_PRIVATE_KEY_PEM": "private-key-canary",
        "GITHUB_APP_SLUG": "hamster-dan",
        "GITHUB_APP_WEBHOOK_SECRET": "webhook-secret-canary",
        "GITHUB_INSTALLATION_ACCOUNT_ID": "23",
        "GITHUB_INSTALLATION_ACCOUNT_LOGIN": "HBNetwork",
        "GITHUB_INSTALLATION_REPOSITORIES": "31:HBNetwork/demo-pr-readiness",
        "READINESS_REMINDER_SECONDS": "259200",
        "READINESS_WORKFLOW_PATH": ".github/workflows/ci.yml",
    }


def candidate(tmp_path: Path) -> deploy.Candidate:
    revision = "a" * 40
    manifest = tmp_path / "release.json"
    manifest.write_text(
        "{"
        '"dirty":false,'
        f'"image":"hamsterdan:sha-{revision}",'
        f'"image_digest":"sha256:{"b" * 64}",'
        f'"image_id":"sha256:{"c" * 64}",'
        '"platform":"linux/amd64",'
        f'"source_revision":"{revision}",'
        '"verified":true,'
        '"version":"0.1.0"'
        "}"
    )
    return deploy.read_candidate(manifest)


def test_runtime_configuration_uses_role_authority_and_renders_no_secret_values() -> None:
    config = runtime.RuntimeConfig.from_environment(environment())

    assert config.provider == "anthropic"
    assert config.model == "claude-sonnet-4-5"
    assert config.agent_key == "anthropic-agent-key-canary"
    assert config.repository_count == 1
    rendered = config.render_environment()
    assert "HAMSTERDAN_ALLOWED_REPOSITORIES=31:HBNetwork/demo-pr-readiness" in rendered
    assert "HAMSTERDAN_PI_PROVIDER=anthropic" in rendered
    assert "HAMSTERDAN_PI_MODEL=claude-sonnet-4-5" in rendered
    assert "private-key-canary" not in rendered
    assert "webhook-secret-canary" not in rendered
    assert "anthropic-agent-key-canary" not in rendered
    assert "private-key-canary" not in repr(config)


def test_runtime_configuration_rejects_missing_or_malformed_authority_without_disclosure() -> None:
    values = environment()
    values["GITHUB_INSTALLATION_REPOSITORIES"] = "31:leak-canary"

    with pytest.raises(runtime.RuntimeDeploymentError, match="installation repositories are malformed") as failure:
        runtime.RuntimeConfig.from_environment(values)

    assert "leak-canary" not in str(failure.value)

    values = environment()
    for name in ("ANTHROPIC_AGENT_API_KEY", "ANTHROPIC_API_KEY"):
        values.pop(name)
    with pytest.raises(runtime.RuntimeDeploymentError, match="agent provider authority is missing"):
        runtime.RuntimeConfig.from_environment(values)


def test_materialized_runtime_is_private_and_removed_after_use(tmp_path: Path) -> None:
    config = runtime.RuntimeConfig.from_environment(environment())

    with runtime.materialized_runtime(config, parent=tmp_path) as files:
        root = files.environment.parent
        assert stat.S_IMODE(root.stat().st_mode) == 0o700
        assert files.environment.read_text() == config.render_environment()
        assert files.github_private_key.read_text() == "private-key-canary"
        assert files.webhook_secret.read_text() == "webhook-secret-canary"
        assert files.agent_key.read_text() == "anthropic-agent-key-canary"
        for path in (files.environment, files.github_private_key, files.webhook_secret, files.agent_key):
            assert stat.S_IMODE(path.stat().st_mode) == 0o600

    assert not root.exists()


def test_runtime_ansible_command_carries_paths_and_public_expectations_not_secrets(tmp_path: Path) -> None:
    config = runtime.RuntimeConfig.from_environment(environment())
    selected = candidate(tmp_path)
    access = exe_access.Access(
        private_key=tmp_path / "id_exe",
        known_hosts=tmp_path / "known_hosts",
        ssh_host="example-vm.exe.xyz",
    )

    with runtime.materialized_runtime(config, parent=tmp_path) as files:
        command, variables = runtime.ansible_invocation(
            candidate=selected,
            config=config,
            files=files,
            access=access,
        )

    assert command[-1] == "deployment/ansible/runtime.yml"
    assert variables["candidate_image_id"] == selected.image_id
    assert variables["expected_app_id"] == 17
    assert variables["expected_app_slug"] == "hamster-dan"
    assert variables["expected_repository_count"] == 1
    rendered = repr((command, variables))
    for secret in ("private-key-canary", "webhook-secret-canary", "anthropic-agent-key-canary"):
        assert secret not in rendered


def test_ansible_environment_removes_controller_authority() -> None:
    values = {
        **environment(),
        "AMP_API_KEY": "amp-canary",
        "EXE_DEV_API_TOKEN": "exe-canary",
        "EXE_DEV_SSH_PRIVATE_KEY_B64": "ssh-canary",
        "HOME": "/home/operator",
        "PATH": "/usr/bin:/bin",
    }

    sanitized = runtime.ansible_environment(values)

    assert sanitized["HOME"] == "/home/operator"
    assert sanitized["PATH"] == "/usr/bin:/bin"
    assert sanitized["ANSIBLE_HOST_KEY_CHECKING"] == "True"
    assert not any(
        name.startswith(("AMP_", "ANTHROPIC_", "EXE_DEV_", "GH_", "GITHUB_", "OPENAI_", "OPENROUTER_"))
        for name in sanitized
    )


def test_runtime_playbook_installs_an_inactive_exact_image_service_and_validates() -> None:
    root = Path(__file__).parents[2]
    playbook = (root / "deployment" / "ansible" / "runtime.yml").read_text()
    unit = (root / "deployment" / "ansible" / "templates" / "hamsterdan.service.j2").read_text()

    assert "candidate_image_id" in playbook
    assert "no_log: true" in playbook
    assert 'mode: "0600"' in playbook
    assert "validate" in playbook
    assert "expected_repository_count" in playbook
    assert "enabled: false" in playbook
    assert "systemctl is-active hamsterdan.service" in playbook
    assert "name=^/hamsterdan$" in playbook
    assert "runtime_unit_before.stat.isreg" in playbook
    assert "127.0.0.1:8000:8000" in unit
    assert "{{ candidate_image_id }}" in unit
    assert "--pull=never" in unit
    assert "--read-only" in unit
    assert "--cap-drop=ALL" in unit
    assert "--security-opt=no-new-privileges" in unit
    assert "serve --host 0.0.0.0 --port 8000" in unit
    assert "WantedBy=multi-user.target" in unit
