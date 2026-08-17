from __future__ import annotations

import inspect
import os
import stat
from pathlib import Path
from typing import assert_type

import pytest
from petrus.agenticus.connection.key import KeyContext, KeyOperationError
from petrus.agenticus.hands.contract import ToolMethod
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
        assert_type(host, PiA2RuntimeHost)
        assert host.descriptor.identity.name == "pi.native.a2.local"
        assert host.authority.connection.profile == "api-key"
        assert not host.authority_requested
        host.probe()
        assert not host.authority_requested
    finally:
        host.close()


def test_owned_composition_retains_a_finite_runtime_deadline(tmp_path: Path) -> None:
    host = compose_owned_pi_a2(tmp_path)
    try:
        assert (
            host.config.wall_timeout,
            host.config.attachment_timeout,
            host.config.cancellation_grace,
        ) == (900, 960, 5)
        assert host.config.attachment_timeout > host.config.wall_timeout + host.config.cancellation_grace
        assert host.config.max_tool_calls == 32
        assert host.config.capabilities == frozenset(
            {ToolMethod.WORKSPACE_READ, ToolMethod.WORKSPACE_SEARCH, ToolMethod.WORKSPACE_WRITE}
        )
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
            "HAMSTERDAN_PI_PROVIDER": "openai",
            "HAMSTERDAN_PI_MODEL": "gpt-5.6-sol",
            "HAMSTERDAN_PI_API_KEY_FILE": str(path),
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
        assert host.authority.connection.provider == "openai"
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
                "HAMSTERDAN_PI_PROVIDER": "anthropic",
                "HAMSTERDAN_PI_MODEL": "claude-sonnet-4-5",
                "HAMSTERDAN_PI_API_KEY_FILE": str(path),
                "HAMSTERDAN_PI_CLI_PATH": str(tmp_path / "cli"),
                "HAMSTERDAN_PI_NODE_PATH": str(tmp_path / "node"),
                "HAMSTERDAN_PI_PACKAGE_ROOT": str(tmp_path / "package"),
            }
        )
    assert "x" * 16 not in str(caught.value)


@pytest.mark.parametrize(
    "name",
    [
        "HAMSTERDAN_PI_API_KEY_FILE",
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
        "HAMSTERDAN_PI_PROVIDER": "anthropic",
        "HAMSTERDAN_PI_MODEL": "claude-sonnet-4-5",
        "HAMSTERDAN_PI_API_KEY_FILE": str(path),
        "HAMSTERDAN_PI_CLI_PATH": str(tmp_path / "cli"),
        "HAMSTERDAN_PI_NODE_PATH": str(tmp_path / "node"),
        "HAMSTERDAN_PI_PACKAGE_ROOT": str(tmp_path / "package"),
    }
    environment[name] = "relative"

    with pytest.raises(ValueError, match="must be absolute"):
        PiA2InstallationConfig.from_environment(environment)


@pytest.mark.parametrize(
    ("provider", "model"),
    [
        ("anthropic", "claude-sonnet-4-5"),
        ("openai", "gpt-5.6-sol"),
        ("openrouter", "anthropic/claude-sonnet-4.5"),
    ],
)
def test_installation_config_accepts_only_qualified_provider_model_pairs(
    tmp_path: Path, provider: str, model: str
) -> None:
    key = tmp_path / "authority"
    key.write_bytes(b"synthetic-direct-authority")
    key.chmod(0o600)
    environment = {
        "HAMSTERDAN_PI_PROVIDER": provider,
        "HAMSTERDAN_PI_MODEL": model,
        "HAMSTERDAN_PI_API_KEY_FILE": str(key),
        "HAMSTERDAN_PI_CLI_PATH": str(tmp_path / "cli"),
        "HAMSTERDAN_PI_NODE_PATH": str(tmp_path / "node"),
        "HAMSTERDAN_PI_PACKAGE_ROOT": str(tmp_path / "package"),
    }

    assert PiA2InstallationConfig.from_environment(environment).provider == provider
    environment["HAMSTERDAN_PI_MODEL"] = "unqualified"
    with pytest.raises(ValueError, match="qualified"):
        PiA2InstallationConfig.from_environment(environment)


def test_existing_state_refuses_provider_change_before_authority_read_or_runtime_construction(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    state = tmp_path / "state"
    original = compose_owned_pi_a2(state)
    assert original.close()
    key = tmp_path / "authority"
    key.write_bytes(b"synthetic-direct-authority")
    key.chmod(0o600)
    environment = {
        "HAMSTERDAN_PI_PROVIDER": "openai",
        "HAMSTERDAN_PI_MODEL": "gpt-5.6-sol",
        "HAMSTERDAN_PI_API_KEY_FILE": str(key),
        "HAMSTERDAN_PI_CLI_PATH": str(tmp_path / "cli"),
        "HAMSTERDAN_PI_NODE_PATH": str(tmp_path / "node"),
        "HAMSTERDAN_PI_PACKAGE_ROOT": str(tmp_path / "package"),
    }
    reads = 0

    def read_authority(path: Path) -> bytearray:
        nonlocal reads
        reads += 1
        return bytearray(b"must-not-be-read")

    monkeypatch.setattr(pi_a2, "_load_direct_key", read_authority)

    with pytest.raises(ValueError, match="existing Pi A2 state"):
        PiA2InstallationConfig.from_environment(environment, state_path=state)
    assert reads == 0


def test_competing_provider_binding_winner_is_revalidated_before_runtime_construction(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    state = tmp_path / "state"
    root = state / "pi-a2"
    original_link = os.link

    def competing_link(source: Path, destination: Path) -> None:
        destination.write_bytes(b"openai\ngpt-5.6-sol\n")
        destination.chmod(0o600)
        original_link(source, destination)

    monkeypatch.setattr(os, "link", competing_link)

    with pytest.raises(ValueError, match="different provider/model"):
        compose_owned_pi_a2(state)
    assert (root / "installation").read_bytes() == b"openai\ngpt-5.6-sol\n"
    assert not (root / "runtime-host").exists()


def test_installation_binding_survives_a_crash_cut_after_atomic_publication(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    state = tmp_path / "state"
    root = state / "pi-a2"
    sync = pi_a2._sync_directory
    cuts = 0

    def cut_after_publication(path: Path) -> None:
        nonlocal cuts
        cuts += 1
        if path == root.resolve() and cuts == 1:
            raise OSError("synthetic crash cut")
        sync(path)

    monkeypatch.setattr(pi_a2, "_sync_directory", cut_after_publication)
    with pytest.raises(OSError, match="synthetic crash cut"):
        compose_owned_pi_a2(state)

    assert (root / "installation").read_bytes() == b"anthropic\nclaude-sonnet-4-5\n"
    assert not (root / "runtime-host").exists()
    monkeypatch.setattr(pi_a2, "_sync_directory", sync)
    restarted = compose_owned_pi_a2(state)
    assert restarted.close()


def test_installation_binding_is_restartable_under_a_restrictive_umask(tmp_path: Path) -> None:
    root = tmp_path / "pi-a2"
    root.mkdir(mode=0o700)
    previous = os.umask(0o777)
    try:
        pi_a2._bind_installation(root, "openai", "gpt-5.6-sol")
    finally:
        os.umask(previous)

    assert stat.S_IMODE((root / "installation").stat().st_mode) == 0o600
    pi_a2._bind_installation(root, "openai", "gpt-5.6-sol")


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
