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

ROOT = Path(__file__).resolve().parents[1]
MAX_SECRET_BYTES = 64 * 1024
_CLIENT_ID = re.compile(r"[A-Za-z0-9_-]{1,128}")
_LOGIN = re.compile(r"[A-Za-z0-9-]{1,39}")
_REPOSITORY_NAME = re.compile(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+")
_SLUG = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*")
_WORKFLOW_PATH = re.compile(r"[A-Za-z0-9_./-]+")
_STRIPPED_ENVIRONMENT_PREFIXES = (
    "AMP_",
    "ANTHROPIC_",
    "EXE_DEV_",
    "GH_",
    "GITHUB_",
    "OPENAI_",
    "OPENROUTER_",
    "PETRUS_",
)
_PROVIDERS = (
    ("anthropic", "claude-sonnet-4-5", ("ANTHROPIC_AGENT_API_KEY", "ANTHROPIC_API_KEY")),
    ("openai", "gpt-5.6-sol", ("OPENAI_AGENT_API_KEY", "OPENAI_API_KEY")),
    ("openrouter", "anthropic/claude-sonnet-4.5", ("OPENROUTER_AGENT_API_KEY", "OPENROUTER_API_KEY")),
)


class RuntimeDeploymentError(RuntimeError):
    """A bounded runtime provisioning failure that contains no authority value."""


def _required(environment: Mapping[str, str], name: str, label: str) -> str:
    value = environment.get(name)
    if value is None or not value:
        raise RuntimeDeploymentError(f"{label} is missing")
    return value


def _positive_decimal(environment: Mapping[str, str], name: str, label: str) -> int:
    value = environment.get(name)
    if value is None or not value.isascii() or not value.isdecimal() or value.startswith("0"):
        raise RuntimeDeploymentError(f"{label} is malformed")
    result = int(value)
    if result <= 0:
        raise RuntimeDeploymentError(f"{label} is malformed")
    return result


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


def _provider(environment: Mapping[str, str]) -> tuple[str, str, str]:
    for provider, model, names in _PROVIDERS:
        key = environment.get(names[0]) or environment.get(names[1])
        if key:
            try:
                encoded = key.encode("ascii")
            except UnicodeEncodeError:
                raise RuntimeDeploymentError("agent provider authority is malformed") from None
            if not 16 <= len(encoded) <= 512 or any(byte < 0x21 or byte > 0x7E for byte in encoded):
                raise RuntimeDeploymentError("agent provider authority is malformed")
            return provider, model, key
    raise RuntimeDeploymentError("agent provider authority is missing")


def _repositories(environment: Mapping[str, str]) -> tuple[str, int]:
    raw = environment.get("GITHUB_INSTALLATION_REPOSITORIES")
    if not raw:
        raise RuntimeDeploymentError("installation repositories are missing")
    identifiers: set[int] = set()
    names: set[str] = set()
    for entry in raw.split(","):
        try:
            identifier_text, name = entry.split(":", 1)
        except ValueError:
            raise RuntimeDeploymentError("installation repositories are malformed") from None
        if (
            not identifier_text.isascii()
            or not identifier_text.isdecimal()
            or identifier_text.startswith("0")
            or int(identifier_text) <= 0
            or _REPOSITORY_NAME.fullmatch(name) is None
        ):
            raise RuntimeDeploymentError("installation repositories are malformed")
        identifier = int(identifier_text)
        canonical_name = name.casefold()
        if identifier in identifiers or canonical_name in names:
            raise RuntimeDeploymentError("installation repositories are malformed")
        identifiers.add(identifier)
        names.add(canonical_name)
    return raw, len(identifiers)


@dataclass(frozen=True)
class RuntimeConfig:
    app_id: int
    app_slug: str
    client_id: str
    account_id: int
    account_login: str
    repositories: str
    repository_count: int
    workflow_path: str
    reminder_seconds: int
    provider: str
    model: str
    github_private_key: str = field(repr=False)
    webhook_secret: str = field(repr=False)
    agent_key: str = field(repr=False)

    @classmethod
    def from_environment(cls, environment: Mapping[str, str] | None = None) -> RuntimeConfig:
        values = os.environ if environment is None else environment
        repositories, repository_count = _repositories(values)
        provider, model, agent_key = _provider(values)
        return cls(
            app_id=_positive_decimal(values, "GITHUB_APP_ID", "GitHub App id"),
            app_slug=_matches(values, "GITHUB_APP_SLUG", "GitHub App slug", _SLUG),
            client_id=_matches(values, "GITHUB_APP_CLIENT_ID", "GitHub App client id", _CLIENT_ID),
            account_id=_positive_decimal(values, "GITHUB_INSTALLATION_ACCOUNT_ID", "installation account id"),
            account_login=_matches(values, "GITHUB_INSTALLATION_ACCOUNT_LOGIN", "installation account login", _LOGIN),
            repositories=repositories,
            repository_count=repository_count,
            workflow_path=_matches(values, "READINESS_WORKFLOW_PATH", "workflow path", _WORKFLOW_PATH),
            reminder_seconds=_positive_decimal(values, "READINESS_REMINDER_SECONDS", "reminder seconds"),
            provider=provider,
            model=model,
            github_private_key=_secret(values, "GITHUB_APP_PRIVATE_KEY_PEM", "GitHub App private key"),
            webhook_secret=_secret(values, "GITHUB_APP_WEBHOOK_SECRET", "GitHub App webhook secret"),
            agent_key=agent_key,
        )

    def render_environment(self) -> str:
        values = (
            ("HAMSTERDAN_GITHUB_APP_ID", str(self.app_id)),
            ("HAMSTERDAN_GITHUB_APP_SLUG", self.app_slug),
            ("HAMSTERDAN_GITHUB_CLIENT_ID", self.client_id),
            ("HAMSTERDAN_GITHUB_ACCOUNT_ID", str(self.account_id)),
            ("HAMSTERDAN_GITHUB_ACCOUNT_LOGIN", self.account_login),
            ("HAMSTERDAN_ALLOWED_REPOSITORIES", self.repositories),
            ("HAMSTERDAN_STATE_PATH", "/var/lib/hamsterdan"),
            ("HAMSTERDAN_GITHUB_PRIVATE_KEY_FILE", "/run/secrets/hamsterdan/github-app.pem"),
            ("HAMSTERDAN_GITHUB_WEBHOOK_SECRET_FILE", "/run/secrets/hamsterdan/webhook-secret"),
            ("HAMSTERDAN_PI_PROVIDER", self.provider),
            ("HAMSTERDAN_PI_MODEL", self.model),
            ("HAMSTERDAN_PI_API_KEY_FILE", "/run/secrets/hamsterdan/agent-api-key"),
            ("HAMSTERDAN_WORKFLOW_PATH", self.workflow_path),
            ("HAMSTERDAN_REMINDER_SECONDS", str(self.reminder_seconds)),
        )
        return "".join(f"{name}={value}\n" for name, value in values)


@dataclass(frozen=True)
class RuntimeFiles:
    environment: Path
    github_private_key: Path
    webhook_secret: Path
    agent_key: Path


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
        environment=root / "hamsterdan.env",
        github_private_key=root / "github-app.pem",
        webhook_secret=root / "webhook-secret",
        agent_key=root / "agent-api-key",
    )
    try:
        _write_private(files.environment, config.render_environment())
        _write_private(files.github_private_key, config.github_private_key)
        _write_private(files.webhook_secret, config.webhook_secret)
        _write_private(files.agent_key, config.agent_key)
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
        "runtime_agent_key": str(files.agent_key),
        "runtime_environment": str(files.environment),
        "runtime_github_private_key": str(files.github_private_key),
        "runtime_webhook_secret": str(files.webhook_secret),
        "expected_app_id": config.app_id,
        "expected_app_slug": config.app_slug,
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
        "deployment/ansible/runtime.yml",
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
        raise RuntimeDeploymentError("runtime provisioning playbook failed") from error


def provision(manifest: Path, *, confirm_create: str | None) -> deploy.Candidate:
    config = RuntimeConfig.from_environment()
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


def parser() -> argparse.ArgumentParser:
    value = argparse.ArgumentParser(description=__doc__)
    value.add_argument("--manifest", type=Path, required=True)
    value.add_argument("--confirm-create", help="exact VM name required before creation")
    return value


def main() -> int:
    arguments = parser().parse_args()
    try:
        candidate = provision(arguments.manifest, confirm_create=arguments.confirm_create)
        print(f"validated inactive runtime for {candidate.image} on {exe_vm.DEFAULT_SPEC.name}")
        return 0
    except (RuntimeDeploymentError, deploy.DeploymentError, exe_vm.ExeError, release.ReleaseError) as error:
        print(f"runtime provisioning refused: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
