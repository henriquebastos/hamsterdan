from __future__ import annotations

import base64
import stat
import subprocess
from pathlib import Path

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import (
    Encoding,
    NoEncryption,
    PrivateFormat,
    PublicFormat,
    load_ssh_private_key,
)

from deployment import exe_access

PRIVATE_KEY = Ed25519PrivateKey.generate().private_bytes(Encoding.PEM, PrivateFormat.OpenSSH, NoEncryption())
HOST_KEY = "example-vm.exe.xyz ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAABAQCanary\n"


def environment() -> dict[str, str]:
    return {"EXE_DEV_SSH_PRIVATE_KEY_B64": base64.b64encode(PRIVATE_KEY).decode()}


def test_temporary_access_verifies_the_gateway_key_and_cleans_up(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(exe_access, "scan_host_key", lambda _: HOST_KEY)
    monkeypatch.setattr(exe_access, "host_key_fingerprints", lambda _: {exe_access.EXE_HOST_KEY_FINGERPRINT})

    with exe_access.temporary_access("example-vm.exe.xyz", environment=environment()) as access:
        key_path = access.private_key
        known_hosts_path = access.known_hosts
        expected_public = (
            load_ssh_private_key(PRIVATE_KEY, password=None)
            .public_key()
            .public_bytes(Encoding.OpenSSH, PublicFormat.OpenSSH)
        )
        observed_public = (
            load_ssh_private_key(key_path.read_bytes(), password=None)
            .public_key()
            .public_bytes(Encoding.OpenSSH, PublicFormat.OpenSSH)
        )
        assert observed_public == expected_public
        assert stat.S_IMODE(key_path.stat().st_mode) == 0o600
        assert known_hosts_path.read_text() == HOST_KEY
        assert "StrictHostKeyChecking=yes" in access.ssh_common_args
        assert "UserKnownHostsFile=" in access.ssh_common_args

    assert not key_path.exists()
    assert not known_hosts_path.exists()


def test_temporary_access_rejects_an_unexpected_host_key_and_cleans_up(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(exe_access.tempfile, "mkdtemp", lambda **_: str(tmp_path))
    monkeypatch.setattr(exe_access, "scan_host_key", lambda _: HOST_KEY)
    monkeypatch.setattr(exe_access, "host_key_fingerprints", lambda _: {"SHA256:unexpected"})

    with (
        pytest.raises(exe_access.AccessError, match="fingerprint does not match"),
        exe_access.temporary_access("example-vm.exe.xyz", environment=environment()),
    ):
        raise AssertionError("unreachable")

    assert not (tmp_path / "id_exe").exists()
    assert not (tmp_path / "known_hosts").exists()


def test_temporary_access_requires_a_valid_base64_private_key() -> None:
    with (
        pytest.raises(exe_access.AccessError, match="valid base64 private key"),
        exe_access.temporary_access(
            "example-vm.exe.xyz",
            environment={"EXE_DEV_SSH_PRIVATE_KEY_B64": "private-key-canary"},
        ),
    ):
        raise AssertionError("unreachable")


def test_temporary_access_normalizes_a_pkcs8_key_for_openssh(monkeypatch: pytest.MonkeyPatch) -> None:
    pkcs8 = Ed25519PrivateKey.generate().private_bytes(Encoding.PEM, PrivateFormat.PKCS8, NoEncryption())
    monkeypatch.setattr(exe_access, "scan_host_key", lambda _: HOST_KEY)
    monkeypatch.setattr(exe_access, "host_key_fingerprints", lambda _: {exe_access.EXE_HOST_KEY_FINGERPRINT})

    with exe_access.temporary_access(
        "example-vm.exe.xyz",
        environment={"EXE_DEV_SSH_PRIVATE_KEY_B64": base64.b64encode(pkcs8).decode()},
    ) as access:
        assert access.private_key.read_bytes().startswith(b"-----BEGIN OPENSSH PRIVATE KEY-----\n")
        completed = subprocess.run(
            ("ssh-keygen", "-y", "-f", str(access.private_key)),
            check=False,
            capture_output=True,
            text=True,
        )

    assert completed.returncode == 0


def test_ssh_preflight_requires_a_real_linux_vm_shell(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    access = exe_access.Access(
        private_key=tmp_path / "id_exe",
        known_hosts=tmp_path / "known_hosts",
        ssh_host="example-vm.exe.xyz",
    )
    commands: list[tuple[str, ...]] = []

    def fake_run(command: tuple[str, ...], **_: object) -> subprocess.CompletedProcess[str]:
        commands.append(command)
        return subprocess.CompletedProcess(command, 0, "Linux x86_64\n", "")

    monkeypatch.setattr(exe_access.subprocess, "run", fake_run)

    exe_access.wait_for_ssh(access, timeout=1)

    assert commands[0][-2:] == ("uname", "-sm")


def test_ssh_preflight_rejects_a_key_routed_to_the_control_repl(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    access = exe_access.Access(
        private_key=tmp_path / "id_exe",
        known_hosts=tmp_path / "known_hosts",
        ssh_host="example-vm.exe.xyz",
    )
    monkeypatch.setattr(
        exe_access.subprocess,
        "run",
        lambda *_, **__: subprocess.CompletedProcess((), 1, 'exe.dev repl: command not found: "uname -sm"\n', ""),
    )

    with pytest.raises(exe_access.AccessError, match="not authorized"):
        exe_access.wait_for_ssh(access, timeout=1)
