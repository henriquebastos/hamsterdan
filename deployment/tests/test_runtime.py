from __future__ import annotations

import stat
from pathlib import Path

import pytest

from deployment import deploy, exe_access, runtime


def environment() -> dict[str, str]:
    return {
        "HAMSTERDAN_ENVIRONMENT_ID": "a" * 26,
        "OP_SERVICE_ACCOUNT_TOKEN_VPS": "target-provider-token-canary",
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


def test_runtime_configuration_carries_target_authority_without_app_secret_material(tmp_path: Path) -> None:
    source = installations(tmp_path)
    values = environment()

    config = runtime.RuntimeConfig.from_environment(values, installations_path=source)

    assert config.environment_id == "a" * 26
    assert config.op_token == "target-provider-token-canary"
    assert config.installations.account_count == 1
    assert config.installations.repository_count == 1
    assert "target-provider-token-canary" not in repr(config)
    assert "openai-agent-key-canary" not in repr(config)


@pytest.mark.parametrize("environment_id", ["", "dev,prod", "../prod", "a" * 27])
def test_runtime_configuration_requires_one_explicit_environment(tmp_path: Path, environment_id: str) -> None:
    values = environment()
    values["HAMSTERDAN_ENVIRONMENT_ID"] = environment_id
    with pytest.raises(runtime.RuntimeDeploymentError, match="application Environment id"):
        runtime.RuntimeConfig.from_environment(values, installations_path=installations(tmp_path))


def test_runtime_configuration_rejects_missing_or_malformed_authority_without_disclosure(tmp_path: Path) -> None:
    values = environment()

    with pytest.raises(runtime.RuntimeDeploymentError, match="installation configuration") as failure:
        runtime.RuntimeConfig.from_environment(values, installations_path=installations(tmp_path, malformed=True))

    assert "leak_canary" not in str(failure.value)

    values = environment()
    values.pop("OP_SERVICE_ACCOUNT_TOKEN_VPS")
    with pytest.raises(runtime.RuntimeDeploymentError, match="target secret-provider authority is missing"):
        runtime.RuntimeConfig.from_environment(values, installations_path=installations(tmp_path))


def test_materialized_runtime_is_private_and_removed_after_use(tmp_path: Path) -> None:
    source = installations(tmp_path)
    config = runtime.RuntimeConfig.from_environment(environment(), installations_path=source)

    with runtime.materialized_runtime(config, parent=tmp_path) as files:
        root = files.installations.parent
        assert stat.S_IMODE(root.stat().st_mode) == 0o700
        assert files.installations.read_text() == source.read_text()
        assert files.op_token.read_text() == "target-provider-token-canary"
        assert sorted(path.name for path in root.iterdir()) == ["installations.toml", "op-token"]
        for path in (files.installations, files.op_token):
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
    assert variables["runtime_environment_id"] == "a" * 26
    assert variables["expected_installation_count"] == 1
    assert variables["expected_repository_count"] == 1
    assert variables["runtime_op_token"] == str(files.op_token)
    rendered = repr((command, variables))
    for secret in (
        "private-key-canary",
        "webhook-secret-canary",
        "openai-agent-key-canary",
        "target-provider-token-canary",
    ):
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
        "OP_SERVICE_ACCOUNT_TOKEN": "operator-provider-token-canary",
        "PATH": "/usr/bin:/bin",
    }

    sanitized = runtime.ansible_environment(values)

    assert sanitized["HOME"] == "/home/operator"
    assert sanitized["PATH"] == "/usr/bin:/bin"
    assert sanitized["ANSIBLE_HOST_KEY_CHECKING"] == "True"
    assert not any(
        name.startswith(
            ("AMP_", "ANTHROPIC_", "EXE_DEV_", "GH_", "GITHUB_", "HAMSTERDAN_", "OP_", "OPENAI_", "OPENROUTER_")
        )
        for name in sanitized
    )


def test_validation_and_service_use_the_same_environment_loader() -> None:
    root = Path(__file__).parents[2]
    unit = (root / "deployment/ansible/templates/hamsterdan.service.j2").read_text()
    for name in ("runtime", "configure"):
        playbook = (root / f"deployment/ansible/{name}.yml").read_text()
        assert "--entrypoint=/opt/hamsterdan/with-runtime-secrets" in playbook
        assert "{{ runtime_environment_file }}" in playbook
        assert "source={{ runtime_op_token_file }},target=/run/secrets/op-token,readonly" in playbook
        assert "source={{ op_command }},target=/usr/local/bin/op,readonly" in playbook
        assert "expected_installation_count" in playbook and "expected_repository_count" in playbook
        assert "op_authority" not in playbook and "agent-api-key" not in playbook
    assert "--entrypoint=/opt/hamsterdan/with-runtime-secrets" in unit
    assert "{{ runtime_environment_file }}" in unit
    assert "--read-only" in unit and "--cap-drop=ALL" in unit
    assert "--security-opt=no-new-privileges" in unit and "127.0.0.1:8000:8000" in unit
    assert "source={{ runtime_op_token_file }},target=/run/secrets/op-token,readonly" in unit
    assert "source={{ op_command }},target=/usr/local/bin/op,readonly" in unit
    assert "{{ candidate_image_id }}" in unit and "--pull=never" in unit
    assert "op inject" not in unit and "hamsterdan.env" not in unit


def test_operations_credentials_remain_separate_from_application_authority() -> None:
    root = Path(__file__).parents[2]
    operations = (root / "env-ops.tpl").read_text()
    provision = (root / "env-provision.tpl").read_text()
    assert "PETRUS_GITHUB_TOKEN" not in operations and "OPENAI" not in operations
    assert "OP_SERVICE_ACCOUNT_TOKEN_VPS" not in operations
    assert "OP_SERVICE_ACCOUNT_TOKEN_VPS=op://example-ops/" in provision
