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
        "READINESS_REMINDER_SECONDS": "259200",
        "READINESS_WORKFLOW_PATH": ".github/workflows/ci.yml",
    }


def installations(tmp_path: Path, *, malformed: bool = False) -> Path:
    path = tmp_path / "installations.toml"
    path.write_text(
        "leak_canary = true\n"
        if malformed
        else """
[[accounts]]
id = 23
login = "HBNetwork"
repositories = ["31:HBNetwork/demo-pr-readiness"]
"""
    )
    path.chmod(0o600)
    return path


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


def test_runtime_configuration_uses_role_authority_and_renders_no_secret_values(tmp_path: Path) -> None:
    config = runtime.RuntimeConfig.from_environment(environment(), installations_path=installations(tmp_path))

    assert config.provider == "anthropic"
    assert config.model == "claude-sonnet-4-5"
    assert config.agent_key == "anthropic-agent-key-canary"
    assert config.installations.account_count == 1
    assert config.installations.repository_count == 1
    rendered = config.render_environment()
    assert "HAMSTERDAN_GITHUB_INSTALLATIONS_FILE=/run/config/hamsterdan/installations.toml" in rendered
    assert "HAMSTERDAN_PI_PROVIDER=anthropic" in rendered
    assert "HAMSTERDAN_PI_MODEL=claude-sonnet-4-5" in rendered
    assert "private-key-canary" not in rendered
    assert "webhook-secret-canary" not in rendered
    assert "anthropic-agent-key-canary" not in rendered
    assert "private-key-canary" not in repr(config)


def test_runtime_configuration_rejects_missing_or_malformed_authority_without_disclosure(tmp_path: Path) -> None:
    values = environment()

    with pytest.raises(runtime.RuntimeDeploymentError, match="installation configuration") as failure:
        runtime.RuntimeConfig.from_environment(values, installations_path=installations(tmp_path, malformed=True))

    assert "leak_canary" not in str(failure.value)

    values = environment()
    for name in ("ANTHROPIC_AGENT_API_KEY", "ANTHROPIC_API_KEY"):
        values.pop(name)
    with pytest.raises(runtime.RuntimeDeploymentError, match="agent provider authority is missing"):
        runtime.RuntimeConfig.from_environment(values, installations_path=installations(tmp_path))


def test_materialized_runtime_is_private_and_removed_after_use(tmp_path: Path) -> None:
    source = installations(tmp_path)
    config = runtime.RuntimeConfig.from_environment(environment(), installations_path=source)

    with runtime.materialized_runtime(config, parent=tmp_path) as files:
        root = files.environment.parent
        assert stat.S_IMODE(root.stat().st_mode) == 0o700
        assert files.environment.read_text() == config.render_environment()
        assert files.installations.read_text() == source.read_text()
        assert files.github_private_key.read_text() == "private-key-canary"
        assert files.webhook_secret.read_text() == "webhook-secret-canary"
        assert files.agent_key.read_text() == "anthropic-agent-key-canary"
        for path in (
            files.environment,
            files.installations,
            files.github_private_key,
            files.webhook_secret,
            files.agent_key,
        ):
            assert stat.S_IMODE(path.stat().st_mode) == 0o600

    assert not root.exists()


def test_runtime_ansible_command_carries_paths_and_public_expectations_not_secrets(tmp_path: Path) -> None:
    config = runtime.RuntimeConfig.from_environment(environment(), installations_path=installations(tmp_path))
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
    assert variables["expected_installation_count"] == 1
    assert variables["expected_repository_count"] == 1
    rendered = repr((command, variables))
    for secret in ("private-key-canary", "webhook-secret-canary", "anthropic-agent-key-canary"):
        assert secret not in rendered


def test_configuration_command_carries_only_the_file_and_expected_counts(tmp_path: Path) -> None:
    config = runtime.InstallationConfiguration.from_file(installations(tmp_path))
    access = exe_access.Access(
        private_key=tmp_path / "id_exe",
        known_hosts=tmp_path / "known_hosts",
        ssh_host="example-vm.exe.xyz",
    )

    with runtime.materialized_installations(config, parent=tmp_path) as path:
        command, variables = runtime.configuration_invocation(config=config, path=path, access=access)
        assert stat.S_IMODE(path.stat().st_mode) == 0o600

    assert command[-1] == "deployment/ansible/configure.yml"
    assert variables == {
        "runtime_installations": str(path),
        "expected_installation_count": 1,
        "expected_repository_count": 1,
    }
    assert not path.exists()


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
    configuration = (root / "deployment" / "ansible" / "configure.yml").read_text()
    unit = (root / "deployment" / "ansible" / "templates" / "hamsterdan.service.j2").read_text()

    assert "candidate_image_id" in playbook
    assert "no_log: true" in playbook
    assert 'mode: "0600"' in playbook
    assert "validate" in playbook
    assert "expected_installation_count" in playbook
    assert "expected_repository_count" in playbook
    assert "enabled: false" in playbook
    assert "systemctl is-active hamsterdan.service" in playbook
    assert "name=^/hamsterdan$" in playbook
    assert "runtime_unit_before.stat.isreg" in playbook
    assert "runtime_image_identity" in playbook
    assert "reconciled_installations" in playbook
    assert "isolated candidate validation state" in playbook
    assert "runtime_image_identity" in configuration
    assert "isolated validation state" in configuration
    assert "Publish the validated installation configuration atomically" in configuration
    assert "configuration_publication.changed and service_before.stdout == 'active'" in configuration
    assert "current configuration and service are unchanged" in configuration
    assert "ansible_python_interpreter: /usr/bin/python3" in configuration
    assert "127.0.0.1:8000:8000" in unit
    assert "{{ candidate_image_id }}" in unit
    assert "--pull=never" in unit
    assert "--read-only" in unit
    assert "--cap-drop=ALL" in unit
    assert "--security-opt=no-new-privileges" in unit
    assert "/etc/hamsterdan/config,target=/run/config/hamsterdan,readonly" in unit
    assert "serve --host 0.0.0.0 --port 8000" in unit
    assert "WantedBy=multi-user.target" in unit
