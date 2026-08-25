#!/usr/bin/env python3
"""Transfer and qualify one exact Hamsterdan candidate on exe.dev."""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from deployment import exe_access, exe_vm, release

ROOT = Path(__file__).resolve().parents[1]
SHA256 = re.compile(r"sha256:[0-9a-f]{64}")
REVISION = re.compile(r"[0-9a-f]{40}")


class DeploymentError(RuntimeError):
    """A bounded deployment failure that contains no credential value."""


@dataclass(frozen=True)
class Candidate:
    manifest: Path
    image: str
    image_digest: str
    image_id: str
    revision: str
    version: str


def read_candidate(path: Path) -> Candidate:
    path = path.resolve()
    try:
        value = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as error:
        raise DeploymentError("release manifest is unavailable or malformed") from error
    if not isinstance(value, dict):
        raise DeploymentError("release manifest is malformed")
    if value.get("dirty") is not False:
        raise DeploymentError("deployment requires a clean candidate")
    if value.get("verified") is not True:
        raise DeploymentError("deployment requires a verified candidate")
    if value.get("platform") != "linux/amd64":
        raise DeploymentError("deployment requires a linux/amd64 candidate")
    revision = value.get("source_revision")
    image = value.get("image")
    image_digest = value.get("image_digest")
    image_id = value.get("image_id")
    version = value.get("version")
    if not isinstance(revision, str) or REVISION.fullmatch(revision) is None:
        raise DeploymentError("candidate source revision is malformed")
    if image != f"hamsterdan:sha-{revision}":
        raise DeploymentError("candidate does not have an immutable image name")
    if not isinstance(image_digest, str) or SHA256.fullmatch(image_digest) is None:
        raise DeploymentError("candidate image digest is malformed")
    if not isinstance(image_id, str) or SHA256.fullmatch(image_id) is None:
        raise DeploymentError("candidate image identity is malformed")
    if not isinstance(version, str) or not version:
        raise DeploymentError("candidate version is malformed")
    return Candidate(path, image, image_digest, image_id, revision, version)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def verify_local_image(candidate: Candidate, *, environment: Mapping[str, str] | None = None) -> tuple[str, ...]:
    container = release.container_command(environment)
    observed = release.capture((*container, "image", "inspect", "--format={{.Id}}", candidate.image))
    if observed != candidate.image_id:
        raise DeploymentError("local image does not match the verified candidate")
    return container


def export_candidate(candidate: Candidate, *, container: Sequence[str]) -> tuple[Path, str]:
    archive = candidate.manifest.parent / "candidate.tar.gz"
    checksum = archive.with_suffix(".gz.sha256")
    if archive.is_file() and checksum.is_file():
        expected = checksum.read_text().strip()
        if re.fullmatch(r"[0-9a-f]{64}", expected) and _sha256(archive) == expected:
            return archive, expected

    candidate.manifest.parent.mkdir(mode=0o755, parents=True, exist_ok=True)
    temporary = archive.with_suffix(".tmp")
    temporary.unlink(missing_ok=True)
    with tempfile.TemporaryFile() as errors:
        try:
            process = subprocess.Popen(
                (*container, "image", "save", candidate.image),
                stdout=subprocess.PIPE,
                stderr=errors,
            )
        except OSError as error:
            raise DeploymentError("could not start the candidate export") from error
        try:
            if process.stdout is None:
                raise DeploymentError("candidate export did not provide image data")
            with temporary.open("wb") as raw, gzip.GzipFile(fileobj=raw, mode="wb", mtime=0) as compressed:
                shutil.copyfileobj(process.stdout, compressed, length=1024 * 1024)
            process.stdout.close()
            if process.wait() != 0:
                raise DeploymentError("container engine could not export the candidate")
        except BaseException:
            if process.poll() is None:
                process.kill()
            process.wait()
            temporary.unlink(missing_ok=True)
            raise
    temporary.replace(archive)
    observed = _sha256(archive)
    checksum.write_text(observed + "\n")
    return archive, observed


def ansible_invocation(
    *,
    candidate: Candidate,
    archive: Path,
    archive_sha256: str,
    access: exe_access.Access,
) -> tuple[tuple[str, ...], dict[str, str]]:
    variables = {
        "candidate_archive": str(archive),
        "candidate_archive_sha256": archive_sha256,
        "candidate_image": candidate.image,
        "candidate_image_id": candidate.image_id,
        "candidate_revision": candidate.revision,
        "candidate_version": candidate.version,
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
        "deployment/ansible/candidate.yml",
    )
    return command, variables


def run_ansible(command: Sequence[str]) -> None:
    if shutil.which("ansible-playbook") is None:
        raise DeploymentError("ansible-playbook is required; run uv sync --frozen")
    environment = dict(os.environ)
    environment.update(
        {
            "ANSIBLE_HOST_KEY_CHECKING": "True",
            "ANSIBLE_NOCOLOR": "1",
            "ANSIBLE_RETRY_FILES_ENABLED": "False",
        }
    )
    try:
        subprocess.run(command, cwd=ROOT, env=environment, check=True, text=True)
    except (OSError, subprocess.CalledProcessError) as error:
        raise DeploymentError("candidate qualification playbook failed") from error


def deploy(manifest: Path, *, confirm_create: str | None) -> Candidate:
    candidate = read_candidate(manifest)
    container = verify_local_image(candidate)
    archive, archive_sha256 = export_candidate(candidate, container=container)
    exe_vm.ensure_vm(exe_vm.DEFAULT_SPEC, confirm_create=confirm_create)
    vm = exe_vm.wait_for_running_vm(exe_vm.DEFAULT_SPEC)
    try:
        with exe_access.temporary_access(vm.ssh_host) as access:
            exe_access.wait_for_ssh(access)
            command, _ = ansible_invocation(
                candidate=candidate,
                archive=archive,
                archive_sha256=archive_sha256,
                access=access,
            )
            run_ansible(command)
    except (exe_access.AccessError, exe_vm.ExeError) as error:
        raise DeploymentError(str(error)) from error
    return candidate


def parser() -> argparse.ArgumentParser:
    value = argparse.ArgumentParser(description=__doc__)
    value.add_argument("--manifest", type=Path, required=True)
    value.add_argument("--confirm-create", help="exact VM name required before creation")
    return value


def main() -> int:
    arguments = parser().parse_args()
    try:
        candidate = deploy(arguments.manifest, confirm_create=arguments.confirm_create)
        print(f"qualified {candidate.image} on {exe_vm.DEFAULT_SPEC.name}")
        return 0
    except (DeploymentError, exe_vm.ExeError, release.ReleaseError) as error:
        print(f"deployment refused: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
