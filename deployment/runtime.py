#!/usr/bin/env python3
"""Provision and validate an inactive Hamsterdan runtime on exe.dev."""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from collections.abc import Iterator, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from deployment import deploy, exe_access, exe_vm, release
from hamsterdan.github_app.config import ConfigurationError, installation_accounts

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INSTALLATIONS = ROOT / "deployment" / "config" / "installations.toml"
MAX_SECRET_BYTES = 64 * 1024
_ENVIRONMENT_ID = re.compile(r"[a-z0-9]{26}")
_STRIPPED_ENVIRONMENT_PREFIXES = (
    "AMP_",
    "ANTHROPIC_",
    "EXE_DEV_",
    "HAMSTERDAN_",
    "GH_",
    "GITHUB_",
    "OP_",
    "OPENAI_",
    "OPENROUTER_",
    "PETRUS_",
)


class RuntimeDeploymentError(RuntimeError):
    """A bounded runtime provisioning failure that contains no authority value."""


def _required(environment: Mapping[str, str], name: str, label: str) -> str:
    value = environment.get(name)
    if value is None or not value:
        raise RuntimeDeploymentError(f"{label} is missing")
    return value


def _matches(environment: Mapping[str, str], name: str, label: str, pattern: re.Pattern[str]) -> str:
    value = environment.get(name)
    if value is None or pattern.fullmatch(value) is None:
        raise RuntimeDeploymentError(f"{label} is malformed")
    return value


def _secret(environment: Mapping[str, str], name: str, label: str) -> str:
    value = _required(environment, name, label)
    try:
        encoded = value.encode("utf-8")
    except UnicodeEncodeError:
        raise RuntimeDeploymentError(f"{label} is malformed") from None
    if not 0 < len(encoded) <= MAX_SECRET_BYTES or b"\x00" in encoded or not value.strip():
        raise RuntimeDeploymentError(f"{label} is malformed")
    return value


@dataclass(frozen=True)
class InstallationConfiguration:
    account_count: int
    repository_count: int
    content: str = field(repr=False)

    @classmethod
    def from_file(cls, path: Path) -> InstallationConfiguration:
        try:
            accounts = installation_accounts(path)
            content = path.read_text(encoding="utf-8")
        except (ConfigurationError, OSError, UnicodeError) as error:
            raise RuntimeDeploymentError("installation configuration is unavailable or malformed") from error
        return cls(len(accounts), sum(len(account.repositories) for account in accounts), content)


@dataclass(frozen=True)
class RuntimeConfig:
    environment_id: str
    installations: InstallationConfiguration
    op_token: str = field(repr=False)

    @classmethod
    def from_environment(
        cls,
        environment: Mapping[str, str] | None = None,
        *,
        installations_path: Path = DEFAULT_INSTALLATIONS,
    ) -> RuntimeConfig:
        values = os.environ if environment is None else environment
        return cls(
            environment_id=_matches(values, "HAMSTERDAN_ENVIRONMENT_ID", "application Environment id", _ENVIRONMENT_ID),
            installations=InstallationConfiguration.from_file(installations_path),
            op_token=_secret(values, "OP_SERVICE_ACCOUNT_TOKEN_VPS", "target secret-provider authority"),
        )


@dataclass(frozen=True)
class RuntimeFiles:
    installations: Path
    op_token: Path


def _write_private(path: Path, value: str) -> None:
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", closefd=False) as stream:
            stream.write(value)
            stream.flush()
            os.fsync(descriptor)
    finally:
        os.close(descriptor)


@contextmanager
def materialized_runtime(config: RuntimeConfig, *, parent: Path | None = None) -> Iterator[RuntimeFiles]:
    root = Path(tempfile.mkdtemp(prefix="hamsterdan-runtime-", dir=parent))
    root.chmod(0o700)
    files = RuntimeFiles(
        installations=root / "installations.toml",
        op_token=root / "op-token",
    )
    try:
        _write_private(files.installations, config.installations.content)
        _write_private(files.op_token, config.op_token)
        yield files
    finally:
        shutil.rmtree(root)


def ansible_invocation(
    *,
    candidate: deploy.Candidate,
    config: RuntimeConfig,
    files: RuntimeFiles,
    access: exe_access.Access,
) -> tuple[tuple[str, ...], dict[str, object]]:
    variables: dict[str, object] = {
        "candidate_image_id": candidate.image_id,
        "candidate_revision": candidate.revision,
        "runtime_installations": str(files.installations),
        "runtime_op_token": str(files.op_token),
        "runtime_environment_id": config.environment_id,
        "expected_installation_count": config.installations.account_count,
        "expected_repository_count": config.installations.repository_count,
    }
    command = (
        "ansible-playbook",
        "--inventory",
        f"{access.ssh_host},",
        "--user",
        "exedev",
        "--private-key",
        str(access.private_key),
        "--ssh-common-args",
        access.ssh_common_args,
        "--extra-vars",
        json.dumps(variables, separators=(",", ":"), sort_keys=True),
        "deployment/ansible/runtime.yml",
    )
    return command, variables


