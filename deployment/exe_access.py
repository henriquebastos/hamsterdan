"""Temporary, fingerprint-pinned SSH custody for exe.dev deployment."""

from __future__ import annotations

import base64
import binascii
import os
import re
import shlex
import shutil
import subprocess
import tempfile
import time
from collections.abc import Callable, Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

from cryptography.exceptions import UnsupportedAlgorithm
from cryptography.hazmat.primitives.serialization import (
    Encoding,
    NoEncryption,
    PrivateFormat,
    load_pem_private_key,
    load_ssh_private_key,
)

EXE_HOST_KEY_FINGERPRINT = "SHA256:JJOP/lwiBGOMilfONPWZCXUrfK154cnJFXcqlsi6lPo"
SSH_HOST = re.compile(r"[a-z][a-z0-9-]{0,62}\.exe\.xyz")


class AccessError(RuntimeError):
    """A bounded SSH-access failure that contains no credential value."""


@dataclass(frozen=True)
class Access:
    private_key: Path
    known_hosts: Path
    ssh_host: str

    @property
    def ssh_options(self) -> tuple[str, ...]:
        return (
            "-o",
            "BatchMode=yes",
            "-o",
            "IdentitiesOnly=yes",
            "-o",
            "IdentityAgent=none",
            "-o",
            "StrictHostKeyChecking=yes",
            "-o",
            f"UserKnownHostsFile={self.known_hosts}",
            "-o",
            "GlobalKnownHostsFile=/dev/null",
            "-o",
            "ConnectTimeout=10",
        )

    @property
    def ssh_common_args(self) -> str:
        return shlex.join(self.ssh_options)


def _private_key(environment: Mapping[str, str]) -> bytes:
    encoded = environment.get("EXE_DEV_SSH_PRIVATE_KEY_B64", "")
    try:
        decoded = base64.b64decode("".join(encoded.split()), validate=True)
    except (ValueError, binascii.Error) as error:
        raise AccessError("EXE_DEV_SSH_PRIVATE_KEY_B64 must contain a valid base64 private key") from error
    if not decoded.startswith(b"-----BEGIN ") or b"PRIVATE KEY-----" not in decoded or not decoded.endswith(b"\n"):
        raise AccessError("EXE_DEV_SSH_PRIVATE_KEY_B64 must contain a valid base64 private key")
    try:
        if decoded.startswith(b"-----BEGIN OPENSSH PRIVATE KEY-----"):
            private_key = load_ssh_private_key(decoded, password=None)
        else:
            private_key = load_pem_private_key(decoded, password=None)
        return private_key.private_bytes(Encoding.PEM, PrivateFormat.OpenSSH, NoEncryption())
    except (TypeError, ValueError, UnsupportedAlgorithm) as error:
        raise AccessError("EXE_DEV_SSH_PRIVATE_KEY_B64 must contain a valid unencrypted SSH private key") from error


def _write_private(path: Path, value: bytes) -> None:
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "wb") as stream:
        stream.write(value)


def scan_host_key(host: str) -> str:
    try:
        completed = subprocess.run(
            ("ssh-keyscan", "-T", "10", "-t", "rsa", host),
            check=True,
            capture_output=True,
            text=True,
            timeout=15,
        )
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired) as error:
        raise AccessError(f"could not read the SSH host key for {host}") from error
    if not completed.stdout.strip():
        raise AccessError(f"could not read the SSH host key for {host}")
    return completed.stdout


def host_key_fingerprints(path: Path) -> set[str]:
    try:
        completed = subprocess.run(
            ("ssh-keygen", "-lf", str(path), "-E", "sha256"),
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError) as error:
        raise AccessError("could not fingerprint the exe.dev SSH host key") from error
    fingerprints = {line.split()[1] for line in completed.stdout.splitlines() if len(line.split()) >= 2}
    if not fingerprints:
        raise AccessError("could not fingerprint the exe.dev SSH host key")
    return fingerprints


@contextmanager
def temporary_access(
    host: str,
    *,
    environment: Mapping[str, str] | None = None,
) -> Iterator[Access]:
    if SSH_HOST.fullmatch(host) is None:
        raise AccessError("exe.dev SSH host is malformed")
    env = os.environ if environment is None else environment
    directory = Path(tempfile.mkdtemp(prefix="hamsterdan-exe-"))
    directory.chmod(0o700)
    private_key = directory / "id_exe"
    known_hosts = directory / "known_hosts"
    try:
        _write_private(private_key, _private_key(env))
        host_key = scan_host_key(host)
        known_hosts.write_text(host_key)
        known_hosts.chmod(0o600)
        if host_key_fingerprints(known_hosts) != {EXE_HOST_KEY_FINGERPRINT}:
            raise AccessError("exe.dev SSH host-key fingerprint does not match the published value")
        yield Access(private_key=private_key, known_hosts=known_hosts, ssh_host=host)
    finally:
        shutil.rmtree(directory, ignore_errors=True)


def wait_for_ssh(
    access: Access,
    *,
    timeout: float = 180,
    sleep: Callable[[float], None] = time.sleep,
    clock: Callable[[], float] = time.monotonic,
) -> None:
    deadline = clock() + timeout
    while clock() < deadline:
        try:
            completed = subprocess.run(
                (
                    "ssh",
                    *access.ssh_options,
                    "-i",
                    str(access.private_key),
                    f"root@{access.ssh_host}",
                    "uname",
                    "-sm",
                ),
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                timeout=15,
                check=False,
                text=True,
            )
        except OSError:
            completed = None
        except subprocess.TimeoutExpired:
            completed = None
        if completed is not None:
            if completed.stdout.startswith("exe.dev repl:"):
                raise AccessError(f"the configured SSH key is not authorized for {access.ssh_host}")
            if completed.returncode == 0 and completed.stdout.strip() == "Linux x86_64":
                return
        sleep(2)
    raise AccessError(f"SSH for {access.ssh_host} did not become ready within {timeout:g} seconds")
