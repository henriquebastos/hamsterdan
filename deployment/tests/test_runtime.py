from __future__ import annotations

import stat
from pathlib import Path

import pytest

from deployment import deploy, exe_access, runtime


def environment() -> dict[str, str]:
    return {
        "ANTHROPIC_AGENT_API_KEY": "anthropic-agent-key-canary",
        "ANTHROPIC_API_KEY": "personal-key-must-not-win",
        "GITHUB_APP_ID": "17",
        "GITHUB_APP_PRIVATE_KEY_PEM": "private-key-canary",
        "GITHUB_APP_SLUG": "hamster-dan",
        "GITHUB_APP_WEBHOOK_SECRET": "webhook-secret-canary",
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
    for name in ("GITHUB_APP_PRIVATE_KEY_PEM", "GITHUB_APP_WEBHOOK_SECRET"):
        values.pop(name)

    config = runtime.RuntimeConfig.from_environment(values, installations_path=source)

    assert config.provider == "anthropic"
    assert config.model == "claude-sonnet-4-5"
    assert config.agent_key == "anthropic-agent-key-canary"
    assert config.op_token == "target-provider-token-canary"
    assert config.installations.account_count == 1
    assert config.installations.repository_count == 1
    assert "target-provider-token-canary" not in repr(config)
    assert "anthropic-agent-key-canary" not in repr(config)


def test_runtime_configuration_refuses_an_agent_key_the_boot_template_will_not_use(tmp_path: Path) -> None:
    values = environment()
    for name in ("ANTHROPIC_AGENT_API_KEY", "ANTHROPIC_API_KEY"):
        values.pop(name)
    values["OPENAI_AGENT_API_KEY"] = "openai-agent-key-canary"

    with pytest.raises(runtime.RuntimeDeploymentError, match="does not match the runtime environment template"):
        runtime.RuntimeConfig.from_environment(values, installations_path=installations(tmp_path))


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
        assert files.agent_key.read_text() == "anthropic-agent-key-canary"
        assert files.op_token.read_text() == "target-provider-token-canary"
        assert sorted(path.name for path in root.iterdir()) == ["agent-api-key", "installations.toml", "op-token"]
        for path in (files.installations, files.agent_key, files.op_token):
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
    assert variables["runtime_op_token"] == str(files.op_token)
    rendered = repr((command, variables))
    for secret in (
        "private-key-canary",
        "webhook-secret-canary",
        "anthropic-agent-key-canary",
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
        name.startswith(("AMP_", "ANTHROPIC_", "EXE_DEV_", "GH_", "GITHUB_", "OP_", "OPENAI_", "OPENROUTER_"))
        for name in sanitized
    )


def test_runtime_playbook_installs_an_inactive_exact_image_service_and_validates() -> None:
    root = Path(__file__).parents[2]
    playbook = (root / "deployment" / "ansible" / "runtime.yml").read_text()
    configuration = (root / "deployment" / "ansible" / "configure.yml").read_text()
    custody = (root / "deployment" / "ansible" / "vars" / "runtime-custody.yml").read_text()
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
    assert "runtime_op_token_file: /etc/hamsterdan/op-token" in custody
    assert "runtime_environment_template: /etc/hamsterdan/env-prod.tpl" in custody
    assert "runtime_vault: hamsterdan-prod" in custody
    assert "op_version: 2.35.0" in custody
    assert "op_archive_sha256: 4457ade59850b852c64c77164235b34dd0b984ef7826eb0ccd32f1fd78a2ceb7" in custody
    assert "vars_files:\n    - vars/runtime-custody.yml" in playbook
    assert "vars_files:\n    - vars/runtime-custody.yml" in configuration
    assert 'checksum: "sha256:{{ op_archive_sha256 }}"' in playbook
    assert "op_installed.stdout == op_version" in playbook
    assert 'src: "{{ playbook_dir }}/../../env-prod.tpl"' in playbook
    assert "Publish the validated runtime environment atomically" not in playbook
    assert "Remove throwaway validation secret custody" in playbook
    assert "runtime_image_identity" in configuration
    assert "isolated validation state" in configuration
    assert "Publish the validated installation configuration atomically" in configuration
    assert "configuration_publication.changed and service_before.stdout == 'active'" in configuration
    assert "current configuration and service are unchanged" in configuration
    assert "ansible_python_interpreter: /usr/bin/python3" in configuration
    assert "/etc/hamsterdan/hamsterdan.env" not in configuration
    assert "Render the throwaway validation environment from the installed template" in configuration
    assert "Remove throwaway validation secret custody" in configuration
    assert '--env-file\n              - "{{ staged_config.path }}/hamsterdan.env"' in configuration
    assert "source={{ validation_secrets.path }},target=/run/secrets/hamsterdan,readonly" in configuration
    assert "127.0.0.1:8000:8000" in unit
    assert "{{ candidate_image_id }}" in unit
    assert "--pull=never" in unit
    assert "--read-only" in unit
    assert "--cap-drop=ALL" in unit
    assert "--security-opt=no-new-privileges" in unit
    assert "/etc/hamsterdan/config,target=/run/config/hamsterdan,readonly" in unit
    assert "serve --host 0.0.0.0 --port 8000" in unit
    assert "WantedBy=multi-user.target" in unit


def test_service_start_resolves_every_boot_rendered_credential_without_exposing_the_token() -> None:
    root = Path(__file__).parents[2]
    unit = (root / "deployment" / "ansible" / "templates" / "hamsterdan.service.j2").read_text()
    pre_start = [line for line in unit.splitlines() if line.startswith("ExecStartPre=")]

    assert len(pre_start) == 4
    assert pre_start[0] == "ExecStartPre=-/usr/bin/docker rm hamsterdan"
    for line in pre_start[1:]:
        assert line.startswith("ExecStartPre=/bin/sh -ec 'OP_SERVICE_ACCOUNT_TOKEN=`cat {{ runtime_op_token_file }}`;")
        assert "{{ op_command }}" in line
    assert "inject --force --file-mode 0600 --in-file {{ runtime_root }}/env-prod.tpl" in pre_start[1]
    assert "--out-file {{ runtime_root }}/hamsterdan.env" in pre_start[1]
    assert "document get github-app.pem --vault {{ runtime_vault }}" in pre_start[2]
    assert "--out-file {{ runtime_secrets }}/github-app.pem" in pre_start[2]
    assert "read --no-newline" in pre_start[3]
    assert "op://{{ runtime_vault }}/github-app/webhook_secret" in pre_start[3]
    assert unit.index("ExecStartPre") < unit.index("ExecStart=/usr/bin/docker run")


def test_runtime_environment_template_resolves_app_identity_and_carries_no_secret_value() -> None:
    root = Path(__file__).parents[2]
    template = (root / "env-prod.tpl").read_text()
    assignments = [line for line in template.splitlines() if line and not line.startswith("#")]

    assert [line.split("=", 1)[0] for line in assignments] == [
        "HAMSTERDAN_GITHUB_APP_ID",
        "HAMSTERDAN_GITHUB_APP_SLUG",
        "HAMSTERDAN_GITHUB_CLIENT_ID",
        "HAMSTERDAN_GITHUB_INSTALLATIONS_FILE",
        "HAMSTERDAN_STATE_PATH",
        "HAMSTERDAN_GITHUB_PRIVATE_KEY_FILE",
        "HAMSTERDAN_GITHUB_WEBHOOK_SECRET_FILE",
        "HAMSTERDAN_PI_PROVIDER",
        "HAMSTERDAN_PI_MODEL",
        "HAMSTERDAN_PI_API_KEY_FILE",
        "HAMSTERDAN_WORKFLOW_PATH",
        "HAMSTERDAN_REMINDER_SECONDS",
    ]
    references = [line.split("=", 1)[1] for line in assignments if "op://" in line]
    assert references == [
        "{{ op://hamsterdan-prod/github-app/app_id }}",
        "{{ op://hamsterdan-prod/github-app/slug }}",
        "{{ op://hamsterdan-prod/github-app/client_id }}",
    ]
    assert "HAMSTERDAN_GITHUB_PRIVATE_KEY_FILE=/run/secrets/hamsterdan/github-app.pem" in assignments
    assert "HAMSTERDAN_GITHUB_WEBHOOK_SECRET_FILE=/run/secrets/hamsterdan/webhook-secret" in assignments
    assert "HAMSTERDAN_PI_API_KEY_FILE=/run/secrets/hamsterdan/agent-api-key" in assignments
    assert "HAMSTERDAN_PI_PROVIDER=anthropic" in assignments
    assert "HAMSTERDAN_PI_MODEL=claude-sonnet-4-5" in assignments
    assert "HAMSTERDAN_WORKFLOW_PATH=.github/workflows/ci.yml" in assignments
    assert "HAMSTERDAN_REMINDER_SECONDS=259200" in assignments


def test_development_secret_template_is_rendered_by_direnv_from_the_development_vault() -> None:
    root = Path(__file__).parents[2]
    template = (root / "env-dev.tpl").read_text()
    envrc = (root / ".envrc").read_text()
    assignments = [line for line in template.splitlines() if line and not line.startswith("#")]

    assert [line.split("=", 1)[0] for line in assignments] == [
        "AI_MEMORY_AUTH_TOKEN",
        "AMP_API_KEY",
        "CF_ACCESS_CLIENT_ID",
        "CF_ACCESS_CLIENT_SECRET",
        "E2B_API_KEY",
        "GITHUB_HENRIQUEBASTOS_HOSTS",
        "HAMSTERDAN_GITHUB_WORKFLOW_TOKEN",
        "OPENAI_AGENT_API_KEY",
        "OPENAI_API_KEY",
        "OPENROUTER_API_KEY",
        "PETRUS_GITHUB_TOKEN",
    ]
    assert all(line.split("=", 1)[1].startswith('"op://hamsterdan-dev/') for line in assignments)
    assert "op inject --force -i env-dev.tpl -o .env && chmod 600 .env" in envrc
    assert "watch_file env-dev.tpl" in envrc
    assert "dotenv .env" in envrc


def test_deployment_authority_resolves_only_from_the_operations_vault() -> None:
    root = Path(__file__).parents[2]
    template = (root / "env-ops.tpl").read_text()
    launcher = (root / "scripts" / "ops").read_text()
    development = (root / "env-dev.tpl").read_text()
    assignments = [line for line in template.splitlines() if line and not line.startswith("#")]

    assert [line.split("=", 1)[0] for line in assignments] == [
        "ANTHROPIC_AGENT_API_KEY",
        "EXE_DEV_API_TOKEN",
        "EXE_DEV_SSH_PRIVATE_KEY_B64",
        "GITHUB_APP_ID",
        "GITHUB_APP_SLUG",
        "OP_SERVICE_ACCOUNT_TOKEN_VPS",
    ]
    assert all(line.split("=", 1)[1].startswith("op://example-ops/") for line in assignments)

    # An agent key is identified by the provider that issued it, so switching
    # providers is a visible item change rather than a silent value swap.
    assert "op://example-ops/anthropic/credential" in template

    # A development sandbox must never hold authority over the production host.
    assert "hamsterdan-ops" not in development
    assert "EXE_DEV" not in development

    # A workstation authenticates personally; only a headless environment
    # substitutes a service account.
    assert 'export OP_SERVICE_ACCOUNT_TOKEN="$OP_SA_HAMSTERDAN_OPS"' in launcher
    assert "unset OP_SERVICE_ACCOUNT_TOKEN" in launcher
    assert 'exec op run --env-file=env-ops.tpl -- "$@"' in launcher
