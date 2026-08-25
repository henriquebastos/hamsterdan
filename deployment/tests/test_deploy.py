from __future__ import annotations

import json
from pathlib import Path

import pytest

from deployment import deploy, exe_access


def manifest_value(**overrides: object) -> dict[str, object]:
    revision = "a" * 40
    value: dict[str, object] = {
        "dirty": False,
        "image": f"hamsterdan:sha-{revision}",
        "image_digest": f"sha256:{'b' * 64}",
        "image_id": f"sha256:{'c' * 64}",
        "platform": "linux/amd64",
        "source_revision": revision,
        "verified": True,
        "version": "0.1.0",
    }
    value.update(overrides)
    return value


def write_manifest(tmp_path: Path, **overrides: object) -> Path:
    path = tmp_path / "release.json"
    path.write_text(json.dumps(manifest_value(**overrides)))
    return path


def test_candidate_requires_a_clean_verified_linux_amd64_manifest(tmp_path: Path) -> None:
    candidate = deploy.read_candidate(write_manifest(tmp_path))

    assert candidate.manifest.is_absolute()
    assert candidate.image == f"hamsterdan:sha-{'a' * 40}"
    assert candidate.image_id == f"sha256:{'c' * 64}"

    for overrides, message in (
        ({"dirty": True}, "clean candidate"),
        ({"verified": False}, "verified candidate"),
        ({"platform": "linux/arm64"}, "linux/amd64"),
        ({"image": "hamsterdan:latest"}, "immutable image name"),
    ):
        with pytest.raises(deploy.DeploymentError, match=message):
            deploy.read_candidate(write_manifest(tmp_path, **overrides))


def test_ansible_command_carries_only_candidate_identity_and_strict_ssh_paths(tmp_path: Path) -> None:
    candidate = deploy.read_candidate(write_manifest(tmp_path))
    archive = tmp_path / "candidate.tar.gz"
    archive.write_bytes(b"candidate")
    access = exe_access.Access(
        private_key=tmp_path / "id_exe",
        known_hosts=tmp_path / "known_hosts",
        ssh_host="example-vm.exe.xyz",
    )

    command, variables = deploy.ansible_invocation(
        candidate=candidate,
        archive=archive,
        archive_sha256="d" * 64,
        access=access,
    )

    assert command[:5] == (
        "ansible-playbook",
        "--inventory",
        "example-vm.exe.xyz,",
        "--user",
        "exedev",
    )
    assert "--private-key" in command
    assert "--ssh-common-args" in command
    assert command[-1] == "deployment/ansible/candidate.yml"
    assert variables == {
        "candidate_archive": str(archive),
        "candidate_archive_sha256": "d" * 64,
        "candidate_image": candidate.image,
        "candidate_image_id": candidate.image_id,
        "candidate_revision": candidate.revision,
        "candidate_version": candidate.version,
    }
    assert "EXE_DEV_API_TOKEN" not in json.dumps(variables)
    assert "EXE_DEV_SSH_PRIVATE_KEY_B64" not in json.dumps(variables)


def test_candidate_playbook_loads_and_verifies_without_starting_the_host() -> None:
    playbook = (deploy.ROOT / "deployment" / "ansible" / "candidate.yml").read_text()

    assert "ansible_architecture == 'x86_64'" in playbook
    assert "become: true" in playbook
    assert "sha256sum" in playbook
    assert "docker image load" in playbook
    assert "candidate_image_id" in playbook
    assert "--help" in playbook
    assert "/opt/hamsterdan/.venv/bin/python" in playbook
    assert "/opt/hamsterdan/pi/node_modules/node/bin/node" in playbook
    assert "test -w /var/lib/hamsterdan" in playbook
    assert "systemd" not in playbook
    assert "HAMSTERDAN_GITHUB" not in playbook