def configuration_invocation(
    *,
    config: InstallationConfiguration,
    path: Path,
    access: exe_access.Access,
) -> tuple[tuple[str, ...], dict[str, object]]:
    variables: dict[str, object] = {
        "runtime_installations": str(path),
        "expected_installation_count": config.account_count,
        "expected_repository_count": config.repository_count,
    }
    command = (
        "ansible-playbook",
        "--inventory",
        f"{access.ssh_host},",
        "--user",
        "exedev",
        "--private-key",
        str(access.private_key),
        "--ssh-common-args",
        access.ssh_common_args,
        "--extra-vars",
        json.dumps(variables, separators=(",", ":"), sort_keys=True),
        "deployment/ansible/configure.yml",
    )
    return command, variables


def ansible_environment(environment: Mapping[str, str] | None = None) -> dict[str, str]:
    source = os.environ if environment is None else environment
    values = {name: value for name, value in source.items() if not name.startswith(_STRIPPED_ENVIRONMENT_PREFIXES)}
    values.update(
        {
            "ANSIBLE_HOST_KEY_CHECKING": "True",
            "ANSIBLE_NOCOLOR": "1",
            "ANSIBLE_RETRY_FILES_ENABLED": "False",
        }
    )
    return values


def run_ansible(command: Sequence[str]) -> None:
    if shutil.which("ansible-playbook") is None:
        raise RuntimeDeploymentError("ansible-playbook is required; run uv sync --frozen")
    try:
        subprocess.run(command, cwd=ROOT, env=ansible_environment(), check=True, text=True)
    except (OSError, subprocess.CalledProcessError) as error:
        raise RuntimeDeploymentError("runtime operation playbook failed") from error


def provision(manifest: Path, installations: Path, *, confirm_create: str | None) -> deploy.Candidate:
    config = RuntimeConfig.from_environment(installations_path=installations)
    candidate = deploy.read_candidate(manifest)
    exe_vm.ensure_vm(exe_vm.DEFAULT_SPEC, confirm_create=confirm_create)
    vm = exe_vm.wait_for_running_vm(exe_vm.DEFAULT_SPEC)
    try:
        with (
            materialized_runtime(config) as files,
            exe_access.temporary_access(vm.ssh_host) as access,
        ):
            exe_access.wait_for_ssh(access)
            command, _ = ansible_invocation(candidate=candidate, config=config, files=files, access=access)
            run_ansible(command)
    except (exe_access.AccessError, exe_vm.ExeError) as error:
        raise RuntimeDeploymentError(str(error)) from error
    return candidate


def configure(installations: Path) -> InstallationConfiguration:
    config = InstallationConfiguration.from_file(installations)
    vm = exe_vm.wait_for_running_vm(exe_vm.DEFAULT_SPEC)
    try:
        with (
            materialized_installations(config) as path,
            exe_access.temporary_access(vm.ssh_host) as access,
        ):
            exe_access.wait_for_ssh(access)
            command, _ = configuration_invocation(config=config, path=path, access=access)
            run_ansible(command)
    except (exe_access.AccessError, exe_vm.ExeError) as error:
        raise RuntimeDeploymentError(str(error)) from error
    return config


@contextmanager
def materialized_installations(config: InstallationConfiguration, *, parent: Path | None = None) -> Iterator[Path]:
    root = Path(tempfile.mkdtemp(prefix="hamsterdan-installations-", dir=parent))
    root.chmod(0o700)
    path = root / "installations.toml"
    try:
        _write_private(path, config.content)
        yield path
    finally:
        shutil.rmtree(root)


def parser() -> argparse.ArgumentParser:
    value = argparse.ArgumentParser(description=__doc__)
    commands = value.add_subparsers(dest="command", required=True)
    provision_command = commands.add_parser("provision", help="provision inactive runtime custody")
    provision_command.add_argument("--manifest", type=Path, required=True)
    provision_command.add_argument("--file", type=Path, default=DEFAULT_INSTALLATIONS)
    provision_command.add_argument("--confirm-create", help="exact VM name required before creation")
    configure_command = commands.add_parser("configure", help="apply installation configuration without redeploying")
    configure_command.add_argument("--file", type=Path, default=DEFAULT_INSTALLATIONS)
    return value


def main() -> int:
    arguments = parser().parse_args()
    try:
        if arguments.command == "provision":
            candidate = provision(arguments.manifest, arguments.file, confirm_create=arguments.confirm_create)
            print(f"validated inactive runtime for {candidate.image} on {exe_vm.DEFAULT_SPEC.name}")
        else:
            config = configure(arguments.file)
            print(
                f"applied {config.account_count} installation accounts and {config.repository_count} repositories "
                f"on {exe_vm.DEFAULT_SPEC.name}"
            )
        return 0
    except (RuntimeDeploymentError, deploy.DeploymentError, exe_vm.ExeError, release.ReleaseError) as error:
        print(f"runtime operation refused: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
