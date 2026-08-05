from __future__ import annotations

import inspect
import os
import stat
from pathlib import Path

import pytest
from petrus.agenticus.connection.key import KeyContext, KeyOperationError
from petrus.agenticus.runtime.pi_a2_host import PiA2RuntimeHost

from hamsterdan.host import pi_a2
from hamsterdan.host.pi_a2 import (
    OneShotApiKeySupplier,
    PersistentKeyOperations,
    PiA2InstallationConfig,
    compose_owned_pi_a2,
)


def test_persistent_keys_authenticate_context_tamper_and_erase(tmp_path: Path) -> None:
    context = KeyContext("synthetic", 1, 1)
    sealed = PersistentKeyOperations(tmp_path / "keys").seal(context, bytearray(b"synthetic secret"))
    recreated = PersistentKeyOperations(tmp_path / "keys")
    assert recreated.open(context, sealed) == bytearray(b"synthetic secret")
    with pytest.raises(KeyOperationError):
        recreated.open(KeyContext("synthetic", 2, 1), sealed)
    with pytest.raises(KeyOperationError):
        recreated.open(context, sealed[:-1] + bytes([sealed[-1] ^ 1]))
    assert recreated.erase("synthetic").erased
    with pytest.raises(KeyOperationError):
        recreated.open(context, sealed)


def test_new_key_is_synced_before_sealing_returns(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    syncs: list[str] = []
    fsync = os.fsync

    def observe(descriptor: int) -> None:
        syncs.append("directory" if stat.S_ISDIR(os.fstat(descriptor).st_mode) else "file")
        fsync(descriptor)

    monkeypatch.setattr(os, "fsync", observe)
    PersistentKeyOperations(tmp_path / "keys").seal(KeyContext("synthetic", 1, 1), bytearray(b"synthetic"))

    assert syncs == ["file", "directory"]


def test_one_shot_supplier_transfers_mutable_buffer_once() -> None:
    source = bytearray(b"synthetic")
    calls = 0

    def load() -> bytearray:
        nonlocal calls
        calls += 1
        return source

    supplier = OneShotApiKeySupplier(load)
    assert supplier() is source
    with pytest.raises(RuntimeError, match="already spent"):
        supplier()
    assert calls == 1


def test_owned_composition_and_probe_do_not_request_authority(tmp_path: Path) -> None:
    host = compose_owned_pi_a2(tmp_path)
    try:
        assert isinstance(host, PiA2RuntimeHost)
        assert host.descriptor.identity.name == "pi.native.a2.local"
        assert host.authority.connection.profile == "api-key"
        assert not host.authority_requested
        host.probe()
        assert not host.authority_requested
    finally:
        host.close()


def test_direct_key_config_and_probe_validate_path_without_reading_authority(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "authority"
    path.write_text("x" * 32)
    path.chmod(0o600)
    runtime = tmp_path / "runtime"
    runtime.mkdir()
    cli, node = runtime / "cli.js", runtime / "node"
    cli.touch()
    node.touch()
    config = PiA2InstallationConfig.from_environment(
        {
            "HAMSTERDAN_ANTHROPIC_API_KEY_FILE": str(path),
            "HAMSTERDAN_PI_CLI_PATH": str(cli),
            "HAMSTERDAN_PI_NODE_PATH": str(node),
            "HAMSTERDAN_PI_PACKAGE_ROOT": str(runtime),
        }
    )
    calls = 0

    def observe(selected: Path) -> bytearray:
        nonlocal calls
        calls += 1
        return bytearray(b"synthetic-direct-key")

    monkeypatch.setattr(pi_a2, "_load_direct_key", observe)
    host = compose_owned_pi_a2(tmp_path / "state", config)
    try:
        host.probe()
        assert calls == 0 and not host.authority_requested
        supplied = host.authority.supply_api_key()
        assert supplied == bytearray(b"synthetic-direct-key")
        assert calls == 1
        with pytest.raises(RuntimeError, match="already spent"):
            host.authority.supply_api_key()
    finally:
        for index in range(len(supplied)):
            supplied[index] = 0
        host.close()


@pytest.mark.parametrize("failure", ["missing", "symlink", "permissions", "small", "large"])
def test_direct_key_config_rejects_unsafe_files_without_reading_them(tmp_path: Path, failure: str) -> None:
    path = tmp_path / "authority"
    if failure != "missing":
        path.write_bytes(b"x" * (513 if failure == "large" else 32))
        path.chmod(0o600)
    if failure == "symlink":
        target = tmp_path / "target"
        path.rename(target)
        path.symlink_to(target)
    elif failure == "permissions":
        path.chmod(0o640)
    elif failure == "small":
        path.write_bytes(b"short")

    with pytest.raises(ValueError) as caught:
        PiA2InstallationConfig.from_environment(
            {
                "HAMSTERDAN_ANTHROPIC_API_KEY_FILE": str(path),
                "HAMSTERDAN_PI_CLI_PATH": str(tmp_path / "cli"),
                "HAMSTERDAN_PI_NODE_PATH": str(tmp_path / "node"),
                "HAMSTERDAN_PI_PACKAGE_ROOT": str(tmp_path / "package"),
            }
        )
    assert "x" * 16 not in str(caught.value)


@pytest.mark.parametrize(
    "name",
    [
        "HAMSTERDAN_ANTHROPIC_API_KEY_FILE",
        "HAMSTERDAN_PI_CLI_PATH",
        "HAMSTERDAN_PI_NODE_PATH",
        "HAMSTERDAN_PI_PACKAGE_ROOT",
    ],
)
def test_installation_config_rejects_relative_custody_paths(tmp_path: Path, name: str) -> None:
    path = tmp_path / "authority"
    path.write_bytes(b"synthetic-direct-authority")
    path.chmod(0o600)
    environment = {
        "HAMSTERDAN_ANTHROPIC_API_KEY_FILE": str(path),
        "HAMSTERDAN_PI_CLI_PATH": str(tmp_path / "cli"),
        "HAMSTERDAN_PI_NODE_PATH": str(tmp_path / "node"),
        "HAMSTERDAN_PI_PACKAGE_ROOT": str(tmp_path / "package"),
    }
    environment[name] = "relative"

    with pytest.raises(ValueError, match="must be absolute"):
        PiA2InstallationConfig.from_environment(environment)


def test_direct_key_loader_returns_erasable_exact_material_and_refuses_whitespace(tmp_path: Path) -> None:
    path = tmp_path / "authority"
    path.write_bytes(b"synthetic-direct-key-material")
    path.chmod(0o600)
    value = pi_a2._load_direct_key(path)
    assert value == bytearray(b"synthetic-direct-key-material")
    for index in range(len(value)):
        value[index] = 0

    path.write_bytes(b"synthetic-direct-key-material\n")
    with pytest.raises(ValueError, match="malformed"):
        pi_a2._load_direct_key(path)


def test_production_composition_does_not_inject_provider_or_client_factory() -> None:
    source = inspect.getsource(compose_owned_pi_a2)
    assert "client_factory=" not in source
    assert "provider=" not in source.partition("compose_pi_a2_runtime(")[2]
    assert "compose_pi_a2_runtime(config=config, authority=authority)" in source
